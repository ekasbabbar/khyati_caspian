# Khyati

Khyati is a personal AI career representative. Recruiters can email Khyati to
learn about a candidate from a verified local knowledge base; sensitive
requests are escalated to the candidate through a private Telegram owner gateway.

Khyati is explicit about being an AI representative. It does not invent career
facts, negotiate compensation, accept interviews, or make commitments without
the candidate's approval.

Its central product principle is active, truthful advocacy: Khyati identifies
the candidate's strongest verified fit, communicates it persuasively, and moves
legitimate recruiter interest toward a concrete next step.

## Product flow

```text
Recruiter Email/Telegram -> Caspian -> grounded AI reply
                                  \-> private Telegram update -> candidate
```

Email and Telegram are connected through one Caspian message handler. Both are
recruiter-facing by default; the configured Telegram username enters the
authenticated owner control path.

## What it does

- Retrieves only relevant Markdown/text sections for each recruiter question.
- Uses two-stage retrieval: relevant files first, then relevant sections.
- Uses hybrid BM25-style ranking plus career-concept expansion.
- Skips retrieval for greetings and unrelated task requests.
- Persists the local chunk index in ignored SQLite storage.
- Enforces recruiter versus owner visibility before context reaches the model.
- Separates public demo knowledge from private personal information.
- Classifies recruiter intent with an LLM and a deterministic five-rule fallback.
- Escalates interview, availability, and compensation requests to the owner.
- Persists interview requests and lets the owner approve, decline, or propose
  another time through Telegram.
- Keeps bounded, isolated context for each conversation.
- Limits concurrent model calls and degrades safely when a provider fails.
- Uses Featherless/Qwen as primary and Gemini as an automatic secondary.
- Rejects leaked model reasoning and malformed structured output.
- Locks owner access to one configured Telegram username.

## Architecture

```text
knowledge/ -> heading chunks -> persistent hybrid index
                                  | relevant, authorized chunks
                                  v
                              ReplyAgent
                                  ^
Recruiter Email -> Caspian single handler -> Email reply
                                  |
                                  v
                        Owner Telegram alert

Featherless/Qwen -> Gemini -> safe response fallback

sample_events.json -> EventStore -> IntentAgent -> CareerDecision -> preview
                                      \-> five-rule fallback

Interview request -> persistent approval -> Telegram owner command
                                      \-> original recruiter email thread
```

## Quick start

Requires Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item data/sample_events.example.json data/sample_events.json
```

On macOS/Linux, activate with `source .venv/bin/activate` and use `cp` for the
two copy commands.

Run the deterministic/LLM-backed local decision preview:

```bash
python app.py
```

This command never sends a message. Run `python provider_check.py` to verify the
configured model with one live request.

## Private career knowledge

The repository contains fictional, publishable examples under
`knowledge.example/`. A local `knowledge/` folder is ignored by Git and is the
default source when present:

```text
knowledge/
|-- profile.md
|-- experience.md
|-- education.md
|-- skills.md
|-- availability.md
|-- preferences.md
|-- private_notes.md
`-- projects/
    `-- khyati.md
```

Fill these files with concise, verifiable facts. Do not include credentials,
government IDs, home addresses, references' private details, or anything an AI
should never disclose. You may point to another folder with
`KHYATI_KNOWLEDGE_DIR`.

Files may begin with metadata controlling retrieval:

```markdown
---
visibility: recruiter
approval_required: false
document_type: project
topics: python, analytics, data science
description: Verified analytics project and measurable outcomes
last_updated: 2026-08-02
---
```

Supported visibility values are `public`, `recruiter`, and `owner_only`.
Recruiter email retrieval can never select `owner_only` chunks; authenticated
owner Telegram retrieval can. Put sensitive decision context in separate
`owner_only` files because visibility currently applies at file level.
`document_type`, `topics`, and `description` improve ranking; `last_updated`
helps you audit freshness. Update dates manually when facts change.

The index is rebuilt automatically when a knowledge file changes. Override its
ignored local location with `KHYATI_KNOWLEDGE_INDEX` if needed.

In a fresh clone without a local folder, Khyati safely loads
`knowledge.example/`, so the public demo works without personal data.

## Configure the LLM

Featherless is the primary provider and Gemini is the automatic secondary:

```dotenv
KHYATI_USE_LLM=true
FEATHERLESS_API_KEY=your_featherless_key
FEATHERLESS_MODEL=Qwen/Qwen3-32B
FEATHERLESS_BASE_URL=https://api.featherless.ai/v1
FEATHERLESS_TIMEOUT_SECONDS=15
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
GEMINI_TIMEOUT_SECONDS=12
LLM_MAX_CONCURRENT=2
LLM_CIRCUIT_FAILURE_THRESHOLD=3
LLM_CIRCUIT_COOLDOWN_SECONDS=60
```

Each provider uses its own deadline with SDK retries disabled. After repeated
failures, a short circuit breaker prevents calls to the unhealthy provider.
Intent analysis falls back to five conservative rules if both providers fail;
live replies use a safe acknowledgement. Runtime logs identify which provider
served each response.

Qwen 3 thinking mode is disabled through Featherless chat-template options.
Khyati also strips complete `<think>...</think>` blocks and rejects incomplete
reasoning output, causing Gemini failover instead of exposing private reasoning.

Verify the live provider chain before starting the channels:

```bash
python provider_check.py
```

Expected output:

```text
Provider order: featherless -> gemini
Served by: featherless
Response: OK
```

## Connect Caspian Email and Telegram

Install and initialize Caspian:

```bash
python -m pip install caspian-cli
caspian init
```

Configure the Caspian channels in `.env`. Telegram serves recruiters and the
authenticated owner:

```dotenv
CASPIAN_API_KEY=your_caspian_key
CASPIAN_BASE_URL=https://api.trycaspianai.com
CASPIAN_EMAIL_USERNAME=khyati-yourname
TELEGRAM_BOT_TOKEN=your_bot_token
KHYATI_OWNER_TELEGRAM_USERNAME=@your_username
KHYATI_OWNER_CHANNEL_STATE=.khyati/owner_channel.json
KHYATI_APPROVAL_STATE=.khyati/pending_approvals.json
KHYATI_OUTBOUND_STATE=.khyati/outbound_drafts.json
KHYATI_EMAIL_THREAD_STATE=.khyati/email_threads.json
```

Start the live multi-channel agent:

```bash
python channels.py
```

Recruiters can use Email or Telegram; Khyati replies in the originating
conversation and sends private summaries to the registered owner conversation.
Message the bot once from `KHYATI_OWNER_TELEGRAM_USERNAME` to register Telegram.
Startup reports whether
the owner conversation was restored or needs registration.

### Interview approval workflow

When a recruiter proposes an interview time, Khyati stores the original email
thread and sends Telegram instructions such as:

```text
INTERVIEW APPROVAL INT-A1B2C3

approve INT-A1B2C3 tomorrow at 3:00 PM IST
decline INT-A1B2C3
counter INT-A1B2C3 Wednesday between 4:00 PM and 6:00 PM IST
```

Approval requires an exact time and timezone. A successful command sends a
deterministic response into the original recruiter email thread and resolves
the request. Send `pending` through Telegram to list open requests. Approval state
is stored under ignored `.khyati/` data and survives restarts.

The authenticated owner can also initiate a new email from Telegram with an explicit,
confirm-before-send flow:

```text
ask person@example.com if she is available for a call tomorrow at 4 PM?
```

Khyati returns an `OUT-XXXXXX` draft containing the exact recipient and body.
Nothing is sent until the owner replies `send OUT-XXXXXX`; use
`cancel OUT-XXXXXX` to discard it. Khyati reuses an existing conversation when
the address has emailed before. A genuinely new address requires Caspian's
`INITIATE` capability on the active Email connection.

## Safety model

- Recruiter messages, quoted mail, URLs, attachments, and event metadata are
  untrusted input.
- Career answers must be grounded in the configured knowledge files.
- Only the top relevant chunks are sent to the model, and retrieved source
  names are printed in the terminal for auditability.
- Specific questions normally retrieve from one or two files; broad background
  requests may use up to three files. Weak matches below the absolute/relative
  relevance thresholds are discarded.
- Interview scheduling, compensation, references, and private contact details
  require owner involvement.
- Owner authorization uses a case-insensitive Telegram username comparison,
  not only a prompt.
- Conversation histories are isolated and bounded to recent messages.
- One failed channel does not prevent the other from starting.

No system prompt makes an agent immune to prompt injection. A production version
would also need durable identity mapping, encrypted persistent memory,
idempotency, and comprehensive audit logs.

## Tests

All 51 tests are offline and send no real messages:

```bash
python -m unittest discover -s tests -q
python smoke_test.py
```

## Project structure

```text
app.py                    Local recruiter-intent preview
channels.py               Caspian Email + Telegram runtime
llm_provider.py           Featherless/Gemini failover and circuit breaker
knowledge_retriever.py    Persistent hybrid retrieval and privacy filtering
reply_agent.py            Grounded recruiter/owner conversation agent
intent_agent.py           LLM classifier + five-rule fallback
approval_store.py         Persistent interview approval state
outbound_store.py         Confirm-before-send outbound drafts
models.py                 Recruiter, event, and decision models
event_store.py            Demo interaction loader
conversation_memory.py    Bounded per-thread context
knowledge.example/        Fictional public knowledge base
knowledge/                Private ignored knowledge base
data/                     Public and local interaction fixtures
tests/                    Offline regression tests
```

## Prototype limitations

- Owner Telegram registration is local to one deployment; moving Khyati to a
  new machine requires messaging the gateway once on that deployment.
- Conversation memory is not persistent.
- Provider circuit-breaker state is process-local and resets after restart.
- `app.py` previews decisions; only `channels.py` communicates through Caspian.
- Attachments are not parsed into trusted knowledge.
- Retrieval currently uses inspectable lexical/concept ranking rather than
  embedding similarity. The retriever boundary is ready for pgvector or Qdrant
  when corpus size or semantic diversity warrants it.
- Approval updates the recruiter email thread but does not create a calendar
  event; the recruiter is asked to send the invitation and meeting link.
## Hackathon

Built for Caspian's 15-day AI Agent Hackathon. Khyati uses `caspian-sdk`, runs on
Email and Telegram, and handles both through one normalized handler.
