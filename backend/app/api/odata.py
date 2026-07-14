"""OData v4-style integration surface — the SAP lingua franca.

Davey's Angular developers orchestrate data between custom front ends and SAP
(ECC / S/4HANA) over **OData**, mapping **WBS** (Work Breakdown Structure) and
**CATS** (Cross-Application Time Sheet) layers. This module mirrors that seam on
top of the CanopyOps domain — honestly, with synthetic data:

  * a TreatmentPlan (its WorkOrder + Corridor) projects to a **WBS element**;
  * a field execution projects to **CATS** time confirmations booked to that WBS.

It implements the OData patterns that role calls for:
  * server-driven paging (`$top` / `$skip` + ``@odata.nextLink``),
  * `$select` / `$filter` / `$orderby` / `$count` / `$expand`,
  * **deferred loading** — navigation properties are returned as links and only
    materialised when `$expand` is passed (never eagerly), and
  * **caching** — strong `ETag` + `If-None-Match` conditional requests (`304`).

Not real SAP; a compatible facade demonstrating the integration competency.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import domain as m
from app.services import assurance

router = APIRouter(tags=["odata (SAP-style integration)"])

PAGE_SIZE = 5  # server-driven paging window


# --------------------------------------------------------------------------- #
# Projections: CanopyOps domain -> SAP-style WBS / CATS entities               #
# --------------------------------------------------------------------------- #
def _wbs_code(reference: str) -> str:
    """WO-2026-1002 -> UVM.2026.1002 (a WBS-element-looking key)."""
    return reference.replace("WO-", "UVM.").replace("-", ".")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def wbs_elements(db: Session) -> list[dict[str, Any]]:
    """One WBS element per treatment plan, parented to its circuit."""
    plans = db.scalars(select(m.TreatmentPlan)).all()
    out: list[dict[str, Any]] = []
    for p in plans:
        wo = p.work_order
        corridor = wo.corridor if wo else None
        score, complete = assurance.evidence_score(p)
        out.append({
            "Wbs": _wbs_code(wo.reference) if wo else p.id,
            "ParentWbs": corridor.circuit_id if corridor else None,
            "WorkOrder": wo.reference if wo else None,
            "Description": (p.target_condition or "")[:120],
            "Circuit": corridor.circuit_id if corridor else None,
            "Span": corridor.span_label if corridor else None,
            "Status": p.status.value,
            "Priority": wo.priority.value if wo else None,
            "Method": p.method_category.value,
            "CoverageRatio": round(p.execution.coverage_ratio, 4)
            if (p.execution and p.execution.coverage_ratio is not None) else None,
            "EvidenceComplete": complete,
            "EvidenceScore": round(score, 4),
            "Revision": p.revision,
            "UpdatedAt": _iso(p.updated_at),
            "_planId": p.id,  # internal join key (stripped from output)
        })
    return out


def cats_entries(db: Session) -> list[dict[str, Any]]:
    """Time confirmations derived from field executions, booked to a WBS."""
    users = {u.id: u.display_name for u in db.scalars(select(m.User)).all()}
    plans = db.scalars(select(m.TreatmentPlan)).all()
    out: list[dict[str, Any]] = []
    seq = 0
    for p in plans:
        ex = p.execution
        if not ex:
            continue
        wo = p.work_order
        seq += 1
        # Deterministic synthetic hours (no randomness): crew day scaled by area
        # actually treated. Purely illustrative.
        cov = ex.coverage_ratio if ex.coverage_ratio is not None else 1.0
        hours = round(5.0 + cov * 3.0 + (seq % 3) * 0.5, 1)
        person = users.get(ex.crew_id, "Unknown")
        out.append({
            "CatsId": f"CATS-{seq:04d}",
            "Wbs": _wbs_code(wo.reference) if wo else p.id,
            "PersonnelId": f"EMP-{(ex.crew_id or '000000')[:6].upper()}",
            "PersonnelName": person,
            "WorkDate": _iso(ex.performed_at),
            "Hours": hours,
            "ActivityType": p.method_category.value,
            "Confirmed": True,
            "_planId": p.id,
        })
    return out


# --------------------------------------------------------------------------- #
# A focused OData v4 query engine over projected dict rows                     #
# --------------------------------------------------------------------------- #
_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b,
    "ge": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "le": lambda a, b: a is not None and a <= b,
}


def _coerce(token: str) -> Any:
    """OData literal -> Python value. 'text' -> str; 123 -> int; true -> bool."""
    t = token.strip()
    if len(t) >= 2 and t[0] == "'" and t[-1] == "'":
        return t[1:-1].replace("''", "'")
    low = t.lower()
    if low in ("true", "false"):
        return low == "true"
    if low == "null":
        return None
    try:
        return int(t)
    except ValueError:
        try:
            return float(t)
        except ValueError:
            return t


def _predicate(rows: list[dict], clause: str) -> list[dict]:
    """Apply one predicate: `Field op literal` or `contains(Field,'x')`."""
    clause = clause.strip()
    if clause.lower().startswith("contains(") and clause.endswith(")"):
        inner = clause[len("contains("):-1]
        field, _, needle = inner.partition(",")
        field, needle = field.strip(), _coerce(needle.strip())
        return [r for r in rows if str(needle).lower() in str(r.get(field, "")).lower()]
    parts = clause.split(None, 2)  # Field op literal
    if len(parts) != 3:
        return rows  # unrecognised — ignore rather than 500
    field, op, literal = parts
    fn = _OPS.get(op.lower())
    if not fn:
        return rows
    val = _coerce(literal)
    return [r for r in rows if fn(r.get(field), val)]


def _apply_filter(rows: list[dict], expr: str) -> list[dict]:
    """Subset grammar: predicates joined by top-level `and` / `or` (no grouping)."""
    if " or " in f" {expr} ":
        result: list[dict] = []
        seen: set[int] = set()
        for part in expr.split(" or "):
            for r in _apply_filter(rows, part):
                if id(r) not in seen:
                    seen.add(id(r))
                    result.append(r)
        return result
    out = rows
    for part in expr.split(" and "):
        out = _predicate(out, part)
    return out


def _apply_orderby(rows: list[dict], expr: str) -> list[dict]:
    for spec in reversed([s.strip() for s in expr.split(",") if s.strip()]):
        bits = spec.split()
        field = bits[0]
        desc = len(bits) > 1 and bits[1].lower() == "desc"
        rows = sorted(rows, key=lambda r: (r.get(field) is None, r.get(field)), reverse=desc)
    return rows


def _project(row: dict, select_expr: str | None) -> dict:
    clean = {k: v for k, v in row.items() if not k.startswith("_")}
    if not select_expr:
        return clean
    keep = {s.strip() for s in select_expr.split(",") if s.strip()}
    return {k: v for k, v in clean.items() if k in keep}


def _etag(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return 'W/"' + hashlib.sha1(raw).hexdigest()[:16] + '"'


def _collection_response(
    request: Request,
    if_none_match: str | None,
    entity_set: str,
    rows: list[dict],
    params: dict[str, str],
    nav_name: str | None = None,
    nav_rows_for: Any = None,
) -> Response:
    """Assemble an OData v4 collection response with the query options applied,
    deferred navigation links, server paging, and an ETag (304 on match)."""
    # $filter -> $orderby -> $count -> paging
    if params.get("$filter"):
        rows = _apply_filter(rows, params["$filter"])
    if params.get("$orderby"):
        rows = _apply_orderby(rows, params["$orderby"])

    total = len(rows)
    skip = int(params.get("$skip", 0) or 0)
    top = params.get("$top")
    window = int(top) if top is not None else PAGE_SIZE
    page = rows[skip: skip + window]

    expand = {e.strip() for e in (params.get("$expand", "").split(",")) if e.strip()}
    select_expr = params.get("$select")

    value = []
    for row in page:
        item = _project(row, select_expr)
        if nav_name:
            if nav_name in expand and nav_rows_for is not None:
                item[nav_name] = [
                    {k: v for k, v in nr.items() if not k.startswith("_")}
                    for nr in nav_rows_for(row)
                ]
            else:
                # DEFERRED: link only, materialised on $expand.
                key = row.get("Wbs")
                item[f"{nav_name}@odata.navigationLink"] = f"{entity_set}('{key}')/{nav_name}"
        value.append(item)

    body: dict[str, Any] = {"@odata.context": f"$metadata#{entity_set}", "value": value}
    if params.get("$count", "").lower() == "true":
        body["@odata.count"] = total
    if skip + window < total:
        nxt = skip + window
        body["@odata.nextLink"] = f"{entity_set}?$skip={nxt}" + (
            f"&$top={top}" if top else "")

    etag = _etag(body)
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-store"})
    return JSONResponse(body, headers={"ETag": etag, "Cache-Control": "no-store"})


def _query_params(request: Request) -> dict[str, str]:
    # Preserve $-prefixed OData system query options.
    return {k: v for k, v in request.query_params.items()}


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/odata/")
def service_document() -> dict:
    """OData service document — the entity sets a client can consume."""
    return {
        "@odata.context": "$metadata",
        "value": [
            {"name": "WbsElements", "kind": "EntitySet", "url": "WbsElements"},
            {"name": "CatsEntries", "kind": "EntitySet", "url": "CatsEntries"},
        ],
    }


@router.get("/odata/$metadata")
def metadata() -> PlainTextResponse:
    """EDMX metadata (CSDL) describing the entity model — as SAP OData exposes."""
    edmx = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="CanopyOps.Uvm" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="WbsElement">
        <Key><PropertyRef Name="Wbs"/></Key>
        <Property Name="Wbs" Type="Edm.String" Nullable="false"/>
        <Property Name="ParentWbs" Type="Edm.String"/>
        <Property Name="WorkOrder" Type="Edm.String"/>
        <Property Name="Description" Type="Edm.String"/>
        <Property Name="Circuit" Type="Edm.String"/>
        <Property Name="Span" Type="Edm.String"/>
        <Property Name="Status" Type="Edm.String"/>
        <Property Name="Priority" Type="Edm.String"/>
        <Property Name="Method" Type="Edm.String"/>
        <Property Name="CoverageRatio" Type="Edm.Double"/>
        <Property Name="EvidenceComplete" Type="Edm.Boolean"/>
        <Property Name="EvidenceScore" Type="Edm.Double"/>
        <Property Name="Revision" Type="Edm.Int32"/>
        <Property Name="UpdatedAt" Type="Edm.DateTimeOffset"/>
        <NavigationProperty Name="CatsEntries" Type="Collection(CanopyOps.Uvm.CatsEntry)"/>
      </EntityType>
      <EntityType Name="CatsEntry">
        <Key><PropertyRef Name="CatsId"/></Key>
        <Property Name="CatsId" Type="Edm.String" Nullable="false"/>
        <Property Name="Wbs" Type="Edm.String"/>
        <Property Name="PersonnelId" Type="Edm.String"/>
        <Property Name="PersonnelName" Type="Edm.String"/>
        <Property Name="WorkDate" Type="Edm.DateTimeOffset"/>
        <Property Name="Hours" Type="Edm.Double"/>
        <Property Name="ActivityType" Type="Edm.String"/>
        <Property Name="Confirmed" Type="Edm.Boolean"/>
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="WbsElements" EntityType="CanopyOps.Uvm.WbsElement">
          <NavigationPropertyBinding Path="CatsEntries" Target="CatsEntries"/>
        </EntitySet>
        <EntitySet Name="CatsEntries" EntityType="CanopyOps.Uvm.CatsEntry"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""
    return PlainTextResponse(edmx, media_type="application/xml")


@router.get("/odata/WbsElements")
def wbs_collection(
    request: Request,
    if_none_match: str | None = Header(None),
    db: Session = Depends(get_db),
) -> Response:
    rows = wbs_elements(db)
    cats = cats_entries(db)

    def nav_for(row: dict) -> list[dict]:
        return [c for c in cats if c["Wbs"] == row["Wbs"]]

    return _collection_response(
        request, if_none_match, "WbsElements", rows, _query_params(request),
        nav_name="CatsEntries", nav_rows_for=nav_for,
    )


@router.get("/odata/WbsElements('{key}')")
def wbs_entity(key: str, db: Session = Depends(get_db)) -> Response:
    row = next((r for r in wbs_elements(db) if r["Wbs"] == key), None)
    if row is None:
        return JSONResponse(
            {"error": {"code": "404", "message": f"WbsElement '{key}' not found"}},
            status_code=404,
        )
    body = {"@odata.context": "$metadata#WbsElements/$entity",
            **{k: v for k, v in row.items() if not k.startswith("_")}}
    return JSONResponse(body, headers={"ETag": _etag(body), "Cache-Control": "no-store"})


@router.get("/odata/WbsElements('{key}')/CatsEntries")
def wbs_cats_nav(
    key: str,
    request: Request,
    if_none_match: str | None = Header(None),
    db: Session = Depends(get_db),
) -> Response:
    rows = [c for c in cats_entries(db) if c["Wbs"] == key]
    return _collection_response(
        request, if_none_match, "CatsEntries", rows, _query_params(request),
    )


@router.get("/odata/CatsEntries")
def cats_collection(
    request: Request,
    if_none_match: str | None = Header(None),
    db: Session = Depends(get_db),
) -> Response:
    rows = cats_entries(db)
    return _collection_response(
        request, if_none_match, "CatsEntries", rows, _query_params(request),
    )
