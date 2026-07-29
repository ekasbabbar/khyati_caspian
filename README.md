# IntentFlow

IntentFlow is an AI customer success agent that reasons over user activity events and decides whether to proactively contact users. Communication will be delivered through [Caspian](https://github.com/TryCaspian/caspian-sdk) in a later iteration.

## Project structure

```
intentflow/
├── app.py              # Entry point
├── config.py           # Environment-based settings
├── models.py           # Pydantic domain models
├── event_store.py      # Event loading and queries
├── intent_agent.py     # Intent reasoning (stub)
├── messaging_agent.py  # Outbound messaging (stub)
├── logger.py           # Logging setup
├── utils.py            # Shared helpers
├── data/
│   └── sample_events.json
└── prompts/
    ├── intent.txt
    └── message.txt
```

## Requirements

- Python 3.11+

## Setup

```bash
cd intentflow
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # optional — defaults work out of the box
```

## Run

```bash
python app.py
```

This loads sample events from `data/sample_events.json` and prints them to stdout.

## What's implemented

- Pydantic `Customer` and `Event` models
- JSON-backed `EventStore`
- Configuration via environment variables
- Prompt templates for future AI agents
- Stub modules for intent reasoning and messaging

## What's next

- Wire up `IntentAgent` with an LLM to evaluate outreach decisions
- Integrate `MessagingAgent` with the Caspian SDK for multi-channel delivery
- Replace the file-based event store with a real event pipeline
