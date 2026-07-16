"""Tenant / program isolation. Every program-owned row is auto-scoped by the
Session-level filter, driven by the JWT's tenant claim. A user in one program
can never see or fetch another program's data — enforced at the data-access
layer, not just the UI."""
from __future__ import annotations

from sqlalchemy import text

from app.core.database import AdminSessionLocal, SessionLocal
from app.core.tenancy import reset_current_tenant, set_current_tenant
from app.models import domain as m
from tests.conftest import auth


def test_work_order_reference_is_unique_per_program(client):
    """The reference generator counts a program's OWN work orders, so the
    reference must be unique per program, not globally — two programs must be
    able to hold the same reference without a unique violation."""
    with AdminSessionLocal() as db:
        demo_cor = db.execute(text("SELECT id FROM corridor WHERE tenant_id='demo' LIMIT 1")).scalar()
        ng_cor = db.execute(text("SELECT id FROM corridor WHERE tenant_id='northgrid' LIMIT 1")).scalar()
        db.add(m.WorkOrder(tenant_id="demo", reference="WO-DUP-9", corridor_id=demo_cor))
        db.add(m.WorkOrder(tenant_id="northgrid", reference="WO-DUP-9", corridor_id=ng_cor))
        db.commit()   # must NOT raise IntegrityError (per-program uniqueness)


def test_login_returns_tenant(client):
    demo = client.post("/api/auth/token",
                       data={"username": "manager@synthetic.test", "password": "canopyops"}).json()
    assert demo["user"]["tenantId"] == "demo"
    assert demo["user"]["tenantName"]

    ng = client.post("/api/auth/token",
                     data={"username": "ng.manager@synthetic.test", "password": "canopyops"}).json()
    assert ng["user"]["tenantId"] == "northgrid"


def test_default_program_sees_demo_not_northgrid(client):
    # unauthenticated resolves to the default (demo) program
    circuits = [c["circuitId"] for c in client.get("/api/corridors").json()]
    assert any(c.startswith("CKT-") for c in circuits)
    assert "NG-1201" not in circuits


def test_northgrid_user_sees_only_its_own_corridors(client):
    hdr = auth(client, "ng.manager@synthetic.test")
    circuits = [c["circuitId"] for c in client.get("/api/corridors", headers=hdr).json()]
    assert circuits == ["NG-1201"]
    assert not any(c.startswith("CKT-") for c in circuits)


def test_demo_user_cannot_read_a_northgrid_plan(client):
    ng = auth(client, "ng.manager@synthetic.test")
    ng_plan_id = client.get("/api/treatments", headers=ng).json()[0]["planId"]

    # the plan simply doesn't exist for the demo program → 404 (not 403)
    demo = auth(client, "manager@synthetic.test")
    assert client.get(f"/api/treatments/{ng_plan_id}", headers=demo).status_code == 404
    # but its own program can read it
    assert client.get(f"/api/treatments/{ng_plan_id}", headers=ng).status_code == 200


def test_lists_are_disjoint_across_programs(client):
    demo_ids = {t["planId"] for t in client.get("/api/treatments",
                headers=auth(client, "manager@synthetic.test")).json()}
    ng_ids = {t["planId"] for t in client.get("/api/treatments",
              headers=auth(client, "ng.manager@synthetic.test")).json()}
    assert demo_ids and ng_ids
    assert demo_ids.isdisjoint(ng_ids)


def test_new_rows_are_stamped_with_the_creators_program(client):
    # a plan created via the API under the demo token is invisible to northgrid
    mgr = auth(client, "manager@synthetic.test")
    corridor_id = client.get("/api/corridors", headers=mgr).json()[0]["id"]
    created = client.post("/api/plans", json={
        "corridorId": corridor_id,
        "methodCategory": "mechanical",
        "targetCondition": "tenant-stamp test",
        "plannedGeometry": {"type": "Polygon", "coordinates": [[[-83.2, 40.1], [-83.19, 40.1], [-83.19, 40.11], [-83.2, 40.11], [-83.2, 40.1]]]},
        "priority": "routine",
        "requiredEvidence": ["photo_before"],
    }, headers=mgr)
    assert created.status_code in (200, 201), created.text
    new_id = created.json()["planId"]
    # northgrid can't see it
    assert client.get(f"/api/treatments/{new_id}",
                      headers=auth(client, "ng.manager@synthetic.test")).status_code == 404


def test_rls_enforced_at_the_database_even_for_raw_sql(client):
    """The DATABASE enforces isolation, not just the ORM filter: a raw SQL count
    (which the app-layer ``with_loader_criteria`` never touches) still returns
    only the current program's rows, because Postgres Row-Level Security applies
    to the non-superuser app role. If the app connects as a superuser this test
    fails — which is exactly the point."""
    # superuser (admin) sees every program's plans — RLS is bypassed for it
    with AdminSessionLocal() as adb:
        total = adb.execute(text("SELECT count(*) FROM treatment_plan")).scalar()

    # the app role, scoped to northgrid, sees only northgrid's — enforced by the DB
    token = set_current_tenant("northgrid")
    try:
        with SessionLocal() as db:
            scoped = db.execute(text("SELECT count(*) FROM treatment_plan")).scalar()
    finally:
        reset_current_tenant(token)

    assert scoped == 1, "RLS should hide every other program's plans from a raw query"
    assert total > scoped, "more plans exist across programs, invisible to the scoped role"
