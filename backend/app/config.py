"""Loads settings from .env once, so every module reads the same values."""
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

# .env lives at the repo root (two levels up from backend/app/)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# boto3 treats an empty AWS_PROFILE= / AWS_ACCESS_KEY_ID= as a real value and fails,
# so drop any AWS_* variable that .env left blank.
for _k in ("AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
    if os.environ.get(_k) == "":
        del os.environ[_k]


def get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    return value if value not in ("", None) else default


AWS_REGION = get("AWS_REGION", "us-east-2")
AWS_PROFILE = get("AWS_PROFILE")           # preferred: keys stay in ~/.aws/credentials
S3_BUCKET = get("S3_BUCKET")
BEDROCK_MODEL_ID = get("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")
BEDROCK_FALLBACK_ID = get("BEDROCK_FALLBACK_ID", "us.amazon.nova-pro-v1:0")
GEMINI_API_KEY = get("GEMINI_API_KEY")
MONGODB_URI = get("MONGODB_URI")
MONGODB_DB = get("MONGODB_DB", "returniq")
LINK_SIGNING_SECRET = get("LINK_SIGNING_SECRET", "dev-only-change-me")
STATION_KEY = get("STATION_KEY")             # shared staff secret for ship-out, review and seed
# Only needed when the pages are hosted somewhere else (e.g. Amplify): comma-separated exact origins.
ALLOWED_ORIGINS = [o.strip() for o in (get("ALLOWED_ORIGINS") or "").split(",") if o.strip()]
DEMO_MODE = get("DEMO_MODE", "0") == "1"   # enables POST /seed (wipes demo data); off by default


def aws_session() -> boto3.Session:
    """Uses AWS_PROFILE if set, otherwise AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY from the environment."""
    return boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
