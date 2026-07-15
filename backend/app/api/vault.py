"""Compliance evidence vault endpoints — the auto-assembled documentation dossier.

Read-only: gathers the full evidence chain per plan and maps it to the frameworks
a utility answers to (NERC FAC-003 / TVMP, NESC, environmental, QA). See
services/vault.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import PlanDossier, VaultIndex
from app.services import vault as vault_svc

router = APIRouter(prefix="/vault", tags=["compliance vault"])

_NOTE = (
    "Evidence dossiers are assembled from the live record chain — prescription, "
    "execution, evidence integrity, verification, risk sign-off, QA audit, and "
    "constraint acknowledgement — mapped to NERC FAC-003 / TVMP / NESC / "
    "environmental requirements. Illustrative; synthetic data, not a filing."
)


@router.get("", response_model=VaultIndex)
def index(db: Session = Depends(get_db)) -> VaultIndex:
    data = vault_svc.vault_index(db)
    return VaultIndex(
        generated_at=datetime.now(timezone.utc),
        note=_NOTE,
        summary=data["summary"],
        plans=data["plans"],
    )


@router.get("/plans/{plan_id}", response_model=PlanDossier)
def dossier(plan_id: str, db: Session = Depends(get_db)) -> PlanDossier:
    d = vault_svc.one_dossier(db, plan_id)
    if d is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Plan not found"})
    return d
