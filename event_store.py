"""Load a sample recruiter interaction from JSON."""

import json
from pathlib import Path

from pydantic import BaseModel

from models import InteractionEvent, RecruiterLead


class RecruiterDetails(BaseModel):
    id: str
    name: str
    email: str
    company: str | None = None
    role: str | None = None
    hiring_for: str | None = None


class RecruiterHistory(BaseModel):
    recruiter: RecruiterDetails
    events: list[InteractionEvent]


class EventStore:
    """Load and validate a recruiter interaction history."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lead: RecruiterLead | None = None

    @property
    def lead(self) -> RecruiterLead:
        if self._lead is None:
            raise RuntimeError("Call load() before accessing lead.")
        return self._lead

    def load(self) -> RecruiterLead:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        history = RecruiterHistory.model_validate(raw)
        recruiter = history.recruiter
        self._lead = RecruiterLead(
            id=recruiter.id,
            name=recruiter.name,
            email=recruiter.email,
            company=recruiter.company,
            role=recruiter.role,
            hiring_for=recruiter.hiring_for,
            events=sorted(history.events, key=lambda event: event.timestamp),
        )
        return self._lead
