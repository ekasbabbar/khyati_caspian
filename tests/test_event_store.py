"""Tests for recruiter interaction loading."""
import json
from pathlib import Path
import tempfile
import unittest
from event_store import EventStore
from pydantic import ValidationError

class EventStoreTests(unittest.TestCase):
    def setUp(self): self.temp_dir = tempfile.TemporaryDirectory()
    def tearDown(self): self.temp_dir.cleanup()
    def write_history(self, payload):
        path = Path(self.temp_dir.name) / "events.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path
    def test_events_are_sorted_chronologically(self):
        path = self.write_history({"recruiter":{"id":"r1","name":"Priya","email":"p@example.com"},"events":[{"type":"interview_requested","timestamp":"2026-08-02T09:30:00"},{"type":"general_recruiter_inquiry","timestamp":"2026-08-02T09:00:00"}]})
        lead = EventStore(path).load()
        self.assertEqual([e.type for e in lead.events], ["general_recruiter_inquiry", "interview_requested"])
    def test_missing_recruiter_email_is_rejected(self):
        path = self.write_history({"recruiter":{"id":"r1","name":"Priya"},"events":[]})
        with self.assertRaises(ValidationError): EventStore(path).load()

if __name__ == "__main__": unittest.main()
