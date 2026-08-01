# Khyati

Khyati is a proactive AI customer-success agent. It observes product activity,
decides whether outreach would genuinely help, and continues the conversation
with customers over Email and Telegram through one Caspian handler.

The goal is not to maximize outreach. Khyati is designed to protect long-term
customer trust, which means the right decision can be to do nothing.

## Why Khyati?

Most assistants wait inside a chat window. Khyati connects product behavior to
real customer communication:

```text
Customer events
      ↓
Structured intent decision
      ↓
Helpful message or deliberate no-contact decision
      ↓
Caspian Email + Telegram
      ↓
Contextual follow-up conversation
```

## Current capabilities

- Validates customer profiles and event histories with Pydantic.
- Uses structured LLM reasoning to decide whether outreach is warranted.
- Falls back to a deterministic five-rule engine when the model is unavailable.
- Generates trust-focused outreach messages.
- Receives and replies through Email and Telegram with one Caspian handler.
- Maintains bounded, isolated memory for each Caspian conversation.
- Limits concurrent model calls to protect free-tier API limits.
- Handles partial channel outages and model failures gracefully.
- Includes offline unit tests and an end-to-end smoke test.

## Tech stack

- Python 3.11+
- Pydantic
- Gemini 3.5 Flash-Lite by default
- OpenAI-compatible model interface (Gemini, DeepSeek, or OpenAI)
- [Caspian SDK](https://github.com/TryCaspian/caspian-sdk)
- Email and Telegram

## Architecture

```text
data/sample_events.json
        ↓
EventStore → Customer + Event models
        ↓
IntentAgent
   ├── configured LLM
   └── RuleIntentAgent fallback
        ↓
IntentDecision
        ↓
MessagingAgent → local outreach preview

Email / Telegram
        ↓
Caspian CommClient
        ↓
one message handler
        ↓
ConversationMemory → ReplyAgent → message.reply()
```

## Quick start

### 1. Create a virtual environment

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Create local configuration and data

PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item data/sample_events.example.json data/sample_events.json
```

macOS/Linux:

```bash
cp .env.example .env
cp data/sample_events.example.json data/sample_events.json
```

Both `.env` and `data/sample_events.json` are ignored by Git. Replace the
placeholder contact information only in your local copy.

### 3. Configure an LLM

Gemini 3.5 Flash-Lite is the default development provider because it offers a
free tier. Create a key in [Google AI Studio](https://aistudio.google.com/apikey)
and update `.env`:

```dotenv
KHYATI_USE_LLM=true
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=your_key
LLM_TIMEOUT_SECONDS=60
LLM_MAX_CONCURRENT=2
```

DeepSeek and OpenAI remain available by changing `LLM_PROVIDER`, `LLM_MODEL`,
and the corresponding API-key variable. If no key is configured—or the request
fails—Khyati uses its deterministic rule engine.

### 4. Run the local decision loop

```bash
python app.py
```

This loads the sample customer, prints the timeline, analyzes intent, and
previews the proposed outreach message. It does not send a real message.

To verify the configured model endpoint with one live request:

```bash
python provider_check.py
```

## Connect Email and Telegram

### Caspian setup

Install the Caspian CLI and initialize a project:

```bash
python -m pip install caspian-cli
caspian init
```

Add the generated values to `.env`:

```dotenv
CASPIAN_API_KEY=your_caspian_key
CASPIAN_BASE_URL=https://api.trycaspianai.com
CASPIAN_EMAIL_USERNAME=khyati-yourname
```

### Telegram setup

1. Open Telegram and message `@BotFather`.
2. Send `/newbot` and choose a bot name and username.
3. Copy the bot token into `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=your_bot_token
```

### Start the live agent

```bash
python channels.py
```

Email is provisioned idempotently from `CASPIAN_EMAIL_USERNAME`. Caspian
registers the Telegram connection using the bot token. Both channels reach the
same handler, and `message.reply()` responds in the originating thread.

To test Telegram, open the bot, press **Start**, and send a message. To test
Email, send a message to the Caspian address printed at startup.

## Conversation memory

Recent user and assistant turns are stored by Caspian `conversation_id`:

- Threads remain isolated from one another.
- At most 12 recent messages are retained per conversation.
- Memory is thread-safe.
- Memory resets whenever `channels.py` restarts.

Persistent conversation storage is intentionally deferred for the prototype.

## Reliability and safety

- Customer text, quoted email, event metadata, and retrieved content are treated
  as untrusted input.
- The reply policy rejects requests for prompts, credentials, private data, and
  hidden reasoning.
- Khyati must not invent product features, prices, affiliations, or account state.
- Intent decisions are validated before use.
- Model failures fall back to rules or a safe customer-facing acknowledgement.
- Email and Telegram connect independently, allowing explicit degraded operation.
- Model concurrency is bounded with `LLM_MAX_CONCURRENT`.
- No test sends a real message or spends provider credit.

No prompt can guarantee immunity from prompt injection. Production deployments
should combine model instructions with authorization, tool restrictions, audit
logs, persistent idempotency, and human escalation.

## Testing

Run the offline suite:

```bash
python -m unittest discover -s tests -q
```

Run the deterministic vertical-slice smoke test:

```bash
python smoke_test.py
```

## Project structure

```text
app.py                    Local intent-analysis demo
channels.py               Caspian Email + Telegram runtime
config.py                 Environment configuration
conversation_memory.py    Bounded per-thread memory
event_store.py            JSON loading and validation
intent_agent.py           LLM reasoning + rule fallback
messaging_agent.py        Deterministic outreach templates
models.py                 Domain and decision models
provider_check.py         Live LLM endpoint check
reply_agent.py            Contextual channel replies
data/                     Sanitized example event history
tests/                    Offline behavior tests
```

## Known prototype limitations

- The local outreach generated by `app.py` is preview-only.
- Conversation memory does not survive process restarts.
- Product facts are not yet grounded in an authoritative knowledge source.
- Telegram users must start the bot before it can reply.
- A free-tier model provider may impose rate and concurrency limits.
- This is a hackathon prototype, not a production customer-contact system.

## Roadmap

- Add trusted product knowledge for grounded responses.
- Strip quoted email history before sending messages to the model.
- Add persistent conversation history and idempotency.
- Connect approved proactive Email delivery.
- Add human handoff and escalation for sensitive cases.
- Record delivery outcomes and decision audit trails.

## Hackathon

Khyati is being built for Caspian's 15-day AI Agent Hackathon. The prototype uses
the `caspian-sdk`, operates on Email and Telegram, and serves both channels through
a single normalized handler.
