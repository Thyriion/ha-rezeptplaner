from openai import AsyncOpenAI

from .config import AppConfig, load


def get_client(cfg: AppConfig | None = None) -> tuple[AsyncOpenAI, str]:
    if cfg is None:
        cfg = load()
    client = AsyncOpenAI(
        base_url=cfg.base_url,
        api_key=cfg.api_key or "no-key",  # Ollama braucht keinen Key
        timeout=60.0,
    )
    return client, cfg.model


async def test_connection() -> tuple[bool, str]:
    client, model = get_client()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Antworte nur mit: OK"}],
            max_tokens=10,
        )
        reply = resp.choices[0].message.content or ""
        return True, f"Verbindung erfolgreich ({model}): {reply.strip()}"
    except Exception as e:
        return False, str(e)
