"""Application configuration for the local vertical slice."""

from dataclasses import dataclass
import os
from pathlib import Path

# Project root is the repository directory.
PACKAGE_ROOT: Path = Path(__file__).resolve().parent
DATA_DIR: Path = PACKAGE_ROOT / "data"
DEFAULT_EVENTS_PATH: Path = DATA_DIR / "sample_events.json"


@dataclass(frozen=True)
class Settings:
    """Runtime settings for Khyati."""

    events_path: Path = DEFAULT_EVENTS_PATH


def get_settings() -> Settings:
    """Return settings, allowing the sample file to be overridden."""
    configured_path = os.getenv("KHYATI_EVENTS_PATH")
    return Settings(
        events_path=Path(configured_path) if configured_path else DEFAULT_EVENTS_PATH
    )
