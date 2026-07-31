"""Run a quick end-to-end check of Khyati's core product loop."""

from config import get_settings
from event_store import EventStore
from intent_agent import IntentAgent
from messaging_agent import MessagingAgent


def main() -> None:
    customer = EventStore(get_settings().events_path).load()
    # Smoke tests are deterministic and never spend API credit.
    decision = IntentAgent(api_key=None).analyze(customer)
    message = MessagingAgent().generate(customer, decision)

    assert customer.name == "Alice"
    assert decision.should_contact is True
    assert decision.action == "offer_pro_plan"
    assert message.startswith("Hi Alice,")

    print("PASS: Alice's event history produced a Pro plan outreach message.")


if __name__ == "__main__":
    main()
