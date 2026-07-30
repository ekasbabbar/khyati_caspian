"""Tests for loading and validating customer event history."""

import json
from pathlib import Path
import tempfile
import unittest

from event_store import EventStore
from pydantic import ValidationError


class EventStoreTests(unittest.TestCase):
    def write_history(self, payload: dict) -> Path:
        path = Path(self.temp_dir.name) / "events.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_events_are_sorted_chronologically(self) -> None:
        path = self.write_history(
            {
                "customer": {
                    "id": "cust_001",
                    "name": "Alice",
                    "email": "alice@example.com",
                },
                "events": [
                    {"type": "pricing_page", "timestamp": "2026-07-30T09:30:00"},
                    {"type": "signup", "timestamp": "2026-07-30T09:00:00"},
                ],
            }
        )

        customer = EventStore(path).load()

        self.assertEqual(
            [event.type for event in customer.events],
            ["signup", "pricing_page"],
        )

    def test_missing_customer_fields_raise_validation_error(self) -> None:
        path = self.write_history(
            {
                "customer": {"id": "cust_001", "name": "Alice"},
                "events": [],
            }
        )

        with self.assertRaises(ValidationError):
            EventStore(path).load()


if __name__ == "__main__":
    unittest.main()
