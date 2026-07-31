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

    try:
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
            timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=10.0),
        )
        response.raise_for_status()
    except httpx.ReadTimeout as error:
        raise SystemExit(
            f"TIMEOUT: {settings.llm_provider} did not respond within "
            f"{settings.llm_timeout_seconds:.0f}s. Try again, or increase "
            "LLM_TIMEOUT_SECONDS in .env."
        ) from error
    except httpx.HTTPStatusError as error:
        detail = error.response.text[:500]
        raise SystemExit(
            f"API ERROR: {error.response.status_code} from "
            f"{settings.llm_provider}: {detail}"
        ) from error
    except httpx.RequestError as error:
        raise SystemExit(
            f"NETWORK ERROR: could not reach {settings.llm_provider}: {error}"
        ) from error

    payload = response.json()
    reply = payload["choices"][0]["message"]["content"]
    print(f"Response: {reply}")


if __name__ == "__main__":
    main()
