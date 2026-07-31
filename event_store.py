"""Load customer activity from JSON."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from models import Customer, Event


class CustomerDetails(BaseModel):
    """Customer fields as represented in the event-history file."""

    id: str
    name: str
    email: str
    whatsapp_number: str | None = None
    company: str | None = None
    role: str | None = None
    plan: str | None = None
    timezone: str | None = None
    contact_preferences: dict = Field(default_factory=dict)


class EventHistory(BaseModel):
    """Validated shape of an event-history file."""

    customer: CustomerDetails
    events: list[Event]


class EventStore:
    """Loads a customer and their events from a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._customer: Customer | None = None

    @property
    def customer(self) -> Customer:
        if self._customer is None:
            raise RuntimeError("Call load() before accessing customer.")
        return self._customer

    def load(self) -> Customer:
        """Load customer and events from the configured JSON file."""
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        history = EventHistory.model_validate(raw)
        customer_data = history.customer
        self._customer = Customer(
            id=customer_data.id,
            name=customer_data.name,
            email=customer_data.email,
            whatsapp_number=customer_data.whatsapp_number,
            company=customer_data.company,
            role=customer_data.role,
            plan=customer_data.plan,
            timezone=customer_data.timezone,
            contact_preferences=customer_data.contact_preferences,
            events=sorted(history.events, key=lambda event: event.timestamp),
        )
        return self._customer
