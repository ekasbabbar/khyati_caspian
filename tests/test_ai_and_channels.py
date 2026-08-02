"""Offline tests for AI reasoning and Caspian's shared handler."""
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import StringIO
from pathlib import Path
from threading import Lock
from time import sleep
from types import SimpleNamespace
import re
import tempfile
import unittest

from approval_store import ApprovalStore
from channels import (
    EmailThreadRegistry,
    OwnerChannelRegistry,
    build_handler,
    connect_available_channels,
    is_scheduling_request,
)
from conversation_memory import ConversationMemory
from intent_agent import IntentAgent
from models import CareerDecision, InteractionEvent, RecruiterLead
from reply_agent import (
    ReplyAgent,
    _clean_email_message,
    _clean_model_reply,
    _retrieval_queries,
)
from knowledge_retriever import RetrievalResult
from outbound_store import OutboundDraftStore

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
    def initiate(self,connection_id,recipient,text): self.sent.append((connection_id,recipient,text)); return {"id":"new-conversation"}
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
    def test_system_prompt_requires_truthful_advocacy(self):
        completions=FakeCompletions(reply="Strong, grounded answer")
        agent=ReplyAgent(api_key="test",model="test",client=FakeOpenAI(completions))
        agent.respond("Would this candidate fit?","email")
        prompt=completions.last_kwargs["messages"][0]["content"]
        self.assertIn("active advocate",prompt)
        self.assertIn("strongest truthful light",prompt)
        self.assertIn("concrete",prompt)
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
    def test_email_signature_is_removed_before_retrieval(self):
        cleaned=_clean_email_message("Tell me about AI agents.\n\nBest regards,\nRecruiter\nIIT Guwahati")
        self.assertEqual(cleaned,"Tell me about AI agents.")
    def test_subject_and_signature_are_removed_from_model_reply(self):
        cleaned=_clean_model_reply("Subject: Re: AI work\n\nDirect answer.\n\nBest regards,\nKhyati")
        self.assertEqual(cleaned,"Direct answer.")
    def test_model_reasoning_is_removed_from_reply(self):
        cleaned=_clean_model_reply("<think>private reasoning</think>\nUseful answer")
        self.assertEqual(cleaned,"Useful answer")
    def test_unterminated_reasoning_is_rejected(self):
        self.assertEqual(_clean_model_reply("<think>unfinished reasoning"),"")
    def test_multi_question_email_is_decomposed(self):
        questions=_retrieval_queries(
            "Could you tell me:\nWho is Ekas?\nWhat has he built?\nWhy is he a fit?"
        )
        self.assertEqual(len(questions),3)
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
    def test_owner_conversation_survives_registry_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"owner.json"
            first=OwnerChannelRegistry(path); first.set("owner-chat")
            second=OwnerChannelRegistry(path)
            self.assertEqual(second.get(),"owner-chat")
    def test_missing_owner_conversation_prints_warning(self):
        client=FakeCaspianClient()
        with redirect_stdout(StringIO()) as output:
            build_handler(StubReplyAgent(),client=client)(FakeMessage("email"))
        self.assertIn("owner notification skipped",output.getvalue())
    def test_interview_request_creates_owner_approval(self):
        client=FakeCaspianClient(); registry=OwnerChannelRegistry(); registry.set("owner-chat")
        store=ApprovalStore()
        handler=build_handler(StubReplyAgent(),client=client,owner_registry=registry,approval_store=store)
        email=FakeMessage("email",text="We are hiring for an AI internship. Can we schedule an interview tomorrow at 3 PM IST?",conversation_id="email-thread")
        with redirect_stdout(StringIO()): handler(email)
        self.assertEqual(len(store.pending()),1)
        self.assertEqual(client.sent[0][0],"owner-chat")
        self.assertIn("INTERVIEW APPROVAL",client.sent[0][1])
    def test_owner_approval_updates_original_email_thread(self):
        client=FakeCaspianClient(); registry=OwnerChannelRegistry(); registry.set("owner-chat")
        store=ApprovalStore(); request=store.create("email-thread","john@example.com","John","Interview tomorrow")
        handler=build_handler(StubReplyAgent(),client=client,owner_telegram_username="@owner",owner_registry=registry,approval_store=store)
        command=FakeMessage("telegram",text=f"approve {request.id} tomorrow at 3:00 PM IST",sender="@owner",conversation_id="owner-chat")
        with redirect_stdout(StringIO()): handler(command)
        self.assertEqual(client.sent[0][0],"email-thread")
        self.assertIn("confirmed",client.sent[0][1])
        self.assertEqual(store.get(request.id).status,"approved")
        self.assertIn("recruiter thread was updated",command.replies[0])
    def test_approval_without_exact_time_requests_one(self):
        client=FakeCaspianClient(); store=ApprovalStore(); request=store.create("email-thread","john@example.com","John","Between 2 and 5")
        handler=build_handler(StubReplyAgent(),client=client,owner_telegram_username="@owner",approval_store=store)
        command=FakeMessage("telegram",text=f"approve {request.id}",sender="@owner")
        with redirect_stdout(StringIO()): handler(command)
        self.assertIn("exact time",command.replies[0])
        self.assertEqual(client.sent,[])

    def test_scheduling_detection_requires_professional_time_request(self):
        self.assertTrue(is_scheduling_request("Hiring AI interns; can we schedule an interview tomorrow at 3 PM?"))
        self.assertFalse(is_scheduling_request("I may schedule an interview after learning more."))
    def test_owner_can_confirm_cold_start_email_draft(self):
        client=FakeCaspianClient(); drafts=OutboundDraftStore()
        handler=build_handler(StubReplyAgent(),client=client,owner_telegram_username="@owner",outbound_store=drafts,email_connection_id="email-1")
        draft_message=FakeMessage("telegram",text="ask person@example.com if she is available for a call in 15 minutes?",sender="@owner")
        with redirect_stdout(StringIO()): handler(draft_message)
        self.assertIn("Reply `send OUT-",draft_message.replies[0])
        draft_id=re.search(r"OUT-[A-F0-9]{6}",draft_message.replies[0]).group(0)
        send_message=FakeMessage("telegram",text=f"send {draft_id}",sender="@owner")
        with redirect_stdout(StringIO()): handler(send_message)
        self.assertEqual(client.sent[0][0],"email-1")
        self.assertEqual(client.sent[0][1],"person@example.com")
        self.assertIn("Would you be available",client.sent[0][2])
    def test_owner_can_cancel_outbound_draft(self):
        client=FakeCaspianClient(); drafts=OutboundDraftStore(); draft=drafts.create("person@example.com","Hello")
        handler=build_handler(StubReplyAgent(),client=client,owner_telegram_username="@owner",outbound_store=drafts,email_connection_id="email-1")
        message=FakeMessage("telegram",text=f"cancel {draft.id}",sender="@owner")
        with redirect_stdout(StringIO()): handler(message)
        self.assertEqual(client.sent,[]); self.assertIn("nothing was sent",message.replies[0])
    def test_owner_outbound_reuses_known_email_thread(self):
        client=FakeCaspianClient(); drafts=OutboundDraftStore(); threads=EmailThreadRegistry()
        threads.set("person@example.com","existing-thread")
        draft=drafts.create("person@example.com","Can you meet tomorrow?")
        handler=build_handler(StubReplyAgent(),client=client,owner_telegram_username="@owner",outbound_store=drafts,email_connection_id="email-1",email_threads=threads)
        message=FakeMessage("telegram",text=f"send {draft.id}",sender="@owner")
        with redirect_stdout(StringIO()): handler(message)
        self.assertEqual(client.sent[0][0],"existing-thread")
        self.assertEqual(len(client.sent[0]),2)

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
