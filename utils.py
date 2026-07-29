"""Shared utility helpers."""

from pathlib import Path


def read_text_file(path: Path) -> str:
    """Read a UTF-8 text file and return its contents."""
    return path.read_text(encoding="utf-8")
