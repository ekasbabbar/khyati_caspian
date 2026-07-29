"""Load and query user activity events."""

import json
from pathlib import Path

from models import Customer, Event


class EventStore:
    """In-memory store backed by a JSON file of events and customers."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._events: list[Event] = []
        self._customers: dict[str, Customer] = {}

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    @property
    def customers(self) -> dict[str, Customer]:
        return dict(self._customers)

    def load(self) -> None:
        """Load events and customers from the configured JSON file."""
        raw = json.loads(self._path.read_text(encoding="utf-8"))

        self._customers = {
            customer["id"]: Customer.model_validate(customer)
            for customer in raw.get("customers", [])
        }
        self._events = [Event.model_validate(event) for event in raw.get("events", [])]

    def get_events_for_customer(self, customer_id: str) -> list[Event]:
        """Return all events belonging to a single customer."""
        return [event for event in self._events if event.customer_id == customer_id]
