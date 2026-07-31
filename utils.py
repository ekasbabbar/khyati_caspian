"""Display helpers for the Khyati console experience."""

from models import Customer, IntentDecision

EVENT_LABELS: dict[str, str] = {
    "signup": "Signup",
    "email_verified": "Verified Email",
    "created_project": "Created Project",
    "imported_records": "Imported Records",
    "invited_teammate": "Invited Teammate",
    "completed_workflow": "Completed Workflow",
    "pricing_page": "Viewed Pricing",
    "payment_failed": "Payment Failed",
    "inactive_14_days": "Inactive 14 Days",
    "login": "Login",
}


def event_label(event_type: str) -> str:
    """Return a human-readable label for an event type."""
    return EVENT_LABELS.get(event_type, event_type.replace("_", " ").title())


def print_timeline(customer: Customer) -> None:
    """Print the customer's activity timeline."""
    print("\nTimeline\n")
    for event in customer.events:
        time_str = event.timestamp.strftime("%H:%M")
        print(f"{time_str} {event_label(event.type)}")


def print_decision(customer: Customer, decision: IntentDecision) -> None:
    """Print a formatted intent decision block."""
    contact_label = "CONTACT" if decision.should_contact else "NO CONTACT"
    confidence_pct = f"{decision.confidence * 100:.0f}%"

    print("\n" + "━" * 26)
    print("\nKHYATI DECISION\n")
    print(f"Customer:\n{customer.name}\n")
    print(f"Decision:\n{contact_label}\n")
    print(f"Confidence:\n{confidence_pct}\n")
    print(f"Reason:\n{decision.reason}\n")

    if decision.should_contact:
        channel = decision.recommended_channel or "Not specified"
        objective = decision.objective or "Provide helpful outreach"
        print(f"Channel:\n{channel.title()}\n")
        print(f"Objective:\n{objective}.\n")

    print("━" * 26)
