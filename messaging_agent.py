"""Template-based message generation — no Caspian yet."""

from models import Customer, IntentDecision


class MessagingAgent:
    """Composes proactive outreach messages from intent decisions."""

    def generate(self, customer: Customer, decision: IntentDecision) -> str:
        """Build a message tailored to the customer and decision objective."""
        if not decision.should_contact:
            return ""

        templates: dict[str, str] = {
            "Offer Pro plan": (
                f"Hi {customer.name},\n\n"
                "Looks like your team is growing.\n\n"
                "If you'd like, I'd be happy to explain how the Pro plan could help."
            ),
            "Resolve payment issue": (
                f"Hi {customer.name},\n\n"
                "It looks like your recent payment didn't go through.\n\n"
                "I'm here to help if you'd like assistance completing checkout."
            ),
            "Re-engage customer": (
                f"Hi {customer.name},\n\n"
                "We noticed you haven't been around lately.\n\n"
                "If anything blocked you from getting started, I'm happy to help."
            ),
            "Offer plan guidance": (
                f"Hi {customer.name},\n\n"
                "You've been exploring our plans — happy to walk you through "
                "which option fits your team best."
            ),
        }

        return templates.get(
            decision.objective,
            f"Hi {customer.name},\n\n{decision.reason}",
        )
