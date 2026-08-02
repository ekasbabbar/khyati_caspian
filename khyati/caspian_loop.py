"""Durable Caspian polling for the production worker."""

import logging
import time


logger = logging.getLogger(__name__)


def listen_with_postgres_cursor(
    client,
    events,
    *,
    consumer: str = "caspian",
    poll_interval: float = 1.0,
    max_backoff: float = 30.0,
) -> None:
    """Poll from a durable cursor and deduplicate accepted Caspian events.

    Caspian SDK 0.x exposes event polling publicly but keeps dispatch internal.
    This adapter deliberately pins that small compatibility boundary here.
    """
    sequence = events.cursor(consumer)
    backoff = poll_interval
    while True:
        try:
            batch = client.events(after_seq=sequence)
            backoff = poll_interval
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.warning("Caspian poll failed; retrying in %.1fs", backoff, exc_info=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
            continue
        if not batch:
            time.sleep(poll_interval)
            continue
        for event in batch:
            event_id = str(event.get("id") or f"seq:{event['seq']}")
            if events.claim(event_id, event.get("seq")):
                client._dispatch_event(event)
            sequence = int(event["seq"])
            events.advance(sequence, consumer)
