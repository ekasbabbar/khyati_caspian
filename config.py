"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root is the repository directory.
PACKAGE_ROOT: Path = Path(__file__).resolve().parent
DATA_DIR: Path = PACKAGE_ROOT / "data"
LOCAL_KNOWLEDGE_DIR: Path = PACKAGE_ROOT / "knowledge"
EXAMPLE_KNOWLEDGE_DIR: Path = PACKAGE_ROOT / "knowledge.example"
DEFAULT_KNOWLEDGE_INDEX: Path = PACKAGE_ROOT / ".khyati" / "knowledge.sqlite3"
DEFAULT_OWNER_CHANNEL_STATE: Path = PACKAGE_ROOT / ".khyati" / "owner_channel.json"
DEFAULT_APPROVAL_STATE: Path = PACKAGE_ROOT / ".khyati" / "pending_approvals.json"
DEFAULT_OUTBOUND_STATE: Path = PACKAGE_ROOT / ".khyati" / "outbound_drafts.json"
DEFAULT_EMAIL_THREAD_STATE: Path = PACKAGE_ROOT / ".khyati" / "email_threads.json"
LOCAL_EVENTS_PATH: Path = DATA_DIR / "sample_events.json"
EXAMPLE_EVENTS_PATH: Path = DATA_DIR / "sample_events.example.json"
DEFAULT_EVENTS_PATH: Path = (
    LOCAL_EVENTS_PATH if LOCAL_EVENTS_PATH.exists() else EXAMPLE_EVENTS_PATH
)

load_dotenv(PACKAGE_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Runtime settings for Khyati."""

    events_path: Path = DEFAULT_EVENTS_PATH
    knowledge_dir: Path = EXAMPLE_KNOWLEDGE_DIR
    knowledge_index_path: Path = DEFAULT_KNOWLEDGE_INDEX
    owner_channel_state_path: Path = DEFAULT_OWNER_CHANNEL_STATE
    approval_state_path: Path = DEFAULT_APPROVAL_STATE
    outbound_state_path: Path = DEFAULT_OUTBOUND_STATE
    email_thread_state_path: Path = DEFAULT_EMAIL_THREAD_STATE
    llm_provider: str = "gemini"
    llm_api_key: str | None = None
    llm_model: str = "gemini-3.5-flash-lite"
    llm_base_url: str | None = None
    llm_timeout_seconds: float = 60.0
    llm_max_concurrent: int = 2
    featherless_api_key: str | None = None
    featherless_model: str = "Qwen/Qwen3-32B"
    featherless_base_url: str = "https://api.featherless.ai/v1"
    featherless_timeout_seconds: float = 15.0
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_timeout_seconds: float = 12.0
    llm_circuit_failure_threshold: int = 3
    llm_circuit_cooldown_seconds: float = 60.0
    use_llm: bool = True
    caspian_api_key: str | None = None
    caspian_base_url: str = "https://api.trycaspianai.com"
    caspian_email_username: str = "khyati"
    caspian_telegram_bot_token: str | None = None
    owner_telegram_username: str | None = None


def get_settings() -> Settings:
    """Build settings from `.env` or process-level environment variables."""
    configured_path = os.getenv("KHYATI_EVENTS_PATH")
    configured_knowledge = os.getenv("KHYATI_KNOWLEDGE_DIR")
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
        knowledge_dir=(
            Path(configured_knowledge)
            if configured_knowledge
            else (
                LOCAL_KNOWLEDGE_DIR
                if LOCAL_KNOWLEDGE_DIR.exists()
                else EXAMPLE_KNOWLEDGE_DIR
            )
        ),
        knowledge_index_path=Path(
            os.getenv("KHYATI_KNOWLEDGE_INDEX", str(DEFAULT_KNOWLEDGE_INDEX))
        ),
        owner_channel_state_path=Path(
            os.getenv(
                "KHYATI_OWNER_CHANNEL_STATE",
                str(DEFAULT_OWNER_CHANNEL_STATE),
            )
        ),
        approval_state_path=Path(
            os.getenv("KHYATI_APPROVAL_STATE", str(DEFAULT_APPROVAL_STATE))
        ),
        outbound_state_path=Path(
            os.getenv("KHYATI_OUTBOUND_STATE", str(DEFAULT_OUTBOUND_STATE))
        ),
        email_thread_state_path=Path(
            os.getenv("KHYATI_EMAIL_THREAD_STATE", str(DEFAULT_EMAIL_THREAD_STATE))
        ),
        llm_provider=provider,
        llm_api_key=os.getenv("LLM_API_KEY") or provider_key,
        llm_model=os.getenv("LLM_MODEL", default_model),
        llm_base_url=os.getenv("LLM_BASE_URL") or default_base_url,
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        llm_max_concurrent=int(os.getenv("LLM_MAX_CONCURRENT", "2")),
        featherless_api_key=os.getenv("FEATHERLESS_API_KEY"),
        featherless_model=os.getenv("FEATHERLESS_MODEL", "Qwen/Qwen3-32B"),
        featherless_base_url=os.getenv(
            "FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"
        ),
        featherless_timeout_seconds=float(
            os.getenv("FEATHERLESS_TIMEOUT_SECONDS", "15")
        ),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        gemini_base_url=os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        gemini_timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "12")),
        llm_circuit_failure_threshold=int(
            os.getenv("LLM_CIRCUIT_FAILURE_THRESHOLD", "3")
        ),
        llm_circuit_cooldown_seconds=float(
            os.getenv("LLM_CIRCUIT_COOLDOWN_SECONDS", "60")
        ),
        use_llm=os.getenv("KHYATI_USE_LLM", "true").lower()
        in {"1", "true", "yes", "on"},
        caspian_api_key=os.getenv("CASPIAN_API_KEY"),
        caspian_base_url=os.getenv(
            "CASPIAN_BASE_URL", "https://api.trycaspianai.com"
        ),
        caspian_email_username=os.getenv("CASPIAN_EMAIL_USERNAME", "khyati"),
        caspian_telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        owner_telegram_username=os.getenv("KHYATI_OWNER_TELEGRAM_USERNAME"),
    )
