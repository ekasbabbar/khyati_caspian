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

## Email and Telegram

Khyati uses one Caspian handler for both competition channels:

```bash
python channels.py
```

Before running it:

1. Fill in the selected LLM provider key and `CASPIAN_API_KEY` in `.env`.
2. Create a Telegram bot with `@BotFather` using `/newbot`.
3. Put the returned token in `TELEGRAM_BOT_TOKEN`.

Email is provisioned idempotently from `CASPIAN_EMAIL_USERNAME`. Telegram is a
free channel connected through the bot token. Both inbound channels reach the
same `handle(message)` function, and
`message.reply()` returns the answer to the originating thread.

Recent turns are kept in process-local memory by Caspian `conversation_id`, so
follow-up replies receive the preceding context without leaking history between
customers. Memory resets when `channels.py` restarts. Concurrent conversations
are supported, while `LLM_MAX_CONCURRENT` bounds simultaneous model requests to
protect free-tier provider limits.

## What it does

1. Loads a customer and their event timeline from `data/sample_events.json`
2. Uses structured LLM reasoning to decide whether outreach is warranted
3. Generates a proactive message when contact is recommended
4. Replies to inbound Email and Telegram messages through one Caspian handler

## Safety boundaries

- The deterministic rule engine remains the fallback.
- Telegram users must start the bot before it can reply to them.
- `channels.py` performs real network operations. Tests never send messages or
  spend API/Caspian credit.
