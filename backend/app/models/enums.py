"""Domain enumerations.

Vocabulary is deliberately drawn from real Utility Vegetation Management (UVM)
practice so the model reads as domain-true to a reviewer: circuits, spans,
rights-of-way, prescriptions, MVCD, wire/border zones, cycle vs. mid-cycle.
"""
import enum


class Role(str, enum.Enum):
    """Server-enforced RBAC roles. Mirror real UVM program roles."""

    PROGRAM_MANAGER = "program_manager"      # ROW / vegetation program manager
    FIELD_CREW = "field_crew"                # crew member / applicator
    QUALITY_REVIEWER = "quality_reviewer"    # arborist / CUF auditor
    COMPLIANCE_REVIEWER = "compliance_reviewer"  # environmental / compliance


class TreatmentStatus(str, enum.Enum):
    """The treatment lifecycle state machine (blueprint §08).

    DRAFT -> SCHEDULED -> IN_PROGRESS -> APPLIED -> AWAITING_VERIFICATION
    -> EFFECTIVE | PARTIALLY_EFFECTIVE | INEFFECTIVE | INCONCLUSIVE
    -> FOLLOW_UP_PLANNED -> CLOSED
    """

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    APPLIED = "applied"
    AWAITING_VERIFICATION = "awaiting_verification"
    EFFECTIVE = "effective"
    PARTIALLY_EFFECTIVE = "partially_effective"
    INEFFECTIVE = "ineffective"
    INCONCLUSIVE = "inconclusive"
    FOLLOW_UP_PLANNED = "follow_up_planned"
    CLOSED = "closed"


# Allowed forward transitions. Enforced server-side; the UI must not be the only
# guard. Terminal outcome states may fan into follow-up or close.
ALLOWED_TRANSITIONS: dict[TreatmentStatus, set[TreatmentStatus]] = {
    TreatmentStatus.DRAFT: {TreatmentStatus.SCHEDULED},
    TreatmentStatus.SCHEDULED: {TreatmentStatus.IN_PROGRESS},
    TreatmentStatus.IN_PROGRESS: {TreatmentStatus.APPLIED},
    TreatmentStatus.APPLIED: {TreatmentStatus.AWAITING_VERIFICATION},
    TreatmentStatus.AWAITING_VERIFICATION: {
        TreatmentStatus.EFFECTIVE,
        TreatmentStatus.PARTIALLY_EFFECTIVE,
        TreatmentStatus.INEFFECTIVE,
        TreatmentStatus.INCONCLUSIVE,
    },
    TreatmentStatus.EFFECTIVE: {TreatmentStatus.CLOSED},
    TreatmentStatus.PARTIALLY_EFFECTIVE: {
        TreatmentStatus.FOLLOW_UP_PLANNED,
        TreatmentStatus.CLOSED,
    },
    TreatmentStatus.INEFFECTIVE: {
        TreatmentStatus.FOLLOW_UP_PLANNED,
        TreatmentStatus.CLOSED,
    },
    TreatmentStatus.INCONCLUSIVE: {
        TreatmentStatus.FOLLOW_UP_PLANNED,
        TreatmentStatus.CLOSED,
    },
    TreatmentStatus.FOLLOW_UP_PLANNED: {TreatmentStatus.CLOSED},
    TreatmentStatus.CLOSED: set(),
}


class MethodCategory(str, enum.Enum):
    """IVM intervention categories (ANSI A300 Part 7 vocabulary).

    Categories only — the system deliberately does NOT prescribe products,
    rates, or mixing instructions.
    """

    MANUAL = "manual"            # hand cutting / pruning
    MECHANICAL = "mechanical"    # mowing / side-trimming
    HERBICIDE = "herbicide"      # foliar / basal / cut-stump (category, not product)
    BIOLOGICAL = "biological"
    CULTURAL = "cultural"        # compatible-cover establishment


class WorkOrderPriority(str, enum.Enum):
    ROUTINE = "routine"
    ELEVATED = "elevated"
    HAZARD = "hazard"            # hazard tree / imminent clearance risk


class ConstraintCategory(str, enum.Enum):
    WATER_BUFFER = "water_buffer"
    HABITAT = "habitat"                 # e.g. nesting window
    STEEP_SLOPE = "steep_slope"
    NO_WORK_ZONE = "no_work_zone"
    ACCESS_RESTRICTED = "access_restricted"
    HFTD = "hftd"                       # high fire-threat district


class ConstraintSeverity(str, enum.Enum):
    ADVISORY = "advisory"
    BLOCKING = "blocking"


class EvidenceType(str, enum.Enum):
    PHOTO_BEFORE = "photo_before"
    PHOTO_AFTER = "photo_after"
    CLEARANCE_MEASUREMENT = "clearance_measurement"  # MVCD reading
    NOTE = "note"
    FORM = "form"


class UploadStatus(str, enum.Enum):
    PENDING = "pending"       # queued locally, not yet sent
    UPLOADING = "uploading"
    STORED = "stored"
    FAILED = "failed"


class VerificationConclusion(str, enum.Enum):
    EFFECTIVE = "effective"
    PARTIALLY_EFFECTIVE = "partially_effective"
    INEFFECTIVE = "ineffective"
    INCONCLUSIVE = "inconclusive"


class SyncStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"          # idempotency key already applied
    CONFLICT = "conflict"            # stale revision, needs human resolution
    REJECTED = "rejected"
