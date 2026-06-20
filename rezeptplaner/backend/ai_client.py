from openai import AsyncOpenAI

from .config import load_options


def get_client() -> tuple[AsyncOpenAI, str]:
    opts = load_options()
    client = AsyncOpenAI(
        base_url=opts["ai_base_url"],
        api_key=opts["ai_api_key"] or "no-key",  # Ollama braucht keinen Key
        timeout=60.0,
    )
    return client, opts["ai_model"]


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
