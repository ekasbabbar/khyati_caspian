"""Domain models for Khyati."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
    telegram_username: str | None = None
    company: str | None = None
    role: str | None = None
    plan: str | None = None
    timezone: str | None = None
    contact_preferences: dict[str, Any] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)


class IntentDecision(BaseModel):
    """Outcome of intent analysis — whether and how to reach out."""

    should_contact: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    action: str | None = None
    objective: str | None = None
    recommended_channel: Literal["email", "telegram"] | None = None

    @model_validator(mode="after")
    def validate_outreach_details(self) -> "IntentDecision":
        """Keep contact decisions internally consistent."""
        outreach = (self.action, self.objective, self.recommended_channel)
        if self.should_contact and any(value is None for value in outreach):
            raise ValueError(
                "contact decisions require action, objective, and channel"
            )
        if not self.should_contact and any(value is not None for value in outreach):
            raise ValueError("no-contact decisions cannot include outreach details")
        return self
