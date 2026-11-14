import sys; sys.path.insert(0, "backend")
from app import config
for m in (config.BEDROCK_MODEL_ID, config.BEDROCK_FALLBACK_ID):
    try:
        r = config.aws_session().client("bedrock-runtime").converse(modelId=m, messages=[{"role": "user", "content": [{"text": "Say OK"}]}], inferenceConfig={"maxTokens": 5})
        print("OK  ", m, "->", r["output"]["message"]["content"][0]["text"])
    except Exception as e:
        print("FAIL", m, "->", type(e).__name__, e)
