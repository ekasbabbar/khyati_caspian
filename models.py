"""Domain models for Khyati, a personal career representative."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class InteractionEvent(BaseModel):
    """One event in a recruiter's interaction with Khyati."""

    type: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecruiterLead(BaseModel):
    """A recruiter, their hiring context, and interaction history."""

    id: str
    name: str
    email: str
    company: str | None = None
    role: str | None = None
    hiring_for: str | None = None
    events: list[InteractionEvent] = Field(default_factory=list)


class CareerDecision(BaseModel):
    """Khyati's decision about a recruiter interaction."""

    should_respond: bool
    should_notify_owner: bool
    confidence: float = Field(ge=0.0, le=1.0)
    recruiter_intent: Literal[
        "general_inquiry",
        "project_question",
        "availability_question",
        "interview_request",
        "compensation_question",
        "direct_contact_request",
        "unrelated",
    ]
    reason: str
    action: str | None = None
    objective: str | None = None
    recommended_channel: Literal["email", "telegram"] | None = None

    @model_validator(mode="after")
    def validate_action_details(self) -> "CareerDecision":
        action_required = self.should_respond or self.should_notify_owner
        details = (self.action, self.objective, self.recommended_channel)
        if action_required and any(value is None for value in details):
            raise ValueError(
                "actionable decisions require action, objective, and channel"
            )
        if not action_required and any(value is not None for value in details):
            raise ValueError("no-action decisions cannot include action details")
        return self
