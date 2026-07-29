"""Domain models for Khyati."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """Known user activity event types."""

    SIGNUP = "signup"
    LOGIN = "login"
    FEATURE_USED = "feature_used"
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUPPORT_TICKET = "support_ticket"
    INACTIVITY = "inactivity"


class Customer(BaseModel):
    """A user tracked by the customer success agent."""

    id: str
    name: str
    email: str
    plan: str = "free"
    created_at: datetime


class Event(BaseModel):
    """A single user activity event."""

    id: str
    customer_id: str
    event_type: EventType
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
