"""Messaging agent — sends proactive outreach to users.

Caspian SDK integration will be added in a later iteration.
"""

from models import Customer


class MessagingAgent:
    """Composes and delivers messages to customers."""

    def send(self, customer: Customer, message: str) -> None:
        """Send a proactive message to a customer.

        Not implemented yet — placeholder for future Caspian integration.
        """
        raise NotImplementedError("MessagingAgent.send() is not implemented yet.")
