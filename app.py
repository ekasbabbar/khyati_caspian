"""Khyati entry point."""

import sys

from config import get_settings
from event_store import EventStore
from intent_agent import IntentAgent
from messaging_agent import MessagingAgent
from utils import print_decision, print_timeline


def main() -> None:
    """Run the full Khyati loop: load → analyze → message."""
    # Windows may otherwise select a legacy encoding that cannot print the
    # checkmark and box-drawing characters used by the product demo.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()

    print("\nLoading customer...")
    store = EventStore(settings.events_path)
    customer = store.load()
    print(f"\n✓ Loaded {customer.name}")

    print_timeline(customer)

    print("\nAnalyzing customer intent...")
    intent_agent = IntentAgent(
        api_key=settings.llm_api_key if settings.use_llm else None,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        provider=settings.llm_provider,
    )
    decision = intent_agent.analyze(customer)
    print(f"Brain: {intent_agent.last_source}")
    print_decision(customer, decision)

    if decision.should_contact:
        print("\nGenerating message...\n")
        message = MessagingAgent().generate(customer, decision)
        print(message)


if __name__ == "__main__":
    main()
