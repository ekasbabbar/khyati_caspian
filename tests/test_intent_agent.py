"""Tests for Khyati's deterministic career-intent fallback."""
from datetime import datetime
import unittest
from intent_agent import IntentAgent
from models import CareerDecision, InteractionEvent, RecruiterLead
from pydantic import ValidationError

def lead_with(*types):
    return RecruiterLead(id="r1", name="Recruiter", email="r@example.com", company="Acme", events=[InteractionEvent(type=t,timestamp=datetime(2026,8,2,9,i)) for i,t in enumerate(types)])

class IntentAgentTests(unittest.TestCase):
    def setUp(self): self.agent = IntentAgent()
    def test_project_question_gets_email_reply(self):
        d=self.agent.analyze(lead_with("project_question")); self.assertTrue(d.should_respond); self.assertFalse(d.should_notify_owner); self.assertEqual(d.recommended_channel,"email")
    def test_interview_replies_and_notifies(self):
        d=self.agent.analyze(lead_with("interview_requested")); self.assertTrue(d.should_respond); self.assertTrue(d.should_notify_owner); self.assertEqual(d.recommended_channel,"telegram")
    def test_compensation_requires_owner(self): self.assertTrue(self.agent.analyze(lead_with("compensation_question")).should_notify_owner)
    def test_unrelated_gets_no_action(self):
        d=self.agent.analyze(lead_with("unrelated")); self.assertFalse(d.should_respond); self.assertFalse(d.should_notify_owner)
    def test_interview_has_priority(self): self.assertEqual(self.agent.analyze(lead_with("project_question","interview_requested")).action,"request_interview_approval")
    def test_confidence_is_bounded(self):
        with self.assertRaises(ValidationError): CareerDecision(should_respond=False,should_notify_owner=False,confidence=1.1,recruiter_intent="unrelated",reason="invalid")
    def test_actionable_requires_details(self):
        with self.assertRaises(ValidationError): CareerDecision(should_respond=True,should_notify_owner=False,confidence=.8,recruiter_intent="general_inquiry",reason="reply")

if __name__ == "__main__": unittest.main()
