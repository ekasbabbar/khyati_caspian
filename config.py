"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is the intentflow/ package directory.
PACKAGE_ROOT: Path = Path(__file__).resolve().parent
DATA_DIR: Path = PACKAGE_ROOT / "data"
PROMPTS_DIR: Path = PACKAGE_ROOT / "prompts"
DEFAULT_EVENTS_PATH: Path = DATA_DIR / "sample_events.json"


class Settings(BaseSettings):
    """Runtime settings for IntentFlow."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Event data
    events_path: Path = DEFAULT_EVENTS_PATH

    # LLM (future intent / messaging agents)
    openai_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"

    # Caspian (future messaging — not wired up yet)
    caspian_api_key: str | None = None
    caspian_base_url: str = "https://api.trycaspianai.com"

    # Logging
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Return application settings, loading from .env when present."""
    return Settings()
