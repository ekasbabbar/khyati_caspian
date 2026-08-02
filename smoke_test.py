"""Deterministic end-to-end check of Khyati's career-agent loop."""
from config import get_settings
from event_store import EventStore
from intent_agent import IntentAgent
from messaging_agent import MessagingAgent

def main():
    lead = EventStore(get_settings().events_path).load()
    decision = IntentAgent(api_key=None).analyze(lead)
    message = MessagingAgent().generate(lead, decision)
    assert decision.should_notify_owner is True
    assert decision.action == "request_interview_approval"
    assert message.startswith("Recruiter alert:")
    print("PASS: recruiter interview request produced an owner approval alert.")

if __name__ == "__main__": main()
