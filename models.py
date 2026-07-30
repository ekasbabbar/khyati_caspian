"""Domain models for Khyati."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Event(BaseModel):
    """A single user activity event."""

    type: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class Customer(BaseModel):
    """A user and their activity history."""

    id: str
    name: str
    email: str
    events: list[Event] = Field(default_factory=list)


class IntentDecision(BaseModel):
    """Outcome of intent analysis — whether and how to reach out."""

    should_contact: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    action: str | None = None
    objective: str | None = None
    recommended_channel: str | None = None
