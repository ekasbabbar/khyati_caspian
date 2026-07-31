"""Small process-local conversation memory for live channel replies."""

from collections import deque
from threading import Lock


class ConversationMemory:
    """Keep a bounded recent history for each Caspian conversation."""

    def __init__(self, max_messages: int = 12) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be positive")
        self._max_messages = max_messages
        self._conversations: dict[str, deque[dict[str, str]]] = {}
        self._lock = Lock()

    def history(self, conversation_id: str) -> list[dict[str, str]]:
        """Return a copy so callers cannot mutate stored history."""
        with self._lock:
            return [
                message.copy()
                for message in self._conversations.get(conversation_id, ())
            ]

    def add(self, conversation_id: str, role: str, content: str) -> None:
        """Append one user or assistant turn to a conversation."""
        if role not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        with self._lock:
            messages = self._conversations.setdefault(
                conversation_id,
                deque(maxlen=self._max_messages),
            )
            messages.append({"role": role, "content": content})
