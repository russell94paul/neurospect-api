import uuid

import boto3
from botocore.config import Config

from app.config import settings


def _make_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


class R2Client:
    """Thin wrapper around boto3 for Cloudflare R2 (S3-compatible)."""

    def __init__(self):
        self._client = _make_client()
        self._bucket = settings.r2_bucket

    def storage_key(self, user_id: uuid.UUID, trade_id: uuid.UUID, phase: str, ext: str) -> str:
        """Build canonical storage key: {user_id}/{trade_id}/{phase}/{uuid4}.{ext}"""
        return f"{user_id}/{trade_id}/{phase}/{uuid.uuid4()}.{ext}"

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def presign(self, key: str, expires: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires,
        )


# Module-level singleton — None when R2_ENDPOINT_URL is not configured (local dev).
# Tests can monkeypatch `app.services.r2.r2` before importing routers.
r2: R2Client | None = R2Client() if settings.r2_endpoint_url else None
