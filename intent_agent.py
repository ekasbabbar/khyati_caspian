"""Rule-based intent engine — decides whether to proactively contact a user."""

from collections import Counter

from models import Customer, IntentDecision


class IntentAgent:
    """Evaluates customer activity and produces outreach decisions."""

    def analyze(self, customer: Customer) -> IntentDecision:
        """Apply outreach rules to a customer's event history."""
        counts = Counter(event.type for event in customer.events)
        types = set(counts)

        # payment_failed — contact immediately
        if "payment_failed" in types:
            return IntentDecision(
                should_contact=True,
                confidence=0.97,
                reason="Payment failed — customer may need help completing checkout.",
                objective="Resolve payment issue",
                recommended_channel="email",
            )

        # inactive_14_days — re-engage
        if "inactive_14_days" in types:
            return IntentDecision(
                should_contact=True,
                confidence=0.88,
                reason="Customer has been inactive for 14 days.",
                objective="Re-engage customer",
                recommended_channel="email",
            )

        # pricing_page ×3 — sustained purchase intent
        if counts.get("pricing_page", 0) >= 3:
            return IntentDecision(
                should_contact=True,
                confidence=0.91,
                reason="User has repeatedly viewed pricing, showing sustained purchase intent.",
                objective="Offer plan guidance",
                recommended_channel="email",
            )

        # invited teammate(s) + pricing — upsell.
        # One invitation is intentional: it powers the sample vertical slice.
        if counts.get("invited_teammate", 0) >= 1 and "pricing_page" in types:
            return IntentDecision(
                should_contact=True,
                confidence=0.82,
                reason="User appears to be evaluating paid plans after collaborating with teammates.",
                objective="Offer Pro plan",
                recommended_channel="email",
            )

        # signup only — don't contact
        if types == {"signup"}:
            return IntentDecision(
                should_contact=False,
                confidence=0.93,
                reason="Customer just signed up — give them space to explore.",
                objective="",
                recommended_channel="",
            )

        return IntentDecision(
            should_contact=False,
            confidence=0.60,
            reason="No outreach triggers detected.",
            objective="",
            recommended_channel="",
        )
