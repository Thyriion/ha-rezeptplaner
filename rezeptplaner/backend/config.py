import json
import os
from pathlib import Path

OPTIONS_PATH = Path(os.environ.get("OPTIONS_PATH", "/data/options.json"))


def load_options() -> dict:
    try:
        return json.loads(OPTIONS_PATH.read_text())
    except FileNotFoundError:
        return {
            "ai_base_url": os.environ.get("AI_BASE_URL", "https://api.mistral.ai/v1"),
            "ai_model": os.environ.get("AI_MODEL", "mistral-small-latest"),
            "ai_api_key": os.environ.get("AI_API_KEY", ""),
        }
