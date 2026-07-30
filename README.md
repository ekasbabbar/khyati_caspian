# Khyati

Khyati is an AI customer success agent that reasons over user activity events and decides whether to proactively contact users.

## Run

```bash
pip install -r requirements.txt
python app.py
```

To use a different event-history file:

```bash
$env:KHYATI_EVENTS_PATH = "data/another_customer.json"
python app.py
```

## Test

```bash
python -m unittest discover -s tests
```

## What it does

1. Loads a customer and their event timeline from `data/sample_events.json`
2. Runs a rule engine to decide whether outreach is warranted
3. Generates a proactive message when contact is recommended

## What's next

- Replace the rule engine with an LLM (Phase 6)
- Send messages via the Caspian SDK (Phase 7)
- Handle inbound replies (Phase 8)
