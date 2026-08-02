"""Deterministic previews for recruiter and owner messages."""

from models import CareerDecision, RecruiterLead


class MessagingAgent:
    def generate(self, lead: RecruiterLead, decision: CareerDecision) -> str:
        if not decision.should_respond and not decision.should_notify_owner:
            return ""

        if decision.should_notify_owner:
            company = lead.company or "an unspecified company"
            return (
                f"Recruiter alert: {lead.name} from {company} contacted Khyati.\n\n"
                f"Intent: {decision.recruiter_intent.replace('_', ' ').title()}\n"
                f"Reason: {decision.reason}\n\n"
                "Review the request before Khyati makes any commitment."
            )

        return (
            f"Hi {lead.name},\n\n"
            "Thanks for reaching out. I’m Khyati, the candidate’s AI career "
            "representative. I can answer using verified career information "
            "and involve the candidate whenever approval is needed.\n\n"
            f"Objective: {decision.objective}."
        )
