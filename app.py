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
    decision = IntentAgent().analyze(customer)
    print_decision(customer, decision)

    if decision.should_contact:
        print("\nGenerating message...\n")
        message = MessagingAgent().generate(customer, decision)
        print(message)


if __name__ == "__main__":
    main()
