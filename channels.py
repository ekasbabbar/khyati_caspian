"""Run Khyati on Email and Telegram through one Caspian handler."""

import json
from pathlib import Path
import re
from threading import Lock

from approval_store import ApprovalStore, PendingApproval
from config import get_settings
from conversation_memory import ConversationMemory
from knowledge_retriever import KnowledgeRetriever
from llm_provider import build_provider_chain
from outbound_store import OutboundDraftStore
from reply_agent import ReplyAgent


def is_scheduling_request(text: str) -> bool:
    """Recognize professional meeting requests that require owner approval."""
    lowered = text.lower()
    professional = re.search(r"\b(interview|recruiter|hiring|role|intern(?:ship)?)\b", lowered)
    scheduling = re.search(r"\b(schedule|book|meeting|conversation|call|availability|available)\b", lowered)
    timing = re.search(
        r"\b(today|tomorrow|next week|monday|tuesday|wednesday|thursday|friday|"
        r"saturday|sunday|between|(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s*(?:am|pm|ist))\b",
        lowered,
    )
    return bool(professional and scheduling and timing)


def approval_alert(item: PendingApproval) -> str:
    excerpt = item.request_text[:1200]
    return (
        f"INTERVIEW APPROVAL {item.id}\n\n"
        f"From: {item.recruiter_name} <{item.recruiter_address}>\n\n"
        f"{excerpt}\n\n"
        "Reply with one of:\n"
        f"approve {item.id} at <exact time and timezone>\n"
        f"decline {item.id}\n"
        f"counter {item.id} <alternative times>\n"
        "Send `pending` to list open requests."
    )


def _select_request(text: str, store: ApprovalStore) -> PendingApproval | None:
    match = re.search(r"\bINT-[A-F0-9]{6}\b", text, re.IGNORECASE)
    if match:
        return store.get(match.group(0))
    pending = store.pending()
    return pending[0] if len(pending) == 1 else None


def handle_owner_approval(text: str, message, client, store: ApprovalStore) -> bool:
    """Handle deterministic owner commands and update the original email thread."""
    lowered = text.lower().strip()
    pending = store.pending()
    if lowered in {"pending", "requests", "pending requests", "recruiter mail"} or re.search(
        r"\b(any|new)\s+(?:recruiter\s+)?(?:mail|request|interview)s?\b", lowered
    ):
        if not pending:
            message.reply("There are no pending recruiter approvals.")
        else:
            summary = "\n\n".join(
                f"{item.id} — {item.recruiter_name} <{item.recruiter_address}>\n"
                f"{item.request_text[:350]}"
                for item in pending
            )
            message.reply(f"Pending recruiter approvals:\n\n{summary}")
        return True

    action_match = re.search(
        r"\b(approve|approved|confirm|confirmed|schedule|decline|declined|deny|"
        r"counter|counter-propose|reschedule)\b",
        lowered,
    )
    if not action_match:
        return False
    item = _select_request(text, store)
    if item is None:
        if not pending:
            message.reply("There is no pending recruiter request to update.")
        else:
            ids = ", ".join(request.id for request in pending)
            message.reply(f"Please include the request ID. Pending: {ids}")
        return True
    if item.status != "pending":
        message.reply(f"{item.id} has already been {item.status}.")
        return True

    action = action_match.group(1)
    if action in {"approve", "approved", "confirm", "confirmed", "schedule"}:
        time_match = re.search(
            r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|"
            r"saturday|sunday)?\s*(?:at\s+)?(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s*"
            r"(?:am|pm)(?:\s+[A-Z]{2,5})?\b",
            text,
            re.IGNORECASE,
        )
        if not time_match:
            message.reply(
                f"Please give an exact time and timezone, for example: "
                f"approve {item.id} tomorrow at 3:00 PM IST"
            )
            return True
        chosen_time = time_match.group(0).strip()
        email_text = (
            f"Hi {item.recruiter_name},\n\n"
            f"Ekas has confirmed that {chosen_time} works for the introductory "
            "conversation. Please send the calendar invitation and meeting link "
            "to this email thread.\n\nKhyati\nAI Career Representative"
        )
        status = "approved"
    elif action in {"decline", "declined", "deny"}:
        email_text = (
            f"Hi {item.recruiter_name},\n\n"
            "Ekas is unable to attend during the proposed window. If useful, "
            "please share a few alternative times and I will route them for approval."
            "\n\nKhyati\nAI Career Representative"
        )
        status = "declined"
    else:
        detail = re.sub(r"(?i)^.*?\b(?:counter|counter-propose|reschedule)\b", "", text).strip()
        detail = re.sub(r"(?i)^INT-[A-F0-9]{6}\b", "", detail).strip(" :-")
        if not detail:
            message.reply(f"Provide alternative times after `counter {item.id}`.")
            return True
        email_text = (
            f"Hi {item.recruiter_name},\n\n"
            f"Ekas cannot confirm the original window. His suggested alternative is: "
            f"{detail}\n\nPlease let me know whether that works.\n\n"
            "Khyati\nAI Career Representative"
        )
        status = "counter_proposed"

    try:
        client.send_message(item.email_conversation_id, text=email_text)
    except Exception as error:
        message.reply(f"I could not update the recruiter thread: {error}")
        return True
    store.resolve(item.id, status)
    message.reply(f"Done. {item.id} was {status.replace('_', ' ')} and the recruiter thread was updated.")
    print(f"   Approval {item.id}: {status}; recruiter email thread updated.")
    return True


class EmailThreadRegistry:
    """Remember existing email threads by sender address."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = Lock()
        self._threads = self._load()

    def _load(self) -> dict[str, str]:
        if self._path is None or not self._path.is_file():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            return {
                str(address).lower(): str(conversation_id)
                for address, conversation_id in payload.get("threads", {}).items()
            }
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    def set(self, address: str, conversation_id: str) -> None:
        with self._lock:
            self._threads[address.lower()] = conversation_id
            if self._path is not None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps({"threads": self._threads}, indent=2),
                    encoding="utf-8",
                )
                temporary.replace(self._path)

    def get(self, address: str) -> str | None:
        with self._lock:
            return self._threads.get(address.lower())


def handle_owner_outbound(
    text: str,
    message,
    client,
    email_connection_id: str | None,
    store: OutboundDraftStore,
    email_threads: EmailThreadRegistry,
) -> bool:
    """Draft and confirm owner-directed cold-start email messages."""
    send_match = re.fullmatch(r"\s*send\s+(OUT-[A-F0-9]{6})\s*", text, re.IGNORECASE)
    cancel_match = re.fullmatch(r"\s*cancel\s+(OUT-[A-F0-9]{6})\s*", text, re.IGNORECASE)
    if send_match or cancel_match:
        draft_id = (send_match or cancel_match).group(1).upper()
        draft = store.get(draft_id)
        if draft is None or draft.status != "draft":
            message.reply(f"No open outbound draft named {draft_id}.")
            return True
        if cancel_match:
            store.resolve(draft_id, "cancelled")
            message.reply(f"Cancelled {draft_id}; nothing was sent.")
            return True
        existing_thread = email_threads.get(draft.recipient)
        if not existing_thread and not email_connection_id:
            message.reply("Email initiation is unavailable because no Email connection is active.")
            return True
        try:
            if existing_thread:
                client.send_message(existing_thread, text=draft.text)
            else:
                client.initiate(email_connection_id, draft.recipient, draft.text)
        except Exception as error:
            message.reply(f"The email could not be sent: {error}")
            return True
        store.resolve(draft_id, "sent")
        message.reply(f"Sent {draft_id} to {draft.recipient}.")
        print(f"   Owner-authorized outbound email {draft_id} sent to {draft.recipient}.")
        return True

    email_match = re.match(
        r"(?is)^\s*(?:please\s+)?(?:email|mail|ask)\s+"
        r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\s*[:,]?\s*(.+)$",
        text,
        re.IGNORECASE,
    )
    if not email_match:
        return False
    recipient, instruction = email_match.group(1), email_match.group(2).strip()
    instruction = re.sub(r"(?i)^(?:and\s+)?(?:ask|tell)\s+(?:her|him|them)\s+", "", instruction)
    if re.match(r"(?i)^if\s+(?:she|he|they)\s+is\s+", instruction):
        instruction = re.sub(r"(?i)^if\s+(?:she|he|they)\s+is\s+", "Would you be ", instruction)
    elif re.match(r"(?i)^that\s+", instruction):
        instruction = re.sub(r"(?i)^that\s+", "", instruction)
    body = (
        "Hi,\n\n"
        f"Ekas asked me to reach out: {instruction.strip()}\n\n"
        "Please reply to this email if you would like me to pass a response back to him.\n\n"
        "Khyati\nAI Representative for Ekas"
    )
    draft = store.create(recipient, body)
    message.reply(
        f"Outbound draft {draft.id}\n\nTo: {recipient}\n\n{body}\n\n"
        f"Reply `send {draft.id}` to send it, or `cancel {draft.id}`."
    )
    return True


class OwnerChannelRegistry:
    """Persist the verified owner's Caspian conversation across restarts."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = Lock()
        self._conversation_id = self._load()

    def _load(self) -> str | None:
        if self._path is None or not self._path.is_file():
            return None
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            value = payload.get("telegram_conversation_id")
            return value if isinstance(value, str) and value else None
        except (OSError, json.JSONDecodeError):
            return None

    def get(self) -> str | None:
        with self._lock:
            return self._conversation_id

    def set(self, conversation_id: str) -> None:
        with self._lock:
            self._conversation_id = conversation_id
            if self._path is not None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps({"telegram_conversation_id": conversation_id}),
                    encoding="utf-8",
                )
                temporary.replace(self._path)


def explain_connection_error(channel: str, error: Exception) -> str:
    """Turn common Caspian failures into actionable startup guidance."""
    error_name = type(error).__name__
    if error_name == "AccountRequiredError":
        return f"{channel}: Caspian login required. Run `caspian login`."
    if error_name == "InsufficientCreditError":
        return (
            f"{channel}: insufficient Caspian credit. Add credit or request "
            "hackathon starter credit."
        )
    return f"{channel}: connection failed ({error})."


def connect_available_channels(client, settings) -> dict[str, dict]:
    """Connect each channel independently so one failure does not stop the other."""
    connected: dict[str, dict] = {}

    try:
        connected["email"] = client.connect_email(
            username=settings.caspian_email_username
        )
    except Exception as error:
        print(f"WARNING: {explain_connection_error('Email', error)}")

    if not settings.caspian_telegram_bot_token:
        print("WARNING: Telegram: set TELEGRAM_BOT_TOKEN in .env.")
    else:
        try:
            connected["telegram"] = client.connect_telegram(
                bot_token=settings.caspian_telegram_bot_token
            )
        except Exception as error:
            print(f"WARNING: {explain_connection_error('Telegram', error)}")

    if not connected:
        raise RuntimeError(
            "Khyati could not connect Email or Telegram. Fix at least one "
            "connection and try again."
        )
    return connected


def build_handler(
    reply_agent: ReplyAgent,
    memory: ConversationMemory | None = None,
    client=None,
    owner_telegram_username: str | None = None,
    owner_registry: OwnerChannelRegistry | None = None,
    approval_store: ApprovalStore | None = None,
    outbound_store: OutboundDraftStore | None = None,
    email_connection_id: str | None = None,
    email_threads: EmailThreadRegistry | None = None,
):
    """Build the single normalized handler shared by every Caspian channel."""
    memory = memory or ConversationMemory()
    owner_registry = owner_registry or OwnerChannelRegistry()
    approval_store = approval_store or ApprovalStore()
    outbound_store = outbound_store or OutboundDraftStore()
    email_threads = email_threads or EmailThreadRegistry()
    expected_owner = (owner_telegram_username or "").strip().lower().lstrip("@")

    def handle(message) -> None:
        text = (message.text or "").strip()
        conversation_id = message.conversation_id
        sender = (message.sender or {}).get("address", "unknown")
        print(f"<- [{message.channel}] {sender}: {text}")

        if message.channel == "email" and sender != "unknown":
            email_threads.set(sender, conversation_id)

        if message.channel == "telegram":
            actual_sender = sender.strip().lower().lstrip("@")
            if expected_owner and actual_sender != expected_owner:
                message.reply("This is a private career-agent channel.")
                return
            owner_registry.set(conversation_id)
            print("   Owner Telegram conversation verified and saved.")

            if client and handle_owner_outbound(
                text,
                message,
                client,
                email_connection_id,
                outbound_store,
                email_threads,
            ):
                return
            if client and handle_owner_approval(text, message, client, approval_store):
                return

        if not text:
            message.reply("I received your message, but it did not include any text.")
            return

        approval_created = False
        if message.channel == "email" and client and is_scheduling_request(text):
            recruiter_name = (message.sender or {}).get("name") or sender.split("@", 1)[0]
            request = approval_store.create(
                email_conversation_id=conversation_id,
                recruiter_address=sender,
                recruiter_name=recruiter_name,
                request_text=text[:3000],
            )
            owner_conversation_id = owner_registry.get()
            if owner_conversation_id:
                try:
                    client.send_message(owner_conversation_id, text=approval_alert(request))
                    approval_created = True
                    print(f"   Created and sent interview approval {request.id}.")
                except Exception as error:
                    print(f"WARNING: interview approval notification failed ({error}).")
            else:
                print(
                    f"WARNING: interview approval {request.id} stored but Telegram "
                    "owner is not registered."
                )

        try:
            reply = reply_agent.respond(
                text=text,
                channel=message.channel,
                history=memory.history(conversation_id),
            )
        except Exception as error:
            print(f"WARNING: reply generation failed ({error}).")
            fallback = (
                "Thanks for reaching out. I'm having trouble generating a full "
                "response right now, but your message has been received. Please "
                "try again shortly."
            )
            message.reply(fallback)
            memory.add(conversation_id, "user", text)
            memory.add(conversation_id, "assistant", fallback)
            return

        message.reply(reply)
        memory.add(conversation_id, "user", text)
        memory.add(conversation_id, "assistant", reply)
        print(f"-> [{message.channel}] {reply}")

        owner_conversation_id = owner_registry.get()
        if (
            message.channel == "email"
            and client
            and owner_conversation_id
            and not approval_created
        ):
            try:
                client.send_message(
                    owner_conversation_id,
                    text=(
                        f"Recruiter message from {sender}:\n\n{text}\n\n"
                        "Khyati replied:\n\n"
                        f"{reply}"
                    ),
                )
            except Exception as error:
                print(f"WARNING: owner notification failed ({error}).")
        elif message.channel == "email" and client and not approval_created:
            print(
                "WARNING: owner notification skipped: no verified Telegram "
                "conversation is registered. Message the bot once from the "
                "configured owner account."
            )

    return handle


def main() -> None:
    settings = get_settings()
    if not settings.caspian_api_key:
        raise RuntimeError("Set CASPIAN_API_KEY in .env before running channels.py")
    if not settings.featherless_api_key and not settings.gemini_api_key:
        raise RuntimeError("Set FEATHERLESS_API_KEY or GEMINI_API_KEY in .env")
    if not settings.owner_telegram_username:
        raise RuntimeError(
            "Set KHYATI_OWNER_TELEGRAM_USERNAME in .env to secure Telegram."
        )

    from caspian_sdk import CommClient

    client = CommClient(
        api_key=settings.caspian_api_key,
        base_url=settings.caspian_base_url,
    )
    connected = connect_available_channels(client, settings)
    retriever = KnowledgeRetriever(
        settings.knowledge_dir,
        settings.knowledge_index_path,
    )
    print(
        f"Career knowledge indexed: {retriever.chunk_count} chunks from "
        f"{retriever.source_count} files at {settings.knowledge_dir.resolve()}"
    )

    try:
        behavior_prompt = client.behavior_prompt()
    except Exception as error:
        print(
            f"WARNING: channel behavior guide unavailable ({error}); "
            "using Khyati's base reply policy."
        )
        behavior_prompt = ""

    provider_chain = build_provider_chain(settings)
    print(f"LLM provider order: {' -> '.join(provider_chain.provider_names)}")
    reply_agent = ReplyAgent(
        api_key="provider-chain",
        model="provider-chain",
        max_concurrent=settings.llm_max_concurrent,
        behavior_prompt=behavior_prompt,
        retriever=retriever,
        client=provider_chain,
    )
    owner_registry = OwnerChannelRegistry(settings.owner_channel_state_path)
    approval_store = ApprovalStore(settings.approval_state_path)
    outbound_store = OutboundDraftStore(settings.outbound_state_path)
    email_threads = EmailThreadRegistry(settings.email_thread_state_path)
    if owner_registry.get():
        print("Owner Telegram conversation restored from local state.")
    else:
        print(
            "Owner Telegram conversation not registered yet. Message the bot "
            "once from the configured owner account to enable alerts."
        )
    pending_count = len(approval_store.pending())
    if pending_count:
        print(f"Pending recruiter approvals restored: {pending_count}")

    for channel, connection in connected.items():
        address = connection.get("address", connection.get("id", "active"))
        print(f"{channel.title()} active: {address}")
    unavailable = {"email", "telegram"} - connected.keys()
    if unavailable:
        print(f"Degraded mode: unavailable channel(s): {', '.join(sorted(unavailable))}")
    print("Khyati is listening. Press Ctrl+C to stop.")

    client.on_message(
        build_handler(
            reply_agent,
            client=client,
            owner_telegram_username=settings.owner_telegram_username,
            owner_registry=owner_registry,
            approval_store=approval_store,
            outbound_store=outbound_store,
            email_connection_id=(connected.get("email") or {}).get("id"),
            email_threads=email_threads,
        )
    )
    try:
        client.listen()
    except KeyboardInterrupt:
        print("\nKhyati stopped.")
    except Exception as error:
        raise RuntimeError(f"Caspian listener stopped unexpectedly: {error}") from error
    finally:
        client.close()


if __name__ == "__main__":
    main()
