"""Evidence object storage — a swappable adapter over S3-compatible storage.

Photos and documents live in object storage, never in Postgres. The API issues
**presigned** URLs so bytes flow client → storage directly (the API never
proxies the file), and verifies the object exists on finalize (`head`). Two
backends behind one interface:

* ``S3Storage`` — boto3 against MinIO / AWS S3 (presigned PUT/GET, head_object).
* ``MemoryStorage`` — an in-process fake for tests (``put`` simulates the client
  upload), so the whole presign → upload → finalize flow is deterministic
  without a live object store.

The adapter seam means production swaps MinIO for S3/Azure Blob without touching
the evidence endpoints.
"""
from __future__ import annotations

from typing import Protocol

from app.core.config import get_settings


class Storage(Protocol):
    def presigned_put_url(self, key: str, content_type: str, expires: int) -> str: ...
    def presigned_get_url(self, key: str, expires: int) -> str: ...
    def head(self, key: str) -> tuple[bool, int]: ...  # (exists, size_bytes)


class MemoryStorage:
    """In-process fake. Tests call ``put`` to simulate the client's upload."""

    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self._objects: dict[str, bytes] = {}

    def presigned_put_url(self, key: str, content_type: str, expires: int) -> str:
        return f"memory://{self.bucket}/{key}?X-Amz-Expires={expires}&content-type={content_type}"

    def presigned_get_url(self, key: str, expires: int) -> str:
        return f"memory://{self.bucket}/{key}?X-Amz-Expires={expires}"

    def head(self, key: str) -> tuple[bool, int]:
        data = self._objects.get(key)
        return (data is not None, len(data) if data is not None else 0)

    # --- test helper (not part of the interface) ---
    def put(self, key: str, data: bytes) -> None:
        self._objects[key] = data


class S3Storage:
    """boto3-backed S3 / MinIO. Ensures the bucket exists on construction."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, region: str) -> None:
        import boto3
        from botocore.client import Config

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    def presigned_put_url(self, key: str, content_type: str, expires: int) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )

    def presigned_get_url(self, key: str, expires: int) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )

    def head(self, key: str) -> tuple[bool, int]:
        from botocore.exceptions import ClientError
        try:
            resp = self._client.head_object(Bucket=self.bucket, Key=key)
            return True, int(resp.get("ContentLength", 0))
        except ClientError:
            return False, 0


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is not None:
        return _storage
    s = get_settings()
    if s.storage_backend == "s3":
        _storage = S3Storage(
            s.storage_endpoint, s.storage_access_key, s.storage_secret_key,
            s.storage_bucket, s.storage_region,
        )
    else:
        _storage = MemoryStorage(s.storage_bucket)
    return _storage
