"""Behavior tests for Khyati's rule-based intent engine."""

from datetime import datetime
import unittest

from intent_agent import IntentAgent
from models import Customer, Event, IntentDecision
from pydantic import ValidationError


def customer_with(*event_types: str) -> Customer:
    """Build a customer with the requested event sequence."""
    events = [
        Event(type=event_type, timestamp=datetime(2026, 7, 30, 9, index))
        for index, event_type in enumerate(event_types)
    ]
    return Customer(
        id="cust_test",
        name="Test Customer",
        email="test@example.com",
        events=events,
    )


class IntentAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = IntentAgent()

    def test_signup_alone_does_not_trigger_contact(self) -> None:
        decision = self.agent.analyze(customer_with("signup"))
        self.assertFalse(decision.should_contact)

    def test_three_pricing_views_trigger_contact(self) -> None:
        decision = self.agent.analyze(
            customer_with("pricing_page", "pricing_page", "pricing_page")
        )
        self.assertTrue(decision.should_contact)
        self.assertEqual(decision.objective, "Offer plan guidance")

    def test_payment_failure_triggers_immediate_help(self) -> None:
        decision = self.agent.analyze(customer_with("payment_failed"))
        self.assertTrue(decision.should_contact)
        self.assertEqual(decision.objective, "Resolve payment issue")

    def test_inactivity_triggers_reengagement(self) -> None:
        decision = self.agent.analyze(customer_with("inactive_14_days"))
        self.assertTrue(decision.should_contact)
        self.assertEqual(decision.objective, "Re-engage customer")

    def test_teammate_invitation_and_pricing_trigger_upsell(self) -> None:
        decision = self.agent.analyze(
            customer_with("invited_teammate", "pricing_page")
        )
        self.assertTrue(decision.should_contact)
        self.assertEqual(decision.objective, "Offer Pro plan")

    def test_higher_priority_payment_rule_wins(self) -> None:
        decision = self.agent.analyze(
            customer_with(
                "inactive_14_days",
                "pricing_page",
                "pricing_page",
                "pricing_page",
                "payment_failed",
            )
        )
        self.assertEqual(decision.objective, "Resolve payment issue")

    def test_confidence_must_be_between_zero_and_one(self) -> None:
        with self.assertRaises(ValidationError):
            IntentDecision(
                should_contact=True,
                confidence=1.1,
                reason="Invalid confidence",
                objective="Test",
                recommended_channel="email",
            )


if __name__ == "__main__":
    unittest.main()
