"""Offline tests for AI reasoning and Caspian's shared handler."""
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import StringIO
from threading import Lock
from time import sleep
from types import SimpleNamespace
import unittest

from channels import build_handler, connect_available_channels
from conversation_memory import ConversationMemory
from intent_agent import IntentAgent
from models import CareerDecision, InteractionEvent, RecruiterLead
from reply_agent import ReplyAgent
from knowledge_retriever import RetrievalResult

def sample_lead():
    return RecruiterLead(id="r1",name="Priya",email="p@example.com",events=[InteractionEvent(type="project_question",timestamp=datetime(2026,8,2,9))])

class FakeCompletions:
    def __init__(self, decision=None, reply="How can I help?", error=None): self.decision,self.reply,self.error=decision,reply,error; self.last_kwargs=None
    def create(self, **kwargs):
        self.last_kwargs=kwargs
        if self.error: raise self.error
        content=self.decision.model_dump_json() if self.decision else self.reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
class TrackingCompletions:
    def __init__(self): self.active=0; self.high_water_mark=0; self.lock=Lock()
    def create(self, **kwargs):
        with self.lock: self.active+=1; self.high_water_mark=max(self.high_water_mark,self.active)
        try:
            sleep(.02); return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Happy to help."))])
        finally:
            with self.lock: self.active-=1
class FakeOpenAI:
    def __init__(self, completions): self.chat=SimpleNamespace(completions=completions)
class FakeMessage:
    def __init__(self, channel, text="Can you tell me about the project?", conversation_id="c1", sender="recruiter@example.com"):
        self.channel,self.text,self.conversation_id=channel,text,conversation_id; self.sender={"address":sender}; self.replies=[]
    def reply(self,text): self.replies.append(text)
class StubReplyAgent:
    def __init__(self): self.channels=[]; self.histories=[]
    def respond(self,text,channel,history=None): self.channels.append(channel); self.histories.append(history or []); return f"Helpful reply on {channel}"
class FailingReplyAgent:
    def respond(self,*args,**kwargs): raise RuntimeError("model unavailable")
class StubRetriever:
    def __init__(self): self.audiences=[]
    def search(self,query,audience="recruiter",**kwargs):
        self.audiences.append(audience)
        return RetrievalResult("[SOURCE: skills.md]\nPython\n[END SOURCE]",("skills.md#Python",),())
class FakeCaspianClient:
    def __init__(self,email_error=None,telegram_error=None): self.email_error=email_error; self.telegram_error=telegram_error; self.sent=[]
    def connect_email(self,**kwargs):
        if self.email_error: raise self.email_error
        return {"id":"email-1","address":"khyati@example.com"}
    def connect_telegram(self,**kwargs):
        if self.telegram_error: raise self.telegram_error
        return {"id":"telegram-1","address":"@khyati_bot"}
    def send_message(self,conversation_id,**kwargs): self.sent.append((conversation_id,kwargs["text"]))
SETTINGS=SimpleNamespace(caspian_email_username="khyati",caspian_telegram_bot_token="token")

class AIIntentTests(unittest.TestCase):
    def test_structured_llm_decision_is_used(self):
        expected=CareerDecision(should_respond=False,should_notify_owner=False,confidence=.84,recruiter_intent="unrelated",reason="Not career-related.")
        self.assertEqual(IntentAgent(client=FakeOpenAI(FakeCompletions(decision=expected))).analyze(sample_lead()),expected)
    def test_rule_fallback_when_llm_fails(self):
        with self.assertLogs("intent_agent",level="ERROR"):
            decision=IntentAgent(client=FakeOpenAI(FakeCompletions(error=RuntimeError("API unavailable")))).analyze(sample_lead())
        self.assertTrue(decision.should_respond)

class ReplyAgentTests(unittest.TestCase):
    def test_returns_model_text(self):
        agent=ReplyAgent(api_key="test",model="test",client=FakeOpenAI(FakeCompletions(reply="Verified project details.")))
        self.assertEqual(agent.respond("Tell me more","email"),"Verified project details.")
    def test_knowledge_and_channel_role_reach_model(self):
        completions=FakeCompletions(reply="Assessment")
        agent=ReplyAgent(api_key="test",model="test",client=FakeOpenAI(completions),retriever=StubRetriever())
        with redirect_stdout(StringIO()): agent.respond("data analyst intern","email")
        messages=completions.last_kwargs["messages"]
        self.assertIn("[SOURCE: skills.md]",messages[0]["content"])
        self.assertIn("external recruiter",messages[-1]["content"])
    def test_telegram_is_identified_as_owner_channel(self):
        completions=FakeCompletions(reply="Owner assessment")
        agent=ReplyAgent(api_key="test",model="test",client=FakeOpenAI(completions))
        agent.respond("product management intern","telegram")
        self.assertIn("candidate owner",completions.last_kwargs["messages"][-1]["content"])
    def test_retrieval_uses_channel_audience(self):
        completions=FakeCompletions(reply="Assessment"); retriever=StubRetriever()
        agent=ReplyAgent(api_key="test",model="test",client=FakeOpenAI(completions),retriever=retriever)
        with redirect_stdout(StringIO()): agent.respond("role","email"); agent.respond("role","telegram")
        self.assertEqual(retriever.audiences,["recruiter","owner"])
    def test_concurrency_is_bounded(self):
        completions=TrackingCompletions(); agent=ReplyAgent(api_key="test",model="test",client=FakeOpenAI(completions),max_concurrent=2)
        with ThreadPoolExecutor(max_workers=6) as pool: replies=list(pool.map(lambda _:agent.respond("Help","telegram"),range(6)))
        self.assertEqual(replies,["Happy to help."]*6); self.assertEqual(completions.high_water_mark,2)

class SharedHandlerTests(unittest.TestCase):
    def test_one_handler_serves_both_channels(self):
        agent=StubReplyAgent(); handler=build_handler(agent)
        email,telegram=FakeMessage("email"),FakeMessage("telegram")
        with redirect_stdout(StringIO()): handler(email); handler(telegram)
        self.assertEqual(agent.channels,["email","telegram"])
    def test_failure_sends_safe_fallback(self):
        message=FakeMessage("email")
        with redirect_stdout(StringIO()): build_handler(FailingReplyAgent())(message)
        self.assertIn("message has been received",message.replies[0])
    def test_context_is_remembered(self):
        agent=StubReplyAgent(); handler=build_handler(agent)
        with redirect_stdout(StringIO()): handler(FakeMessage("email",text="First")); handler(FakeMessage("email",text="Second"))
        self.assertEqual(agent.histories[1][0]["content"],"First")
    def test_telegram_rejects_non_owner(self):
        message=FakeMessage("telegram",sender="intruder")
        with redirect_stdout(StringIO()): build_handler(StubReplyAgent(),owner_telegram_username="@owner")(message)
        self.assertEqual(message.replies,["This is a private career-agent channel."])
    def test_email_notifies_known_owner_conversation(self):
        client=FakeCaspianClient(); handler=build_handler(StubReplyAgent(),client=client,owner_telegram_username="@owner")
        with redirect_stdout(StringIO()): handler(FakeMessage("telegram",sender="@owner",conversation_id="owner-chat")); handler(FakeMessage("email"))
        self.assertEqual(client.sent[0][0],"owner-chat")

class ChannelConnectionTests(unittest.TestCase):
    def test_email_survives_telegram_failure(self):
        with redirect_stdout(StringIO()): connected=connect_available_channels(FakeCaspianClient(telegram_error=RuntimeError("down")),SETTINGS)
        self.assertEqual(set(connected),{"email"})
    def test_both_fail_stops_startup(self):
        with redirect_stdout(StringIO()), self.assertRaises(RuntimeError): connect_available_channels(FakeCaspianClient(RuntimeError("down"),RuntimeError("down")),SETTINGS)

class ConversationMemoryTests(unittest.TestCase):
    def test_history_is_bounded(self):
        memory=ConversationMemory(max_messages=2); memory.add("c","user","one"); memory.add("c","assistant","two"); memory.add("c","user","three")
        self.assertEqual([m["content"] for m in memory.history("c")],["two","three"])

if __name__ == "__main__": unittest.main()
