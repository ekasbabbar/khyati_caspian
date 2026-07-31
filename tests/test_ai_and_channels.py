"""Offline tests for OpenAI reasoning and Caspian's shared handler."""

from datetime import datetime
from types import SimpleNamespace
import unittest

from channels import build_handler
from intent_agent import IntentAgent
from models import Customer, Event, IntentDecision
from reply_agent import ReplyAgent


def sample_customer() -> Customer:
    return Customer(
        id="cust_001",
        name="Alice",
        email="alice@example.com",
        events=[
            Event(
                type="pricing_page",
                timestamp=datetime(2026, 7, 30, 9, 30),
            )
        ],
    )


class FakeCompletions:
    def __init__(
        self,
        decision: IntentDecision | None = None,
        reply: str = "How can I help?",
        error: Exception | None = None,
    ) -> None:
        self.decision = decision
        self.reply = reply
        self.error = error

    def create(self, **kwargs):
        if self.error:
            raise self.error
        content = (
            self.decision.model_dump_json()
            if self.decision is not None
            else self.reply
        )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=content))
            ]
        )


class FakeOpenAI:
    def __init__(self, completions: FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


class FakeMessage:
    def __init__(self, channel: str, text: str = "Can you help?") -> None:
        self.channel = channel
        self.text = text
        self.sender = {"address": "alice@example.com"}
        self.replies: list[str] = []

    def reply(self, text: str) -> None:
        self.replies.append(text)


class StubReplyAgent:
    def __init__(self) -> None:
        self.channels: list[str] = []

    def respond(self, text: str, channel: str) -> str:
        self.channels.append(channel)
        return f"Helpful reply on {channel}"


class AIIntentTests(unittest.TestCase):
    def test_structured_llm_decision_is_used(self) -> None:
        expected = IntentDecision(
            should_contact=False,
            confidence=0.84,
            reason="The customer needs time to explore.",
        )
        client = FakeOpenAI(FakeCompletions(decision=expected))

        decision = IntentAgent(client=client).analyze(sample_customer())

        self.assertEqual(decision, expected)

    def test_rule_engine_is_used_when_llm_fails(self) -> None:
        client = FakeOpenAI(FakeCompletions(error=RuntimeError("API unavailable")))

        decision = IntentAgent(client=client).analyze(sample_customer())

        self.assertFalse(decision.should_contact)
        self.assertEqual(decision.reason, "No outreach triggers detected.")


class ReplyAgentTests(unittest.TestCase):
    def test_reply_agent_returns_model_text(self) -> None:
        client = FakeOpenAI(FakeCompletions(reply="Happy to help, Alice."))
        agent = ReplyAgent(api_key="test", model="test-model", client=client)

        reply = agent.respond("I need help", "email")

        self.assertEqual(reply, "Happy to help, Alice.")


class SharedHandlerTests(unittest.TestCase):
    def test_one_handler_replies_on_email_and_whatsapp(self) -> None:
        agent = StubReplyAgent()
        handler = build_handler(agent)
        email = FakeMessage("email")
        whatsapp = FakeMessage("whatsapp")

        handler(email)
        handler(whatsapp)

        self.assertEqual(agent.channels, ["email", "whatsapp"])
        self.assertEqual(email.replies, ["Helpful reply on email"])
        self.assertEqual(whatsapp.replies, ["Helpful reply on whatsapp"])


if __name__ == "__main__":
    unittest.main()
