"""ORM tables. Schema preserves what was intended, what happened, and what was
learned — the three pillars of the CanopyOps thesis (blueprint §08).

All geometry is stored in EPSG:4326 (WGS84 lon/lat) for synthetic GeoJSON.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tenancy import TenantScoped
from app.models import enums


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    """A program / utility client — the isolation boundary. id is a stable slug
    (e.g. "demo", "northgrid") so it can ride in the JWT without a DB lookup."""

    __tablename__ = "tenant"

    id: Mapped[str] = mapped_column(String, primary_key=True)     # slug
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "app_user"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # Users are looked up before the tenant is known (login), so User is NOT
    # auto-scoped; it carries a tenant_id for membership + token minting.
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    role: Mapped[enums.Role] = mapped_column(Enum(enums.Role, name="role"))
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Corridor(TenantScoped, Base):
    """A right-of-way corridor: circuit + span geometry the work applies to."""

    __tablename__ = "corridor"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    circuit_id: Mapped[str] = mapped_column(String, index=True)  # e.g. "CKT-8842"
    span_label: Mapped[str] = mapped_column(String)             # e.g. "SPAN 12-13"
    name: Mapped[str] = mapped_column(String)
    voltage_kv: Mapped[int] = mapped_column(Integer, default=69)
    # ROW centerline; wire/border-zone context lives in the treatment polygon.
    centerline = mapped_column(Geometry("LINESTRING", srid=4326))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    work_orders: Mapped[list[WorkOrder]] = relationship(back_populates="corridor")


class WorkOrder(TenantScoped, Base):
    __tablename__ = "work_order"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    reference: Mapped[str] = mapped_column(String, unique=True, index=True)  # WO-2026-0001
    type: Mapped[str] = mapped_column(String, default="vegetation_maintenance")
    priority: Mapped[enums.WorkOrderPriority] = mapped_column(
        Enum(enums.WorkOrderPriority, name="work_order_priority"),
        default=enums.WorkOrderPriority.ROUTINE,
    )
    corridor_id: Mapped[str] = mapped_column(ForeignKey("corridor.id"))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    corridor: Mapped[Corridor] = relationship(back_populates="work_orders")
    plans: Mapped[list[TreatmentPlan]] = relationship(back_populates="work_order")


class TreatmentPlan(TenantScoped, Base):
    """Approved intent for a defined area (the 'what was intended')."""

    __tablename__ = "treatment_plan"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_order.id"))
    status: Mapped[enums.TreatmentStatus] = mapped_column(
        Enum(enums.TreatmentStatus, name="treatment_status"),
        default=enums.TreatmentStatus.DRAFT,
    )
    # Planned treatment polygon (wire-zone / border-zone footprint).
    planned_geometry = mapped_column(Geometry("POLYGON", srid=4326))
    target_condition: Mapped[str] = mapped_column(Text)  # intended vegetation outcome
    method_category: Mapped[enums.MethodCategory] = mapped_column(
        Enum(enums.MethodCategory, name="method_category")
    )
    # Required evidence set (list of EvidenceType values) — completeness is scored.
    required_evidence: Mapped[list] = mapped_column(JSON, default=list)
    # Verification policy: {"window_days": 30, "cycle": "mid_cycle"}
    verification_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    work_order: Mapped[WorkOrder] = relationship(back_populates="plans")
    execution: Mapped[TreatmentExecution | None] = relationship(
        back_populates="plan", uselist=False
    )
    observations: Mapped[list[VerificationObservation]] = relationship(
        back_populates="plan"
    )


class TreatmentExecution(TenantScoped, Base):
    """Field record of what actually occurred (the 'what happened').

    Carries local_revision (device) and server_revision to power idempotent,
    conflict-aware offline sync.
    """

    __tablename__ = "treatment_execution"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("treatment_plan.id"))
    actual_geometry = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    performed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    crew_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    applicator_record: Mapped[dict] = mapped_column(JSON, default=dict)
    constraint_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Coverage % of planned polygon actually treated — computed via PostGIS.
    coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    local_revision: Mapped[int] = mapped_column(Integer, default=1)
    server_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    plan: Mapped[TreatmentPlan] = relationship(back_populates="execution")
    evidence: Mapped[list[EvidenceItem]] = relationship(back_populates="execution")


class EvidenceItem(TenantScoped, Base):
    """Photo, measurement, note, or form. A failed upload can never mark the
    evidence set complete (invariant enforced by completeness scoring)."""

    __tablename__ = "evidence_item"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("treatment_execution.id"))
    type: Mapped[enums.EvidenceType] = mapped_column(
        Enum(enums.EvidenceType, name="evidence_type")
    )
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)  # opaque key
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    geolocation = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    upload_status: Mapped[enums.UploadStatus] = mapped_column(
        Enum(enums.UploadStatus, name="upload_status"),
        default=enums.UploadStatus.PENDING,
    )
    checksum: Mapped[str | None] = mapped_column(String, nullable=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. MVCD reading payload

    execution: Mapped[TreatmentExecution] = relationship(back_populates="evidence")


class EnvironmentalConstraint(Base):
    """Spatial or procedural restriction shown directly on the map."""

    __tablename__ = "environmental_constraint"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[enums.ConstraintCategory] = mapped_column(
        Enum(enums.ConstraintCategory, name="constraint_category")
    )
    severity: Mapped[enums.ConstraintSeverity] = mapped_column(
        Enum(enums.ConstraintSeverity, name="constraint_severity"),
        default=enums.ConstraintSeverity.ADVISORY,
    )
    geometry = mapped_column(Geometry("POLYGON", srid=4326))
    source: Mapped[str] = mapped_column(String, default="synthetic")
    effective_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class VerificationObservation(TenantScoped, Base):
    """Follow-up result linked to plan geometry (the 'what was learned')."""

    __tablename__ = "verification_observation"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("treatment_plan.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    regrowth_observed: Mapped[bool] = mapped_column(Boolean, default=False)
    compatible_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    # Optional targeted follow-up geometry — only the area needing re-work.
    followup_geometry = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(
        ForeignKey("app_user.id"), nullable=True
    )
    conclusion: Mapped[enums.VerificationConclusion | None] = mapped_column(
        Enum(enums.VerificationConclusion, name="verification_conclusion"),
        nullable=True,
    )

    plan: Mapped[TreatmentPlan] = relationship(back_populates="observations")


class SyncAttempt(TenantScoped, Base):
    """Recoverable transport history for offline mobile mutations."""

    __tablename__ = "sync_attempt"
    __table_args__ = (
        UniqueConstraint("entity_type", "idempotency_key", name="uq_idempotency"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[enums.SyncStatus] = mapped_column(
        Enum(enums.SyncStatus, name="sync_status")
    )
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RiskReview(TenantScoped, Base):
    """A certified human's sign-off on a span's computed risk. Append-only: this
    is the durable evidence that a machine's ranking was reviewed by a person —
    the human-in-the-loop guardrail made into a record, with a snapshot of the
    score the reviewer actually saw."""

    __tablename__ = "risk_review"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("treatment_plan.id"), index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    score: Mapped[float] = mapped_column(Float)          # snapshot the reviewer saw
    level: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String, default="acknowledged")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class QualityAudit(TenantScoped, Base):
    """An independent QA audit of a completed work plan — the "checks and
    balances" second pass. The crew did the work and a verifier confirmed the
    outcome; a *different* certified reviewer audits a sample of closed work
    against objective criteria (coverage, evidence, integrity, verification,
    constraints) and records a verdict. Append-only: the durable proof that
    closed work was independently checked, with a snapshot of the checks seen."""

    __tablename__ = "quality_audit"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("treatment_plan.id"), index=True)
    auditor_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    outcome: Mapped[str] = mapped_column(String)         # pass | conditional | fail
    score: Mapped[float] = mapped_column(Float)          # objective pass ratio 0..1 seen
    checks: Mapped[list] = mapped_column(JSON, default=list)  # snapshot of the criteria
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Job(TenantScoped, Base):
    """A durable background job — the off-request-path task queue. Heavy work
    (Proof Pack generation, large GeoJSON imports, reports) is enqueued here and
    a worker claims it with SELECT ... FOR UPDATE SKIP LOCKED, so the request
    returns immediately and the work survives a restart. Retries with backoff up
    to max_attempts; terminal state is succeeded or failed."""

    __tablename__ = "job"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String, index=True)   # proof_pack | geojson_import
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(TenantScoped, Base):
    """Immutable business history. Never updated or deleted."""

    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String)  # e.g. "plan.approved"
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
