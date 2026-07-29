"""IntentFlow entry point."""

from config import get_settings
from event_store import EventStore
from logger import setup_logger


def main() -> None:
    """Load events from the event store and print them."""
    settings = get_settings()
    logger = setup_logger(level=settings.log_level)

    store = EventStore(settings.events_path)
    store.load()

    logger.info("Loaded %d customer(s) and %d event(s)", len(store.customers), len(store.events))

    for event in store.events:
        customer = store.customers.get(event.customer_id)
        customer_name = customer.name if customer else "Unknown"
        print(f"[{event.timestamp.isoformat()}] {customer_name} - {event.event_type.value}")


if __name__ == "__main__":
    main()
