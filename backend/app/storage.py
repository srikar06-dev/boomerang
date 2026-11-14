"""S3 access: presigned upload URLs and reading photos back. The bucket stays fully private."""
from botocore.config import Config
from botocore.exceptions import ClientError

from . import config

MAX_PHOTO_BYTES = 8 * 1024 * 1024   # reject anything larger before reading it into memory
UPLOAD_URL_TTL_S = 300              # an upload link works for 5 minutes


class NotFound(Exception):
    """The photo was never uploaded."""


class TooLarge(Exception):
    """The uploaded object is bigger than MAX_PHOTO_BYTES."""


_client = None


def client():
    global _client
    if _client is None:
        if not config.S3_BUCKET:
            raise RuntimeError("S3_BUCKET is empty - fill in .env")
        _client = config.aws_session().client("s3", config=Config(signature_version="s3v4"))
    return _client


def presign_put(key: str) -> str:
    """URL the browser/station can PUT one JPEG to. The key is chosen by the server, never the client."""
    return client().generate_presigned_url(
        "put_object",
        Params={"Bucket": config.S3_BUCKET, "Key": key, "ContentType": "image/jpeg"},
        ExpiresIn=UPLOAD_URL_TTL_S,
    )


def presign_get(key: str, ttl_s: int = 300) -> str:
    """Short-lived link for the reviewer page to display a photo."""
    return client().generate_presigned_url(
        "get_object", Params={"Bucket": config.S3_BUCKET, "Key": key}, ExpiresIn=ttl_s)


def get_bytes(key: str) -> bytes:
    try:
        obj = client().get_object(Bucket=config.S3_BUCKET, Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
            raise NotFound(key) from None
        raise
    if obj.get("ContentLength", 0) > MAX_PHOTO_BYTES:
        raise TooLarge(key)
    return obj["Body"].read(MAX_PHOTO_BYTES + 1)[:MAX_PHOTO_BYTES]
