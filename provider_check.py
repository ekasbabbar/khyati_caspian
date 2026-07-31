"""Verify the configured LLM provider with one small live request."""

import httpx

from config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.llm_api_key:
        raise RuntimeError(
            f"No API key loaded for provider {settings.llm_provider!r}"
        )
    if not settings.llm_base_url:
        raise RuntimeError(
            "This check requires LLM_BASE_URL for the configured provider"
        )

    endpoint = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")
    print(f"Endpoint: {endpoint}")

    response = httpx.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "user", "content": "Reply with only: OK"},
            ],
        },
        timeout=30.0,
    )
    response.raise_for_status()

    payload = response.json()
    reply = payload["choices"][0]["message"]["content"]
    print(f"Response: {reply}")


if __name__ == "__main__":
    main()
