"""Intent reasoning agent — decides whether to proactively contact a user.

AI logic will be implemented in a later iteration.
"""

from models import Event


class IntentAgent:
    """Evaluates user activity and produces outreach decisions."""

    def evaluate(self, events: list[Event]) -> None:
        """Analyze events and decide whether proactive contact is warranted.

        Not implemented yet — placeholder for future LLM-backed reasoning.
        """
        raise NotImplementedError("IntentAgent.evaluate() is not implemented yet.")
