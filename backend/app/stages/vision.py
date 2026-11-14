"""Vision grading via Amazon Bedrock (Converse API). Output is evidence, never a decision."""
import json

from pydantic import BaseModel, ValidationError

from .. import config

PROMPT = """You inspect product returns. Image 1: the returned item next to a scale display and an on-screen code.
Image 2: a close-up of the serial label.
Ship-out record of this exact unit: {fp}
Expected on-screen code: {code}

Reply with ONLY this JSON, no other text:
{{"same_item": bool, "same_unit": bool, "confidence": 0-1, "serial_read": string|null,
 "scale_reading_g": number|null, "code_visible": bool, "new_damage": [string], "grade": "A"|"B"|"C"|"D", "notes": string}}"""


class VisionResult(BaseModel):
    same_item: bool
    same_unit: bool
    confidence: float
    serial_read: str | None = None
    scale_reading_g: float | None = None
    code_visible: bool = False
    new_damage: list[str] = []
    grade: str = "C"
    notes: str = ""


_client = None


def client():
    global _client
    if _client is None:
        _client = config.aws_session().client("bedrock-runtime")
    return _client


def _call(model_id: str, item_jpg: bytes, serial_jpg: bytes, fingerprint: dict, code: str) -> VisionResult:
    msg = {"role": "user", "content": [
        {"text": PROMPT.format(fp=json.dumps(fingerprint), code=code)},
        {"image": {"format": "jpeg", "source": {"bytes": item_jpg}}},
        {"image": {"format": "jpeg", "source": {"bytes": serial_jpg}}},
    ]}
    r = client().converse(modelId=model_id, messages=[msg],
                          inferenceConfig={"maxTokens": 600, "temperature": 0})
    text = r["output"]["message"]["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return VisionResult(**json.loads(text))


def grade(item_jpg: bytes, serial_jpg: bytes, fingerprint: dict, code: str) -> tuple[VisionResult | None, str]:
    """Returns (result, model_used). result is None if every attempt failed -> policy sends to REVIEW."""
    for model_id in (config.BEDROCK_MODEL_ID, config.BEDROCK_MODEL_ID, config.BEDROCK_FALLBACK_ID):
        try:
            return _call(model_id, item_jpg, serial_jpg, fingerprint, code), model_id
        except (ValidationError, json.JSONDecodeError, KeyError):
            continue
        except Exception:  # network / throttling / access
            continue
    return None, "none"
