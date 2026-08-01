"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root is the repository directory.
PACKAGE_ROOT: Path = Path(__file__).resolve().parent
DATA_DIR: Path = PACKAGE_ROOT / "data"
DEFAULT_EVENTS_PATH: Path = DATA_DIR / "sample_events.json"

load_dotenv(PACKAGE_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Runtime settings for Khyati."""

    events_path: Path = DEFAULT_EVENTS_PATH
    llm_provider: str = "gemini"
    llm_api_key: str | None = None
    llm_model: str = "gemini-3.5-flash-lite"
    llm_base_url: str | None = None
    llm_timeout_seconds: float = 60.0
    llm_max_concurrent: int = 2
    use_llm: bool = True
    caspian_api_key: str | None = None
    caspian_base_url: str = "https://api.trycaspianai.com"
    caspian_email_username: str = "khyati"
    caspian_telegram_bot_token: str | None = None


def get_settings() -> Settings:
    """Build settings from `.env` or process-level environment variables."""
    configured_path = os.getenv("KHYATI_EVENTS_PATH")
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    provider_defaults = {
        "gemini": (
            os.getenv("GEMINI_API_KEY"),
            "gemini-3.5-flash-lite",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        "deepseek": (
            os.getenv("DEEPSEEK_API_KEY"),
            "deepseek-v4-flash",
            "https://api.deepseek.com",
        ),
        "openai": (
            os.getenv("OPENAI_API_KEY"),
            "gpt-5.6-sol",
            None,
        ),
    }
    if provider not in provider_defaults:
        raise ValueError("LLM_PROVIDER must be gemini, deepseek, or openai")
    provider_key, default_model, default_base_url = provider_defaults[provider]

    return Settings(
        events_path=Path(configured_path) if configured_path else DEFAULT_EVENTS_PATH,
        llm_provider=provider,
        llm_api_key=os.getenv("LLM_API_KEY") or provider_key,
        llm_model=os.getenv("LLM_MODEL", default_model),
        llm_base_url=os.getenv("LLM_BASE_URL") or default_base_url,
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        llm_max_concurrent=int(os.getenv("LLM_MAX_CONCURRENT", "2")),
        use_llm=os.getenv("KHYATI_USE_LLM", "true").lower()
        in {"1", "true", "yes", "on"},
        caspian_api_key=os.getenv("CASPIAN_API_KEY"),
        caspian_base_url=os.getenv(
            "CASPIAN_BASE_URL", "https://api.trycaspianai.com"
        ),
        caspian_email_username=os.getenv("CASPIAN_EMAIL_USERNAME", "khyati"),
        caspian_telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
    )
