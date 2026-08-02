"""Verify the configured primary/fallback LLM chain with one small request."""

from config import get_settings
from llm_provider import build_provider_chain


def main() -> None:
    chain = build_provider_chain(get_settings())
    print(f"Provider order: {' -> '.join(chain.provider_names)}")
    try:
        response = chain.chat.completions.create(
            model="provider-chain",
            messages=[{"role": "user", "content": "Reply with only: OK"}],
            max_tokens=32,
        )
    except Exception as error:
        raise SystemExit(f"PROVIDER CHAIN FAILED: {error}") from error
    print(f"Served by: {chain.last_provider}")
    print(f"Response: {response.choices[0].message.content}")


if __name__ == "__main__":
    main()
