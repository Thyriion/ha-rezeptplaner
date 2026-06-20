import json
import os
from pathlib import Path

from pydantic import BaseModel

OPTIONS_PATH = Path(os.environ.get("OPTIONS_PATH", "/data/options.json"))


class AppConfig(BaseModel):
    base_url: str = "https://api.mistral.ai/v1"
    model: str = "mistral-small-latest"
    api_key: str = ""


def load() -> AppConfig:
    try:
        data = json.loads(OPTIONS_PATH.read_text())
        return AppConfig(
            base_url=data.get("ai_base_url", "https://api.mistral.ai/v1"),
            model=data.get("ai_model", "mistral-small-latest"),
            api_key=data.get("ai_api_key", ""),
        )
    except FileNotFoundError:
        return AppConfig(
            base_url=os.environ.get("AI_BASE_URL", "https://api.mistral.ai/v1"),
            model=os.environ.get("AI_MODEL", "mistral-small-latest"),
            api_key=os.environ.get("AI_API_KEY", ""),
        )
