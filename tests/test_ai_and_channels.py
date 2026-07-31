"""Offline tests for OpenAI reasoning and Caspian's shared handler."""

from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from types import SimpleNamespace
import unittest

from channels import build_handler, connect_available_channels
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


class FailingReplyAgent:
    def respond(self, text: str, channel: str) -> str:
        raise RuntimeError("model unavailable")


class FakeCaspianClient:
    def __init__(
        self,
        email_error: Exception | None = None,
        whatsapp_error: Exception | None = None,
    ) -> None:
        self.email_error = email_error
        self.whatsapp_error = whatsapp_error

    def connect_email(self, **kwargs) -> dict:
        if self.email_error:
            raise self.email_error
        return {"id": "email-1", "address": "khyati@example.com"}

    def connect_whatsapp(self, **kwargs) -> dict:
        if self.whatsapp_error:
            raise self.whatsapp_error
        return {"id": "whatsapp-1", "address": "+15555550123"}


FAKE_SETTINGS = SimpleNamespace(
    caspian_email_username="khyati",
    caspian_whatsapp_provider="twilio-whatsapp",
)


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

        with self.assertLogs("intent_agent", level="ERROR") as logs:
            decision = IntentAgent(client=client).analyze(sample_customer())

        self.assertFalse(decision.should_contact)
        self.assertEqual(decision.reason, "No outreach triggers detected.")
        self.assertIn("using rule fallback", logs.output[0])


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

        with redirect_stdout(StringIO()):
            handler(email)
            handler(whatsapp)

        self.assertEqual(agent.channels, ["email", "whatsapp"])
        self.assertEqual(email.replies, ["Helpful reply on email"])
        self.assertEqual(whatsapp.replies, ["Helpful reply on whatsapp"])

    def test_model_failure_sends_safe_fallback(self) -> None:
        message = FakeMessage("email")

        with redirect_stdout(StringIO()) as output:
            build_handler(FailingReplyAgent())(message)

        self.assertIn("your message has been received", message.replies[0])
        self.assertIn("reply generation failed", output.getvalue())


class ChannelConnectionTests(unittest.TestCase):
    def test_email_remains_available_when_whatsapp_fails(self) -> None:
        client = FakeCaspianClient(
            whatsapp_error=RuntimeError("WhatsApp unavailable")
        )

        with redirect_stdout(StringIO()) as output:
            connected = connect_available_channels(client, FAKE_SETTINGS)

        self.assertEqual(set(connected), {"email"})
        self.assertIn("WhatsApp", output.getvalue())

    def test_startup_fails_when_both_channels_fail(self) -> None:
        client = FakeCaspianClient(
            email_error=RuntimeError("Email unavailable"),
            whatsapp_error=RuntimeError("WhatsApp unavailable"),
        )

        with redirect_stdout(StringIO()):
            with self.assertRaises(RuntimeError):
                connect_available_channels(client, FAKE_SETTINGS)


if __name__ == "__main__":
    unittest.main()
