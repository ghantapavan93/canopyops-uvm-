"""Evidence upload pipeline — real object storage with presigned URLs.

The production-shaped flow, so a failed upload is a first-class, recoverable state:

  1. POST /evidence/{id}/upload-url  → validate type + size, return a presigned
     PUT URL (bytes go client → storage directly; the API never proxies the file).
  2. client PUTs the file straight to object storage.
  3. POST /evidence/{id}/finalize    → the server HEADs the object; if it's there
     (and the declared size matches) it records the checksum + marks STORED; if
     it's missing / mismatched it marks FAILED — a partial upload, retryable by
     requesting a fresh URL.

Uploads carry their own (stricter) per-client rate limit.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ratelimit import RateLimiter
from app.core.security import require_roles
from app.core.storage import get_storage
from app.models import domain as m
from app.models import enums as e
from app.schemas import EvidenceStatusOut, FinalizeIn, UploadUrlIn, UploadUrlOut

router = APIRouter(prefix="/evidence", tags=["evidence"])

_CREW_OR_MANAGER = require_roles(e.Role.FIELD_CREW, e.Role.PROGRAM_MANAGER)

_settings = get_settings()
_ALLOWED = {t.strip() for t in _settings.evidence_allowed_types.split(",") if t.strip()}
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
_upload_limiter = RateLimiter(
    capacity=_settings.upload_rate_burst,
    refill_per_sec=_settings.upload_rate_per_min / 60.0,
)


def _client_key(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _load(db: Session, evidence_id: str) -> m.EvidenceItem:
    ev = db.get(m.EvidenceItem, evidence_id)
    if ev is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Evidence not found"})
    return ev


@router.post("/{evidence_id}/upload-url", response_model=UploadUrlOut)
def create_upload_url(
    evidence_id: str,
    payload: UploadUrlIn,
    request: Request,
    db: Session = Depends(get_db),
    user: m.User = Depends(_CREW_OR_MANAGER),
) -> UploadUrlOut:
    # stricter per-client upload throttle
    allowed, retry = _upload_limiter.check(_client_key(request))
    if not allowed:
        raise HTTPException(status_code=429, detail={
            "code": "upload_rate_limited",
            "message": "Too many upload requests. Slow down and retry.",
        }, headers={"Retry-After": str(max(1, int(retry)))})

    if payload.content_type not in _ALLOWED:
        raise HTTPException(status_code=422, detail={
            "code": "unsupported_type",
            "message": f"content_type must be one of {sorted(_ALLOWED)}",
        })
    if not (0 < payload.size_bytes <= _settings.evidence_max_bytes):
        raise HTTPException(status_code=422, detail={
            "code": "invalid_size",
            "message": f"size_bytes must be 1..{_settings.evidence_max_bytes}",
        })

    ev = _load(db, evidence_id)
    ext = _EXT.get(payload.content_type, "bin")
    key = f"evidence/{ev.execution_id}/{ev.id}.{ext}"
    url = get_storage().presigned_put_url(key, payload.content_type, _settings.storage_url_expiry_s)

    # the object isn't there yet — the item is pending until finalize verifies it
    ev.storage_key = key
    ev.upload_status = e.UploadStatus.PENDING
    ev.checksum = None
    db.commit()

    return UploadUrlOut(
        evidence_id=ev.id, upload_url=url, storage_key=key,
        expires_seconds=_settings.storage_url_expiry_s, max_bytes=_settings.evidence_max_bytes,
    )


@router.post("/{evidence_id}/finalize", response_model=EvidenceStatusOut)
def finalize_upload(
    evidence_id: str,
    payload: FinalizeIn,
    db: Session = Depends(get_db),
    user: m.User = Depends(_CREW_OR_MANAGER),
) -> EvidenceStatusOut:
    ev = _load(db, evidence_id)
    if not ev.storage_key:
        raise HTTPException(status_code=409, detail={
            "code": "no_upload", "message": "Request an upload URL before finalizing.",
        })

    storage = get_storage()
    exists, size = storage.head(ev.storage_key)
    if not exists:
        # partial / failed upload — leave it recoverable (request a fresh URL)
        ev.upload_status = e.UploadStatus.FAILED
        db.add(m.AuditEvent(
            actor_id=user.id, action="evidence.upload_failed", entity_type="evidence_item",
            entity_id=ev.id, after={"reason": "object_missing"},
        ))
        db.commit()
        return EvidenceStatusOut(
            id=ev.id, type=ev.type, upload_status=ev.upload_status,
            storage_key=ev.storage_key, checksum=None,
            message="Object not found in storage — the upload did not complete. Request a new URL and retry.",
        )
    if payload.size_bytes is not None and payload.size_bytes != size:
        ev.upload_status = e.UploadStatus.FAILED
        db.commit()
        return EvidenceStatusOut(
            id=ev.id, type=ev.type, upload_status=ev.upload_status,
            storage_key=ev.storage_key, checksum=None,
            message=f"Size mismatch (declared {payload.size_bytes}, stored {size}) — retry the upload.",
        )

    ev.upload_status = e.UploadStatus.STORED
    ev.checksum = payload.checksum
    db.add(m.AuditEvent(
        actor_id=user.id, action="evidence.upload_recovered", entity_type="evidence_item",
        entity_id=ev.id, after={"upload_status": "stored", "bytes": size},
    ))
    db.commit()

    return EvidenceStatusOut(
        id=ev.id, type=ev.type, upload_status=ev.upload_status,
        storage_key=ev.storage_key, checksum=ev.checksum,
        download_url=storage.presigned_get_url(ev.storage_key, _settings.storage_url_expiry_s),
        message="Stored and verified.",
    )
