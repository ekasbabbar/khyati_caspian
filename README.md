# Khyati

Khyati is an AI customer success agent that reasons over user activity events and decides whether to proactively contact users.

TechStack: Gemini 3 Flash + Caspian SDK 

## Local product loop

```bash
pip install -r requirements.txt
python app.py
```

Copy `.env.example` to `.env` and add a key for the selected LLM provider.
Gemini 3.5 Flash-Lite is the default because it has a development free tier.
DeepSeek and OpenAI remain selectable without code changes. Without a key—or if
the model call fails—the tested rule engine is used automatically.

To use a different event-history file:

```bash
$env:KHYATI_EVENTS_PATH = "data/another_customer.json"
python app.py
```

## Test

```bash
python -m unittest discover -s tests
```

For a quick end-to-end smoke test:

```bash
python smoke_test.py
```

To verify which configured LLM provider answers a live request:

```bash
python provider_check.py
```

## Email and WhatsApp

Khyati uses one Caspian handler for both competition channels:

```bash
python channels.py
```

Before running it:

1. Fill in the selected LLM provider key and `CASPIAN_API_KEY` in `.env`.
2. Connect WhatsApp using Caspian's Twilio sandbox or Meta onboarding.
3. Keep `CASPIAN_WHATSAPP_PROVIDER` aligned with the provider you selected.

Email is provisioned idempotently from `CASPIAN_EMAIL_USERNAME`. WhatsApp is a
paid hosted channel and may require `caspian login`, starter credit, and provider
setup. Both inbound channels reach the same `handle(message)` function, and
`message.reply()` returns the answer to the originating thread.

Recent turns are kept in process-local memory by Caspian `conversation_id`, so
follow-up replies receive the preceding context without leaking history between
customers. Memory resets when `channels.py` restarts.

## What it does

1. Loads a customer and their event timeline from `data/sample_events.json`
2. Uses structured LLM reasoning to decide whether outreach is warranted
3. Generates a proactive message when contact is recommended
4. Replies to inbound Email and WhatsApp messages through one Caspian handler

## Safety boundaries

- The deterministic rule engine remains the fallback.
- WhatsApp cold outreach requires an approved template; this prototype does not
  bypass that platform rule.
- `channels.py` performs real network operations. Tests never send messages or
  spend API/Caspian credit.
