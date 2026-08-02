"""Channel-independent orchestration shared by Caspian and future APIs."""

from dataclasses import dataclass
from typing import Protocol

from conversation_memory import ConversationMemory


class ReplyGenerator(Protocol):
    def respond(
        self,
        text: str,
        channel: str,
        history: list[dict[str, str]] | None = None,
    ) -> str: ...


class ConversationStore(Protocol):
    def history(self, conversation_id: str) -> list[dict[str, str]]: ...
    def add(self, conversation_id: str, role: str, content: str) -> None: ...


@dataclass(frozen=True)
class AgentResponse:
    """Stable response contract for communication gateways and HTTP APIs."""

    answer: str
    audience: str
    source: str
    conversation_id: str


class KhyatiService:
    """Apply identity policy, history, and reply generation independently of transport."""

    def __init__(
        self,
        reply_generator: ReplyGenerator,
        conversations: ConversationStore | None = None,
    ) -> None:
        self._reply_generator = reply_generator
        self._conversations = conversations or ConversationMemory()

    def record_exchange(self, conversation_id: str, text: str, answer: str) -> None:
        """Persist a deterministic gateway fallback through the same history boundary."""
        self._conversations.add(conversation_id, "user", text)
        self._conversations.add(conversation_id, "assistant", answer)

    def respond(
        self,
        *,
        text: str,
        audience: str,
        conversation_id: str,
        source: str,
    ) -> AgentResponse:
        if audience not in {"recruiter", "owner"}:
            raise ValueError("audience must be recruiter or owner")
        if source not in {"email", "telegram", "portfolio"}:
            raise ValueError("source must be email, telegram, or portfolio")
        if not conversation_id:
            raise ValueError("conversation_id is required")
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("text must not be empty")

        channel_role = "owner" if audience == "owner" else source
        answer = self._reply_generator.respond(
            text=clean_text,
            channel=channel_role,
            history=self._conversations.history(conversation_id),
        )
        self.record_exchange(conversation_id, clean_text, answer)
        return AgentResponse(answer, audience, source, conversation_id)
