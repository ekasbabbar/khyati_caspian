"""Persistent owner-authorized outbound email drafts."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from threading import Lock
from uuid import uuid4


@dataclass
class OutboundDraft:
    id: str
    recipient: str
    text: str
    status: str = "draft"


class OutboundDraftStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = Lock()
        self._items = self._load()

    def _load(self) -> dict[str, OutboundDraft]:
        if self._path is None or not self._path.is_file():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            return {item["id"]: OutboundDraft(**item) for item in payload.get("drafts", [])}
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            return {}

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"drafts": [asdict(item) for item in self._items.values()]}, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self._path)

    def create(self, recipient: str, text: str) -> OutboundDraft:
        with self._lock:
            item = OutboundDraft(f"OUT-{uuid4().hex[:6].upper()}", recipient, text)
            self._items[item.id] = item
            self._save()
            return item

    def get(self, draft_id: str) -> OutboundDraft | None:
        with self._lock:
            return self._items.get(draft_id.upper())

    def resolve(self, draft_id: str, status: str) -> None:
        with self._lock:
            self._items[draft_id.upper()].status = status
            self._save()
