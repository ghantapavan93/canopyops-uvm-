"""Synthetic seed data.

Everything here is invented. No real utility, circuit, worker, or location is
represented. Coordinates are placed in an arbitrary synthetic sandbox grid and
are not tied to any actual Davey site.

Run:  python -m app.seed        (idempotent-ish: clears domain tables first)
"""
from __future__ import annotations

from datetime import timedelta

from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry import shape as to_geom  # noqa: F401
from sqlalchemy import delete

from app.core.database import AdminSessionLocal, admin_engine, Base
from app.core.security import hash_password
from app.core.tenancy import DEFAULT_TENANT, reset_current_tenant, set_current_tenant
from app.models import domain as m
from app.models import enums as e
from app.models.domain import _now

# Synthetic sandbox origin (NOT a real location).
LON0, LAT0 = -83.20, 40.10


def box(cx: float, cy: float, w: float, h: float) -> Polygon:
    return Polygon(
        [(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h)]
    )


def geom(shape):
    return from_shape(shape, srid=4326)


def clear(db) -> None:
    for table in (
        m.Job, m.QualityAudit, m.RiskReview, m.AuditEvent, m.SyncAttempt, m.VerificationObservation,
        m.EvidenceItem, m.TreatmentExecution, m.TreatmentPlan, m.WorkOrder,
        m.EnvironmentalConstraint, m.Corridor, m.User, m.Tenant,
    ):
        db.execute(delete(table))
    db.commit()


# --- The golden record ----------------------------------------------------
# WO-2026-0142 is the demonstration's anchor: ONE record that every module can
# tell its own chapter of, instead of fifteen screens showing fifteen unrelated
# rows. It is deliberately parked at the most interesting moment in the
# lifecycle — executed, evidence INCOMPLETE (a photo upload failed), awaiting a
# human verdict — because that is where the product's actual claim lives:
# the work is recorded, and it is still not verified.
#
# Nothing here is faked into a "done" state: the coverage number is computed
# from real geometry by the same PostGIS/shapely path the app uses, and the
# failed photo is a real FAILED upload_status that the evidence gate reads.
GOLDEN_REF = "WO-2026-0142"


def _seed_golden_record(db, users, corridors, events) -> None:
    """Seed the demo's anchor record. See GOLDEN_REF above for why it exists."""
    corridor = corridors[2]  # CKT-8842 — the water-buffer corridor

    # Planned area was reduced after the riparian buffer was detected. The plan
    # is at revision 3 because of that adjustment — the Treatment Plan and
    # Verification screens both surface the revision, and the audit trail below
    # explains WHY it moved rather than just that it did.
    planned = box(LON0 + 0.030, LAT0 + 0.0065, 0.0040, 0.0026)
    # What the crew actually treated: full width, but short of plan along the
    # south edge. Sized so the REAL computed coverage lands at ~86.8% — the
    # number is derived from this geometry, never written into the record.
    actual = box(LON0 + 0.030, LAT0 + 0.0065 + 0.000343, 0.0040, 0.002257)
    coverage = round(planned.intersection(actual).area / planned.area, 4)

    wo = m.WorkOrder(
        reference=GOLDEN_REF,
        priority=e.WorkOrderPriority.HAZARD,
        corridor_id=corridor.id,
        owner_id=users["manager"].id,
        due_at=_now() + timedelta(days=3),
    )
    db.add(wo)
    db.flush()

    plan = m.TreatmentPlan(
        work_order_id=wo.id,
        status=e.TreatmentStatus.AWAITING_VERIFICATION,
        planned_geometry=geom(planned),
        target_condition=(
            "Restore MVCD clearance and establish low-growing compatible cover; "
            "planned area reduced from 7.4 to 6.8 acres to hold the riparian buffer."
        ),
        method_category=e.MethodCategory.MECHANICAL,
        required_evidence=[
            e.EvidenceType.PHOTO_BEFORE.value,
            e.EvidenceType.PHOTO_AFTER.value,
            e.EvidenceType.CLEARANCE_MEASUREMENT.value,
        ],
        verification_policy={"window_days": 30, "cycle": "mid_cycle"},
        owner_id=users["manager"].id,
        revision=3,
    )
    db.add(plan)
    db.flush()

    execution = m.TreatmentExecution(
        plan_id=plan.id,
        actual_geometry=geom(actual),
        performed_at=_now() - timedelta(days=2),
        crew_id=users["crew"].id,
        constraint_acknowledged=True,
        coverage_ratio=coverage,
        notes="Recorded offline at the span; synced on return to coverage.",
    )
    db.add(execution)
    db.flush()

    # THE POINT OF THE WHOLE PRODUCT: the after-photo never made it to storage,
    # so this record is "worked" but NOT verifiable. The evidence gate reads this
    # FAILED status and refuses to call the outcome complete.
    for et, status in (
        (e.EvidenceType.PHOTO_BEFORE, e.UploadStatus.STORED),
        (e.EvidenceType.PHOTO_AFTER, e.UploadStatus.FAILED),
        (e.EvidenceType.CLEARANCE_MEASUREMENT, e.UploadStatus.STORED),
    ):
        stored = status is e.UploadStatus.STORED
        db.add(m.EvidenceItem(
            execution_id=execution.id, type=et, upload_status=status,
            storage_key=f"synthetic/golden/{plan.id}/{et.value}" if stored else None,
            captured_at=execution.performed_at,
        ))

    events["created"].append(("plan.created", plan.id, users["manager"].id))
    events["approved"].append(("plan.approved", plan.id, users["manager"].id))
    events["executed"].append(("execution.recorded", plan.id, users["crew"].id))

    # A trail a reviewer can actually read the story from.
    for action, reason in (
        ("plan.constraint_detected",
         "Riparian water buffer (Mill Branch) intersects the planned area — PostGIS ST_Intersects."),
        ("plan.revised",
         "Planned area reduced 7.4 → 6.8 acres to hold the riparian buffer. Revision 2 → 3."),
        ("evidence.failed",
         "photo_after upload failed on sync; outcome cannot be verified until it is recovered."),
    ):
        db.add(m.AuditEvent(
            actor_id=users["manager"].id if action.startswith("plan") else users["crew"].id,
            action=action, entity_type="treatment_plan", entity_id=plan.id,
            reason=reason, created_at=_now() - timedelta(days=2),
        ))


def seed() -> dict:
    """Rebuild the synthetic demonstration data. Returns the row counts."""
    Base.metadata.create_all(admin_engine)  # safety net if migrations skipped
    db = AdminSessionLocal()
    tenant_token = None
    try:
        clear(db)

        # --- Tenants (programs / utility clients) ---
        db.add_all([
            m.Tenant(id=DEFAULT_TENANT, name="CanopyOps Demo Utility"),
            m.Tenant(id="northgrid", name="NorthGrid Power (isolation demo)"),
        ])
        db.flush()

        # Everything below is stamped to the demo program by the tenant guard.
        tenant_token = set_current_tenant(DEFAULT_TENANT)

        # --- Users (one per RBAC role) ---
        pw = hash_password("canopyops")
        users = {
            "manager": m.User(tenant_id=DEFAULT_TENANT, email="manager@synthetic.test", display_name="Morgan Reyes (Program Manager)", role=e.Role.PROGRAM_MANAGER, password_hash=pw),
            "crew": m.User(tenant_id=DEFAULT_TENANT, email="crew@synthetic.test", display_name="Casey Lin (Field Crew)", role=e.Role.FIELD_CREW, password_hash=pw),
            "reviewer": m.User(tenant_id=DEFAULT_TENANT, email="reviewer@synthetic.test", display_name="Avery Stone (ISA Arborist / QA)", role=e.Role.QUALITY_REVIEWER, password_hash=pw),
            "compliance": m.User(tenant_id=DEFAULT_TENANT, email="compliance@synthetic.test", display_name="Jordan Diaz (Compliance)", role=e.Role.COMPLIANCE_REVIEWER, password_hash=pw),
        }
        db.add_all(users.values())
        db.flush()

        # --- Environmental constraints (spatial) ---
        constraints = [
            m.EnvironmentalConstraint(name="Riparian water buffer — Mill Branch (synthetic)", category=e.ConstraintCategory.WATER_BUFFER, severity=e.ConstraintSeverity.BLOCKING, geometry=geom(box(LON0 + 0.030, LAT0 + 0.012, 0.010, 0.004)), source="synthetic"),
            m.EnvironmentalConstraint(name="Migratory nesting window (Apr–Jul, synthetic)", category=e.ConstraintCategory.HABITAT, severity=e.ConstraintSeverity.ADVISORY, geometry=geom(box(LON0 + 0.052, LAT0 + 0.030, 0.008, 0.006)), effective_start=_now() - timedelta(days=60), effective_end=_now() + timedelta(days=20), source="synthetic"),
            m.EnvironmentalConstraint(name="High Fire-Threat District segment (synthetic)", category=e.ConstraintCategory.HFTD, severity=e.ConstraintSeverity.ADVISORY, geometry=geom(box(LON0 + 0.070, LAT0 + 0.004, 0.014, 0.010)), source="synthetic"),
        ]
        db.add_all(constraints)

        # --- Corridors (circuit + span) with centerlines ---
        corridors = []
        for i in range(6):
            cx = LON0 + i * 0.014
            centerline = LineString([(cx, LAT0), (cx + 0.010, LAT0 + 0.006)])
            corridors.append(
                m.Corridor(
                    circuit_id=f"CKT-88{40 + i}",
                    span_label=f"SPAN {10 + i}-{11 + i}",
                    name=f"Synthetic ROW corridor {i + 1}",
                    voltage_kv=69 if i % 2 == 0 else 138,
                    centerline=geom(centerline),
                )
            )
        # A ridge-crossing span for the 3D-terrain / slope demo: its centerline
        # climbs the synthetic escarpment, so its elevation profile shows a steep
        # (>30%) section — where access and fall-protection planning matter. No
        # treatment plan is attached (the lifecycle loop below covers the first 6).
        ridge_line = LineString([(-83.1304, 40.109), (-83.1304, 40.145)])
        corridors.append(
            m.Corridor(
                circuit_id="CKT-8848",
                span_label="RIDGE CROSSING",
                name="Ridge-crossing ROW (steep-grade demo)",
                voltage_kv=138,
                centerline=geom(ridge_line),
            )
        )

        db.add_all(corridors)
        db.flush()

        # --- Work orders + treatment plans across the lifecycle ---
        lifecycle = [
            (e.TreatmentStatus.SCHEDULED, e.WorkOrderPriority.ROUTINE),
            (e.TreatmentStatus.AWAITING_VERIFICATION, e.WorkOrderPriority.ELEVATED),
            (e.TreatmentStatus.APPLIED, e.WorkOrderPriority.HAZARD),
            (e.TreatmentStatus.PARTIALLY_EFFECTIVE, e.WorkOrderPriority.ELEVATED),
            (e.TreatmentStatus.DRAFT, e.WorkOrderPriority.ROUTINE),
            (e.TreatmentStatus.FOLLOW_UP_PLANNED, e.WorkOrderPriority.HAZARD),
        ]
        # Business events accumulate here in lifecycle phase order (created →
        # approved → executed → verified), then get realistic recent timestamps
        # so the Program Overview's live activity feed reflects real history.
        events: dict[str, list[tuple[str, str, str]]] = {
            "created": [], "approved": [], "executed": [], "verified": [],
        }

        for i, (status, priority) in enumerate(lifecycle):
            corridor = corridors[i]
            cx = LON0 + i * 0.014 + 0.005
            wo = m.WorkOrder(
                reference=f"WO-2026-{1001 + i}",
                priority=priority,
                corridor_id=corridor.id,
                owner_id=users["manager"].id,
                due_at=_now() + timedelta(days=7 + i),
            )
            db.add(wo)
            db.flush()
            plan = m.TreatmentPlan(
                work_order_id=wo.id,
                status=status,
                planned_geometry=geom(box(cx, LAT0 + 0.003, 0.004, 0.0025)),
                target_condition="Restore MVCD clearance; establish low-growing compatible cover in wire zone.",
                method_category=e.MethodCategory.MECHANICAL if i % 2 == 0 else e.MethodCategory.HERBICIDE,
                required_evidence=[
                    e.EvidenceType.PHOTO_BEFORE.value,
                    e.EvidenceType.PHOTO_AFTER.value,
                    e.EvidenceType.CLEARANCE_MEASUREMENT.value,
                ],
                verification_policy={"window_days": 30, "cycle": "mid_cycle"},
                owner_id=users["manager"].id,
            )
            db.add(plan)
            db.flush()

            events["created"].append(("plan.created", plan.id, users["manager"].id))
            if status is not e.TreatmentStatus.DRAFT:
                events["approved"].append(("plan.approved", plan.id, users["manager"].id))

            # Give already-progressed plans a real execution + complete evidence
            # so the verification queue and coverage signals are meaningful.
            if status in (
                e.TreatmentStatus.AWAITING_VERIFICATION,
                e.TreatmentStatus.PARTIALLY_EFFECTIVE,
                e.TreatmentStatus.FOLLOW_UP_PLANNED,
            ):
                planned = box(cx, LAT0 + 0.003, 0.004, 0.0025)
                actual = box(cx, LAT0 + 0.003, 0.0032, 0.0021)  # ~partial coverage
                cov = round(planned.intersection(actual).area / planned.area, 4)
                execution = m.TreatmentExecution(
                    plan_id=plan.id,
                    actual_geometry=geom(actual),
                    performed_at=_now() - timedelta(days=20 - i),
                    crew_id=users["crew"].id,
                    constraint_acknowledged=True,
                    coverage_ratio=cov,
                )
                db.add(execution)
                db.flush()
                events["executed"].append(("execution.recorded", plan.id, users["crew"].id))
                if status in (e.TreatmentStatus.PARTIALLY_EFFECTIVE, e.TreatmentStatus.FOLLOW_UP_PLANNED):
                    events["verified"].append(("verification.recorded", plan.id, users["reviewer"].id))
                for et in (
                    e.EvidenceType.PHOTO_BEFORE,
                    e.EvidenceType.PHOTO_AFTER,
                    e.EvidenceType.CLEARANCE_MEASUREMENT,
                ):
                    db.add(m.EvidenceItem(
                        execution_id=execution.id, type=et,
                        upload_status=e.UploadStatus.STORED,
                        storage_key=f"synthetic/seed/{plan.id}/{et.value}",
                        captured_at=execution.performed_at,
                    ))

        _seed_golden_record(db, users, corridors, events)

        # Flatten in chronological phase order and stamp with recent, spaced
        # timestamps so the feed reads naturally (oldest ~4h ago → newest ~now).
        ordered = (
            events["created"] + events["approved"]
            + events["executed"] + events["verified"]
        )
        total_ev = len(ordered) or 1
        for idx, (action, entity_id, actor_id) in enumerate(ordered):
            minutes_ago = int((total_ev - idx) * (240 / total_ev))
            db.add(m.AuditEvent(
                actor_id=actor_id,
                action=action,
                entity_type="treatment_plan",
                entity_id=entity_id,
                reason="Synthetic seed history",
                created_at=_now() - timedelta(minutes=minutes_ago),
            ))

        db.commit()

        # --- Second program (NorthGrid): a minimal, fully isolated dataset. Its
        #     users/corridors/plans must never surface for the demo program. ---
        reset_current_tenant(tenant_token)
        tenant_token = set_current_tenant("northgrid")
        ng_mgr = m.User(tenant_id="northgrid", email="ng.manager@synthetic.test",
                        display_name="Riley Fox (NorthGrid PM)", role=e.Role.PROGRAM_MANAGER, password_hash=pw)
        db.add(ng_mgr)
        db.flush()
        ng_corr = m.Corridor(circuit_id="NG-1201", span_label="SPAN 4-5",
                             name="NorthGrid ROW (synthetic)", voltage_kv=115,
                             centerline=geom(LineString([(-83.30, 40.20), (-83.29, 40.206)])))
        db.add(ng_corr)
        db.flush()
        ng_wo = m.WorkOrder(reference="NG-2026-0001", priority=e.WorkOrderPriority.ELEVATED,
                            corridor_id=ng_corr.id, owner_id=ng_mgr.id)
        db.add(ng_wo)
        db.flush()
        db.add(m.TreatmentPlan(
            work_order_id=ng_wo.id, status=e.TreatmentStatus.AWAITING_VERIFICATION,
            planned_geometry=geom(box(-83.295, 40.203, 0.004, 0.0025)),
            target_condition="Restore MVCD clearance (NorthGrid synthetic).",
            method_category=e.MethodCategory.MECHANICAL,
            required_evidence=[e.EvidenceType.PHOTO_BEFORE.value, e.EvidenceType.PHOTO_AFTER.value],
            verification_policy={"window_days": 30}, owner_id=ng_mgr.id,
        ))
        db.commit()
        reset_current_tenant(tenant_token)
        tenant_token = None

        counts = {
            "tenants": db.query(m.Tenant).count(),
            "users": db.query(m.User).count(),
            "corridors": db.query(m.Corridor).count(),
            "constraints": db.query(m.EnvironmentalConstraint).count(),
            "work_orders": db.query(m.WorkOrder).count(),
            "plans": db.query(m.TreatmentPlan).count(),
        }
        print(f"[seed] done: {counts}")
        return counts
    finally:
        if tenant_token is not None:
            reset_current_tenant(tenant_token)
        db.close()


if __name__ == "__main__":
    seed()
