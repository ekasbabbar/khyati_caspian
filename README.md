# Khyati

Khyati is a personal AI career representative. Recruiters can email Khyati to
learn about a candidate from a verified private knowledge base; sensitive
requests are escalated to the candidate through a private Telegram channel.

Khyati is explicit about being an AI representative. It does not invent career
facts, negotiate compensation, accept interviews, or make commitments without
the candidate's approval.

Its central product principle is active, truthful advocacy: Khyati identifies
the candidate's strongest verified fit, communicates it persuasively, and moves
legitimate recruiter interest toward a concrete next step.

## Product flow

```text
Recruiter Email → Caspian → grounded AI reply
                         ↘ private Telegram update → candidate
```

Email and Telegram are connected through one Caspian message handler, satisfying
the hackathon's two-channel requirement.

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
- Keeps bounded, isolated context for each conversation.
- Limits concurrent model calls and degrades safely when a provider fails.
- Locks the Telegram owner channel to one configured username.

## Architecture

```text
knowledge/ → heading chunks → persistent hybrid index
                                  ↓ relevant, authorized chunks
                              ReplyAgent
                                  ↑
Recruiter Email → Caspian single handler → Email reply
                                  ↓
                         Owner Telegram alert

sample_events.json → EventStore → IntentAgent → CareerDecision → preview
                                      ↘ five-rule fallback
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
├── profile.md
├── experience.md
├── education.md
├── skills.md
├── availability.md
├── preferences.md
└── projects/
    └── khyati.md
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

Gemini's OpenAI-compatible endpoint is the default:

```dotenv
KHYATI_USE_LLM=true
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=your_key
LLM_MAX_CONCURRENT=2
```

DeepSeek and OpenAI are also supported through the corresponding provider and
API-key variables. Intent analysis falls back to five conservative rules if the
model is missing or unavailable. Live conversational replies use a safe
acknowledgement if generation fails.

## Connect Caspian Email and Telegram

Install and initialize Caspian:

```bash
python -m pip install caspian-cli
caspian init
```

Create a Telegram bot with `@BotFather`, then configure `.env`:

```dotenv
CASPIAN_API_KEY=your_caspian_key
CASPIAN_EMAIL_USERNAME=khyati-yourname
TELEGRAM_BOT_TOKEN=your_bot_token
KHYATI_OWNER_TELEGRAM_USERNAME=@your_username
```

Start the live two-channel agent:

```bash
python channels.py
```

Open your Telegram bot from the configured owner account, press **Start**, and
send a message once. This establishes the private owner conversation for the
current process. Recruiters can then email the Caspian address printed during
startup. Khyati replies in the original email thread and sends the owner a
Telegram summary when that owner conversation is available.

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
- Telegram sender authorization is enforced in code, not only in a prompt.
- Conversation histories are isolated and bounded to recent messages.
- One failed channel does not prevent the other from starting.

No system prompt makes an agent immune to prompt injection. A production version
would also need durable identity mapping, encrypted persistent memory,
idempotency, audit logs, and explicit approval actions.

## Tests

All tests are offline and send no real messages:

```bash
python -m unittest discover -s tests -q
python smoke_test.py
```

## Project structure

```text
app.py                    Local recruiter-intent preview
channels.py               Caspian Email + Telegram runtime
knowledge_retriever.py    Persistent hybrid retrieval and privacy filtering
reply_agent.py            Grounded recruiter/owner conversation agent
intent_agent.py           LLM classifier + five-rule fallback
models.py                 Recruiter, event, and decision models
event_store.py            Demo interaction loader
conversation_memory.py    Bounded per-thread context
knowledge.example/        Fictional public knowledge base
knowledge/                Private ignored knowledge base
data/                     Public and local interaction fixtures
tests/                    Offline regression tests
```

## Prototype limitations

- Owner Telegram conversation discovery is process-local and must be
  re-established after restart.
- Conversation memory is not persistent.
- `app.py` previews decisions; only `channels.py` communicates through Caspian.
- Attachments are not parsed into trusted knowledge.
- Retrieval currently uses inspectable lexical/concept ranking rather than
  embedding similarity. The retriever boundary is ready for pgvector or Qdrant
  when corpus size or semantic diversity warrants it.
- The owner approval loop currently alerts rather than executing structured
  approve/deny actions.

## Hackathon

Built for Caspian's 15-day AI Agent Hackathon. Khyati uses `caspian-sdk`, runs on
Email and Telegram, and handles both through one normalized handler.
