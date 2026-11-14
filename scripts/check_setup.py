"""Checks every outside service Boomerang needs. Run from the repo root after filling in .env:

    python scripts/check_setup.py

Each line prints PASS or FAIL with a hint. Costs well under one cent (two tiny Bedrock calls).
"""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import config  # noqa: E402  (loads .env)

ok_all = True


def report(name: str, ok: bool, detail: str = "") -> None:
    global ok_all
    ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


# 1. .env filled in
has_aws = bool(config.AWS_PROFILE) or bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))
missing = [k for k, v in (("AWS_PROFILE or AWS keys", has_aws), ("S3_BUCKET", config.S3_BUCKET),
                          ("MONGODB_URI", config.MONGODB_URI)) if not v]
report(".env values", not missing, f"empty: {', '.join(missing)}" if missing else "")

try:
    session = config.aws_session()
except Exception as e:  # e.g. profile name not found in ~/.aws/credentials
    report("AWS profile", False, f"{type(e).__name__}: {e}")
    sys.exit(1)

# 2. AWS credentials
try:
    who = session.client("sts").get_caller_identity()
    report("AWS credentials", True, f"{who['Arn']} via {'profile ' + config.AWS_PROFILE if config.AWS_PROFILE else 'keys'}")
except Exception as e:
    report("AWS credentials", False, f"{type(e).__name__}: check AWS_PROFILE or the keys in .env")

# 3. Bedrock model (primary and fallback)
for label, model in (("Bedrock primary", config.BEDROCK_MODEL_ID), ("Bedrock fallback", config.BEDROCK_FALLBACK_ID)):
    try:
        r = session.client("bedrock-runtime").converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": "Reply with the word OK."}]}],
            inferenceConfig={"maxTokens": 5},
        )
        report(label, True, f"{model} in {config.AWS_REGION} said {r['output']['message']['content'][0]['text'].strip()!r}")
    except Exception as e:
        msg = str(e)
        hint = ("use the us. inference profile ID" if "on-demand" in msg else
                "enable model access + IAM bedrock:InvokeModel" if "AccessDenied" in msg else msg[:140])
        report(label, False, hint)

# 4. S3 write + read
try:
    s3 = session.client("s3")
    key = f"healthcheck/{uuid.uuid4()}.txt"
    s3.put_object(Bucket=config.S3_BUCKET, Key=key, Body=b"ok")
    body = s3.get_object(Bucket=config.S3_BUCKET, Key=key)["Body"].read()
    try:
        s3.delete_object(Bucket=config.S3_BUCKET, Key=key)
    except Exception:
        pass  # IAM policy may not allow delete; harmless
    report("S3 bucket", body == b"ok", f"{config.S3_BUCKET} ({config.AWS_REGION})")
except Exception as e:
    report("S3 bucket", False, f"{type(e).__name__}: check bucket name/region and IAM s3:PutObject/GetObject")

# 5. MongoDB
try:
    from pymongo import MongoClient
    MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=5000).admin.command("ping")
    report("MongoDB Atlas", True, f"db {config.MONGODB_DB}")
except Exception as e:
    report("MongoDB Atlas", False, f"{type(e).__name__}: check Network Access 0.0.0.0/0 and the password in the URI")

print("\nALL GOOD" if ok_all else "\nFix the FAIL lines above, then run this again.")
sys.exit(0 if ok_all else 1)
