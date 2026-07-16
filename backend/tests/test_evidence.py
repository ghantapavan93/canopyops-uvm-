"""Evidence object-storage pipeline (memory backend): validate type/size →
presigned URL → finalize verifies the object exists → STORED, or FAILED (partial
upload) which is recoverable. Uploads are rate-limited."""
from __future__ import annotations

from app.core.database import AdminSessionLocal
from app.core.ratelimit import RateLimiter
from app.core.storage import get_storage
from app.models import domain as m
from app.models import enums as e
from tests.conftest import auth


def _evidence_id(client) -> str:
    """An evidence id, reset to a not-yet-uploaded (PENDING) state so the upload
    flow is exercisable — seeded evidence is STORED (immutable) by design."""
    for item in client.get("/api/audit/queue").json()["items"]:
        proof = client.get(f"/api/plans/{item['planId']}/proof").json()
        if proof.get("evidence"):
            eid = proof["evidence"][0]["id"]
            with AdminSessionLocal() as db:   # admin bypasses RLS to set up the fixture
                obj = db.get(m.EvidenceItem, eid)
                obj.upload_status = e.UploadStatus.PENDING
                obj.checksum = None
                obj.storage_key = None
                db.commit()
            return eid
    raise AssertionError("no evidence in the seed")


def test_upload_url_validates_type_and_size(client):
    ev = _evidence_id(client)
    hdr = auth(client, "crew@synthetic.test")
    # unsupported content type
    bad = client.post(f"/api/evidence/{ev}/upload-url",
                      json={"content_type": "application/x-msdownload", "size_bytes": 100}, headers=hdr)
    assert bad.status_code == 422
    # zero / oversize
    assert client.post(f"/api/evidence/{ev}/upload-url",
                       json={"content_type": "image/jpeg", "size_bytes": 0}, headers=hdr).status_code == 422
    assert client.post(f"/api/evidence/{ev}/upload-url",
                       json={"content_type": "image/jpeg", "size_bytes": 99_000_000}, headers=hdr).status_code == 422


def test_presign_then_upload_then_finalize_stores(client):
    ev = _evidence_id(client)
    hdr = auth(client, "crew@synthetic.test")
    url = client.post(f"/api/evidence/{ev}/upload-url",
                      json={"content_type": "image/jpeg", "size_bytes": 12}, headers=hdr).json()
    assert url["uploadUrl"].startswith("memory://")
    key = url["storageKey"]

    # simulate the client PUTting bytes straight to object storage
    get_storage().put(key, b"JPEGDATA1234")

    done = client.post(f"/api/evidence/{ev}/finalize",
                       json={"checksum": "abc123", "size_bytes": 12}, headers=hdr).json()
    assert done["uploadStatus"] == "stored"
    assert done["checksum"] == "abc123"
    assert done["downloadUrl"]


def test_finalize_without_object_is_failed_and_recoverable(client):
    ev = _evidence_id(client)
    hdr = auth(client, "crew@synthetic.test")
    client.post(f"/api/evidence/{ev}/upload-url",
                json={"content_type": "image/jpeg", "size_bytes": 10}, headers=hdr)

    # finalize before the object exists → partial upload → FAILED
    failed = client.post(f"/api/evidence/{ev}/finalize",
                         json={"checksum": "x"}, headers=hdr).json()
    assert failed["uploadStatus"] == "failed"

    # recovery: a fresh URL, actually upload, finalize → STORED
    key = client.post(f"/api/evidence/{ev}/upload-url",
                      json={"content_type": "image/png", "size_bytes": 5}, headers=hdr).json()["storageKey"]
    get_storage().put(key, b"PNG12")
    ok = client.post(f"/api/evidence/{ev}/finalize",
                     json={"checksum": "y", "size_bytes": 5}, headers=hdr).json()
    assert ok["uploadStatus"] == "stored"


def test_finalize_size_mismatch_fails(client):
    ev = _evidence_id(client)
    hdr = auth(client, "crew@synthetic.test")
    key = client.post(f"/api/evidence/{ev}/upload-url",
                      json={"content_type": "image/jpeg", "size_bytes": 20}, headers=hdr).json()["storageKey"]
    get_storage().put(key, b"only-8-b")   # 8 bytes, but the client will declare 20
    r = client.post(f"/api/evidence/{ev}/finalize",
                    json={"checksum": "z", "size_bytes": 20}, headers=hdr).json()
    assert r["uploadStatus"] == "failed"


def test_upload_url_requires_crew_or_manager(client):
    ev = _evidence_id(client)
    denied = client.post(f"/api/evidence/{ev}/upload-url",
                         json={"content_type": "image/jpeg", "size_bytes": 10},
                         headers=auth(client, "reviewer@synthetic.test"))
    assert denied.status_code == 403


def test_finalize_rejects_oversize_object(client):
    ev = _evidence_id(client)
    hdr = auth(client, "crew@synthetic.test")
    key = client.post(f"/api/evidence/{ev}/upload-url",
                      json={"content_type": "image/jpeg", "size_bytes": 12}, headers=hdr).json()["storageKey"]
    # the presigned URL can't cap content-length: upload a huge object, declare nothing
    get_storage().put(key, b"x" * 20_000_000)   # > 15 MB default limit
    r = client.post(f"/api/evidence/{ev}/finalize", json={"checksum": "abc"}, headers=hdr).json()
    assert r["uploadStatus"] == "failed"          # real stored size is enforced


def test_finalize_is_idempotent_and_checksum_immutable(client):
    ev = _evidence_id(client)
    hdr = auth(client, "crew@synthetic.test")
    key = client.post(f"/api/evidence/{ev}/upload-url",
                      json={"content_type": "image/jpeg", "size_bytes": 4}, headers=hdr).json()["storageKey"]
    get_storage().put(key, b"JPEG")
    first = client.post(f"/api/evidence/{ev}/finalize", json={"checksum": "good"}, headers=hdr).json()
    assert first["uploadStatus"] == "stored" and first["checksum"] == "good"
    # a replay with a DIFFERENT checksum must not overwrite the recorded one
    second = client.post(f"/api/evidence/{ev}/finalize", json={"checksum": "evil"}, headers=hdr).json()
    assert second["uploadStatus"] == "stored" and second["checksum"] == "good"


def test_cannot_reissue_upload_url_for_stored_evidence(client):
    ev = _evidence_id(client)
    hdr = auth(client, "crew@synthetic.test")
    key = client.post(f"/api/evidence/{ev}/upload-url",
                      json={"content_type": "image/jpeg", "size_bytes": 4}, headers=hdr).json()["storageKey"]
    get_storage().put(key, b"JPEG")
    client.post(f"/api/evidence/{ev}/finalize", json={"checksum": "good"}, headers=hdr)
    # verified evidence is immutable — a new upload URL is refused
    denied = client.post(f"/api/evidence/{ev}/upload-url",
                         json={"content_type": "image/jpeg", "size_bytes": 4}, headers=hdr)
    assert denied.status_code == 409


def test_uploads_are_rate_limited(client, monkeypatch):
    from app.api import evidence
    monkeypatch.setattr(evidence, "_upload_limiter", RateLimiter(capacity=2, refill_per_sec=0.001))
    ev = _evidence_id(client)
    hdr = auth(client, "crew@synthetic.test")
    codes = [
        client.post(f"/api/evidence/{ev}/upload-url",
                    json={"content_type": "image/jpeg", "size_bytes": 10}, headers=hdr).status_code
        for _ in range(5)
    ]
    assert 429 in codes
