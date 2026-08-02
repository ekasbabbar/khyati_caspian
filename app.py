"""Run Khyati's local recruiter-intent demonstration."""

import sys
from time import perf_counter

from config import get_settings
from event_store import EventStore
from intent_agent import IntentAgent
from llm_provider import build_provider_chain
from messaging_agent import MessagingAgent
from utils import print_decision, print_timeline


def main() -> None:
    """Load a recruiter interaction, decide how to act, and preview the action."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    started = perf_counter()

    print("\nLoading recruiter interaction...")
    lead = EventStore(settings.events_path).load()
    print(f"\n✓ Loaded {lead.name} from {lead.company or 'an unknown company'}")
    print_timeline(lead)

    print("\nAnalyzing recruiter intent...")
    provider_chain = None
    if settings.use_llm and (settings.featherless_api_key or settings.gemini_api_key):
        provider_chain = build_provider_chain(settings)
        print(f"LLM provider order: {' -> '.join(provider_chain.provider_names)}")
    agent = IntentAgent(client=provider_chain)
    analysis_started = perf_counter()
    decision = agent.analyze(lead)
    print(f"Brain: {agent.last_source} ({perf_counter() - analysis_started:.2f}s)")
    print_decision(lead, decision)

    if decision.should_respond or decision.should_notify_owner:
        print("\nGenerating action preview...\n")
        print(MessagingAgent().generate(lead, decision))

    print(f"\nCompleted in {perf_counter() - started:.2f}s")


if __name__ == "__main__":
    main()
