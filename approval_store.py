"""Persistent human-approval state for recruiter scheduling requests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from threading import Lock
from uuid import uuid4


@dataclass
class PendingApproval:
    id: str
    email_conversation_id: str
    recruiter_address: str
    recruiter_name: str
    request_text: str
    status: str = "pending"


class ApprovalStore:
    """Store approval requests locally so they survive process restarts."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = Lock()
        self._items = self._load()

    def _load(self) -> dict[str, PendingApproval]:
        if self._path is None or not self._path.is_file():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            return {
                item["id"]: PendingApproval(**item)
                for item in payload.get("requests", [])
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            return {}

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"requests": [asdict(item) for item in self._items.values()]},
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self._path)

    def create(
        self,
        email_conversation_id: str,
        recruiter_address: str,
        recruiter_name: str,
        request_text: str,
    ) -> PendingApproval:
        """Create one request, deduplicating repeated delivery in a thread."""
        with self._lock:
            for item in self._items.values():
                if (
                    item.status == "pending"
                    and item.email_conversation_id == email_conversation_id
                    and item.request_text == request_text
                ):
                    return item
            item = PendingApproval(
                id=f"INT-{uuid4().hex[:6].upper()}",
                email_conversation_id=email_conversation_id,
                recruiter_address=recruiter_address,
                recruiter_name=recruiter_name,
                request_text=request_text,
            )
            self._items[item.id] = item
            self._save()
            return item

    def pending(self) -> list[PendingApproval]:
        with self._lock:
            return [item for item in self._items.values() if item.status == "pending"]

    def get(self, request_id: str) -> PendingApproval | None:
        with self._lock:
            return self._items.get(request_id.upper())

    def resolve(self, request_id: str, status: str) -> None:
        with self._lock:
            item = self._items[request_id.upper()]
            item.status = status
            self._save()
