"""Console display helpers for Khyati's recruiter workflow."""

from models import CareerDecision, RecruiterLead

EVENT_LABELS = {
    "general_recruiter_inquiry": "Recruiter Inquiry",
    "portfolio_viewed": "Viewed Portfolio",
    "resume_requested": "Requested Resume",
    "project_question": "Asked About Project",
    "availability_question": "Asked About Availability",
    "interview_requested": "Requested Interview",
    "compensation_question": "Asked About Compensation",
    "direct_contact_requested": "Requested Direct Contact",
}


def event_label(event_type: str) -> str:
    return EVENT_LABELS.get(event_type, event_type.replace("_", " ").title())


def print_timeline(lead: RecruiterLead) -> None:
    print("\nInteraction Timeline\n")
    for event in lead.events:
        print(f"{event.timestamp:%H:%M} {event_label(event.type)}")


def print_decision(lead: RecruiterLead, decision: CareerDecision) -> None:
    if decision.should_respond and decision.should_notify_owner:
        action = "RESPOND + NOTIFY OWNER"
    elif decision.should_respond:
        action = "RESPOND"
    elif decision.should_notify_owner:
        action = "NOTIFY OWNER"
    else:
        action = "NO ACTION"

    print("\n" + "━" * 34)
    print("\nKHYATI CAREER DECISION\n")
    print(f"Recruiter:\n{lead.name}")
    if lead.company:
        print(f"\nCompany:\n{lead.company}")
    print(f"\nDecision:\n{action}")
    print(f"\nIntent:\n{decision.recruiter_intent.replace('_', ' ').title()}")
    print(f"\nConfidence:\n{decision.confidence * 100:.0f}%")
    print(f"\nReason:\n{decision.reason}")
    if decision.should_respond or decision.should_notify_owner:
        print(f"\nChannel:\n{(decision.recommended_channel or 'unspecified').title()}")
        print(f"\nObjective:\n{decision.objective or 'Handle the recruiter request safely.'}")
    print("\n" + "━" * 34)
