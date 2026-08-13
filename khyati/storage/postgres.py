"""PostgreSQL state for multi-instance production deployments."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
from typing import Iterator
from uuid import uuid4

from approval_store import PendingApproval
from outbound_store import OutboundDraft


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT NOT NULL,
    sequence BIGSERIAL PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS conversations_lookup
    ON conversations (conversation_id, sequence DESC);
CREATE TABLE IF NOT EXISTS owner_channels (
    channel TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS email_threads (
    address TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    email_conversation_id TEXT NOT NULL,
    recruiter_address TEXT NOT NULL,
    recruiter_name TEXT NOT NULL,
    request_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_approval_per_request
    ON approvals (email_conversation_id, request_text) WHERE status='pending';
CREATE TABLE IF NOT EXISTS outbound_drafts (
    id TEXT PRIMARY KEY,
    recipient TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS event_cursors (
    consumer TEXT PRIMARY KEY,
    sequence BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY,
    sequence BIGINT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    actor TEXT,
    conversation_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class PostgresState:
    """Own a PostgreSQL DSN and expose repository adapters used by Khyati."""

    def __init__(self, database_url: str, history_limit: int = 12) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self.database_url = database_url
        self.history_limit = history_limit
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as error:
            raise RuntimeError(
                "PostgreSQL mode requires `pip install psycopg[binary,pool]`."
            ) from error
        self._pool = ConnectionPool(database_url, min_size=1, max_size=8, open=True)
        self.conversations = PostgresConversations(self)
        self.owner_channels = PostgresOwnerChannels(self)
        self.email_threads = PostgresEmailThreads(self)
        self.approvals = PostgresApprovals(self)
        self.outbound_drafts = PostgresOutboundDrafts(self)
        self.events = PostgresEvents(self)

    @contextmanager
    def connection(self) -> Iterator[object]:
        with self._pool.connection() as connection:
            yield connection

    def close(self) -> None:
        self._pool.close()

    def initialize(self) -> None:
        """Create idempotent production tables."""
        with self.connection() as connection:
            connection.execute(SCHEMA)

    def audit(
        self,
        action: str,
        *,
        actor: str | None = None,
        conversation_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO audit_log(action, actor, conversation_id, details) "
                "VALUES (%s, %s, %s, %s::jsonb)",
                (action, actor, conversation_id, json.dumps(details or {})),
            )


class PostgresConversations:
    def __init__(self, state: PostgresState) -> None:
        self.state = state

    def history(self, conversation_id: str) -> list[dict[str, str]]:
        with self.state.connection() as connection:
            rows = connection.execute(
                "SELECT role, content FROM conversations "
                "WHERE conversation_id=%s ORDER BY sequence DESC LIMIT %s",
                (conversation_id, self.state.history_limit),
            ).fetchall()
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    def add(self, conversation_id: str, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        with self.state.connection() as connection:
            connection.execute(
                "INSERT INTO conversations(conversation_id, role, content) VALUES (%s,%s,%s)",
                (conversation_id, role, content),
            )


class PostgresOwnerChannels:
    def __init__(self, state: PostgresState) -> None:
        self.state = state

    def get(self, channel: str = "telegram") -> str | None:
        with self.state.connection() as connection:
            row = connection.execute(
                "SELECT conversation_id FROM owner_channels WHERE channel=%s", (channel,)
            ).fetchone()
        return row[0] if row else None

    def all(self) -> tuple[str, ...]:
        with self.state.connection() as connection:
            rows = connection.execute("SELECT conversation_id FROM owner_channels").fetchall()
        return tuple(dict.fromkeys(row[0] for row in rows))

    def set(self, conversation_id: str, channel: str = "telegram") -> None:
        with self.state.connection() as connection:
            connection.execute(
                "INSERT INTO owner_channels(channel, conversation_id) VALUES (%s,%s) "
                "ON CONFLICT(channel) DO UPDATE SET conversation_id=excluded.conversation_id, updated_at=now()",
                (channel, conversation_id),
            )


class PostgresEmailThreads:
    def __init__(self, state: PostgresState) -> None:
        self.state = state

    def set(self, address: str, conversation_id: str) -> None:
        with self.state.connection() as connection:
            connection.execute(
                "INSERT INTO email_threads(address, conversation_id) VALUES (%s,%s) "
                "ON CONFLICT(address) DO UPDATE SET conversation_id=excluded.conversation_id, updated_at=now()",
                (address.lower(), conversation_id),
            )

    def get(self, address: str) -> str | None:
        with self.state.connection() as connection:
            row = connection.execute(
                "SELECT conversation_id FROM email_threads WHERE address=%s",
                (address.lower(),),
            ).fetchone()
        return row[0] if row else None


class PostgresApprovals:
    def __init__(self, state: PostgresState) -> None:
        self.state = state

    @staticmethod
    def _item(row) -> PendingApproval:
        return PendingApproval(*row)

    def create(self, email_conversation_id, recruiter_address, recruiter_name, request_text):
        item = PendingApproval(
            f"INT-{uuid4().hex[:6].upper()}", email_conversation_id,
            recruiter_address, recruiter_name, request_text,
        )
        with self.state.connection() as connection:
            row = connection.execute(
                "INSERT INTO approvals(id,email_conversation_id,recruiter_address,recruiter_name,request_text) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING "
                "RETURNING id,email_conversation_id,recruiter_address,recruiter_name,request_text,status",
                tuple(asdict(item).values())[:-1],
            ).fetchone()
            if row is None:
                row = connection.execute(
                    "SELECT id,email_conversation_id,recruiter_address,recruiter_name,request_text,status "
                    "FROM approvals WHERE email_conversation_id=%s AND request_text=%s AND status='pending'",
                    (email_conversation_id, request_text),
                ).fetchone()
        return self._item(row)

    def pending(self):
        with self.state.connection() as connection:
            rows = connection.execute(
                "SELECT id,email_conversation_id,recruiter_address,recruiter_name,request_text,status "
                "FROM approvals WHERE status='pending' ORDER BY created_at"
            ).fetchall()
        return [self._item(row) for row in rows]

    def get(self, request_id):
        with self.state.connection() as connection:
            row = connection.execute(
                "SELECT id,email_conversation_id,recruiter_address,recruiter_name,request_text,status "
                "FROM approvals WHERE id=%s", (request_id.upper(),)
            ).fetchone()
        return self._item(row) if row else None

    def resolve(self, request_id, status):
        with self.state.connection() as connection:
            connection.execute(
                "UPDATE approvals SET status=%s,updated_at=now() WHERE id=%s",
                (status, request_id.upper()),
            )


class PostgresOutboundDrafts:
    def __init__(self, state: PostgresState) -> None:
        self.state = state

    @staticmethod
    def _item(row) -> OutboundDraft:
        return OutboundDraft(*row)

    def create(self, recipient, text):
        item = OutboundDraft(f"OUT-{uuid4().hex[:6].upper()}", recipient, text)
        with self.state.connection() as connection:
            connection.execute(
                "INSERT INTO outbound_drafts(id,recipient,text,status) VALUES (%s,%s,%s,%s)",
                tuple(asdict(item).values()),
            )
        return item

    def get(self, draft_id):
        with self.state.connection() as connection:
            row = connection.execute(
                "SELECT id,recipient,text,status FROM outbound_drafts WHERE id=%s",
                (draft_id.upper(),),
            ).fetchone()
        return self._item(row) if row else None

    def resolve(self, draft_id, status):
        with self.state.connection() as connection:
            connection.execute(
                "UPDATE outbound_drafts SET status=%s,updated_at=now() WHERE id=%s",
                (status, draft_id.upper()),
            )


class PostgresEvents:
    """Cursor, deduplication, and audit primitives for the production worker."""

    def __init__(self, state: PostgresState) -> None:
        self.state = state

    def claim(self, event_id: str, sequence: int | None = None) -> bool:
        with self.state.connection() as connection:
            row = connection.execute(
                "INSERT INTO processed_events(event_id, sequence) VALUES (%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING event_id",
                (event_id, sequence),
            ).fetchone()
        return row is not None

    def cursor(self, consumer: str = "caspian") -> int:
        with self.state.connection() as connection:
            row = connection.execute(
                "SELECT sequence FROM event_cursors WHERE consumer=%s", (consumer,)
            ).fetchone()
        return int(row[0]) if row else 0

    def advance(self, sequence: int, consumer: str = "caspian") -> None:
        with self.state.connection() as connection:
            connection.execute(
                "INSERT INTO event_cursors(consumer,sequence) VALUES (%s,%s) "
                "ON CONFLICT(consumer) DO UPDATE SET sequence=GREATEST(event_cursors.sequence,excluded.sequence),updated_at=now()",
                (consumer, sequence),
            )
