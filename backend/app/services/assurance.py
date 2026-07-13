"""Assurance signals — the logic that makes the CanopyOps thesis visible.

'Closed is not the same as effective.' These deterministic functions turn raw
records into the signals the Command Center ranks on: evidence completeness,
planned-vs-actual coverage, and verification debt. No AI verdicts — every
conclusion remains human-authored and evidence-linked.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import domain as m
from app.models import enums as e


def evidence_score(plan: m.TreatmentPlan) -> tuple[float, bool]:
    """Fraction of the plan's REQUIRED evidence that is actually stored.

    A failed or pending upload does not count — so an incomplete or failed
    evidence set can never report as complete. Returns (score 0..1, complete?).
    """
    required = {str(t) for t in (plan.required_evidence or [])}
    if not required:
        return 1.0, True
    execution = plan.execution
    stored: set[str] = set()
    if execution:
        for item in execution.evidence:
            if item.upload_status == e.UploadStatus.STORED:
                stored.add(item.type.value)
    have = len(required & stored)
    score = round(have / len(required), 4)
    return score, have == len(required)


def verification_due_at(plan: m.TreatmentPlan) -> datetime | None:
    """When follow-up verification is due, per the plan's verification policy."""
    policy = plan.verification_policy or {}
    window = policy.get("window_days")
    if window is None:
        return None
    anchor = plan.updated_at or plan.created_at
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return anchor + timedelta(days=int(window))


def is_verification_overdue(plan: m.TreatmentPlan) -> bool:
    """True only while a record is awaiting verification past its window.

    Overdue records surface in the verification-debt queue rather than being
    silently closed.
    """
    if plan.status != e.TreatmentStatus.AWAITING_VERIFICATION:
        return False
    due = verification_due_at(plan)
    return due is not None and datetime.now(timezone.utc) > due
