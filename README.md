# Minerva

**English** · [中文](README.zh-TW.md)

> 🌐 **Live showcase / 線上展示頁 → https://srichsun.github.io/Minerva/**
>
> 🚀 **Live app / 線上試用 → https://daily-coach-592904365774.asia-east1.run.app/**

**A voice AI friend for the hard days.** You talk; she listens.

Minerva is built for the moments that actually derail a day — when fear takes
over, when nothing feels clear enough to decide, when you've lost sight of what
you're capable of. She steadies you, helps you think it through, and reminds
you what your own record already proves — so you get back to calm, and back to
work.

The reason she can do that is **memory**. Unlike a stateless chatbot, she keeps
your whole story, and the technical core of this project is making that
possible: **three layers of memory** that let her carry an ever-growing history
while every prompt stays a fixed, bounded size — the cost and context never
blow up, no matter how long you use it.

## Why three layers of memory

A general chatbot forgets you the moment the tab closes. Feeding it your whole
history every turn is expensive and eventually overflows the context window.
Minerva splits memory into three layers, each answering a different question:

| Layer | Backed by | Answers | AI? |
|-------|-----------|---------|-----|
| **1. Structured log** | Postgres (plain SQL) | "What happened, and when?" — recall a day, this month's wins, mood trends | No AI, just SQL |
| **2. Semantic recall** | pgvector + OpenAI embeddings | "What past moment is relevant to *right now*?" — she pulls back similar entries mid-conversation | Embeddings + vector search |
| **3. Rolling profile** | LLM-condensed summary | "Who is this person?" — goals, habits, triggers, what helps — injected into every reply | An LLM re-condenses it |

Every prompt is assembled as **profile + relevant recalled past + today's
context**. The journal in Postgres can grow forever; the prompt does not, because
layers 2 and 3 keep only a fixed slice of it. That rolling profile — Minerva
steadily learning who you are — is exactly what a stateless chatbot cannot do.

## Two design decisions worth explaining

**There is no conversation-memory component.** An earlier version kept a
LangGraph checkpointer so the agent could remember the current conversation.
It was removed: every exchange is already written to Postgres, so an in-memory
copy was a second source of truth that vanished on restart and never crossed
devices. Each turn now rebuilds today's conversation by replaying it from the
database. Deleting a component proved more about the design than adding a
framework would have.

**A "conversation" is defined as uid + day, not a browser session.** A
`session_id` lives in localStorage, so switching devices silently starts a new
conversation. Days are drawn in **Taiwan time** (`app/core/clock.py`) — a UTC
day boundary would cut the thread at 8am local, halfway through a morning.

## How a conversation flows

```
  you speak ──► gpt-4o-mini-transcribe (STT) ──► LangChain agent
                                                       │
             ┌─────────────────────────────────────────┼───────────────────────────┐
             │ profile + strengths + mantras injected   │ search_past_entries tool  │
             │ (layer 3, every turn)                    │ → pgvector (layer 2)      │
             └─────────────────────────────────────────┼───────────────────────────┘
                                                       ▼
                                          gpt-5.3-chat-latest replies
                                                       │
                       ┌───────────────────────────────┴──────────────────┐
                       ▼                                                  ▼
              Google Cloud TTS                            save entry to Postgres (layer 1)
              reads it aloud                              + embed it into pgvector (layer 2)
                                                          + periodically re-condense profile (layer 3)
```

So one exchange both **answers you now** and **feeds all three memory layers**
for next time.

## What's under the hood

- **Voice in** — OpenAI **`gpt-4o-mini-transcribe`** turns your recorded audio
  into text. The browser reports its own recording format (Chrome makes webm,
  iOS Safari makes mp4) rather than the code assuming one.
- **Minerva** — a LangChain agent (`create_agent`) driven by **OpenAI
  `gpt-5.3-chat-latest`**, with a single `search_past_entries` tool it calls on
  its own whenever recalling a past moment would help. Claude is a supported
  alternative: set `LLM_PROVIDER=anthropic`. Profile, strengths, and saved
  mantras are injected each turn via a dynamic prompt.
- **Voice out** — the reply is read aloud with **Google Cloud TTS**
  (`en-GB-Chirp3-HD-Callirrhoe`, a genuinely British voice). ElevenLabs and
  OpenAI TTS sit behind the same `speak()` call via `TTS_PROVIDER`. Synthesis
  latency grows superlinearly with length, so the frontend splits the reply
  into ~220-character sentences and plays each while fetching the next — the
  first sound arrives in about a second.
- **Accounts** — **Firebase Auth (Google sign-in)** in the browser. The backend
  verifies the ID token with the Firebase Admin SDK and scopes every entry,
  every recall, and the profile to that one person. Every endpoint except
  `/health` requires sign-in.
- **Observability** — **LangSmith** traces every chain and agent call.

## What you can do with her

| Feature | What it is |
|---------|------------|
| **Talk** | Voice or text, streamed back token by token and read aloud. |
| **Wins** | Short factual lines of what you actually did, extracted from each exchange. |
| **You** | A passage in plain prose about who you are, written by an LLM from the whole record of wins. Meant for the days you've forgotten. |
| **Mantra** | Lines you keep for yourself. Full CRUD, and they are injected into her prompt so she can use your own words back at you. |

## Privacy

The public repo, the showcase page, and the deployed demo use **seed / fake data
only**. Real journal entries stay on your machine and are gitignored, no API keys
live in the repo, and every costly endpoint is gated behind sign-in — so
nobody spends your keys or reads your journal.

## Tech stack

| Piece | Choice | Why |
|-------|--------|-----|
| Web framework | **FastAPI** | Async, type hints, auto Swagger docs; light for an API. |
| Packaging | **uv** | One tool for venv + lockfile, far faster than pip/poetry. |
| Orchestration | **LangChain** | Agent + RAG + memory in one industry-standard stack, instead of hand-rolling the tool loop. |
| LLM | **OpenAI** `gpt-5.3-chat-latest` | The family that powers ChatGPT itself; Claude swappable via `LLM_PROVIDER`. |
| Speech-to-text | **OpenAI** `gpt-4o-mini-transcribe` | Newer and more accurate than `whisper-1` at a similar price. |
| Text-to-speech | **Google Cloud TTS** | Real British accent, generous free tier; ElevenLabs / OpenAI behind the same call. |
| Journal store | **Postgres + pgvector** | One database holds both the SQL entries and the vectors (LangChain `PGVector`). |
| Embeddings | **OpenAI** `text-embedding-3-small` | Powers semantic recall. |
| Auth | **Firebase Auth** (Google) | No passwords handled here; per-user scoping from a verified uid. |
| Tracing | **LangSmith** | Every chain/agent call is traced. |
| Frontend | **React (Vite)** | Chat, Wins, You, and Mantra screens with mic recording + spoken replies. |
| Lint | **ruff** | Lint and format in one fast tool. |
| CI/CD | **GitHub Actions** | ruff + pytest on every push; green main deploys itself. |
| Deploy | **Google Cloud** | Cloud Run + Cloud SQL (Postgres + pgvector) + Secret Manager. |

## Project layout

```
app/
  main.py            FastAPI app: mounts the router, creates tables, serves the built frontend
  api/
    router.py        collects every route module
    deps.py          CurrentUser — annotate a route with it to require sign-in
    routes/          health · coach · voice · journal · profile · mantras
  services/
    agent.py         LangChain agent (create_agent + tool + prompt injection)
    chat_model.py    builds the chat model chosen by LLM_PROVIDER
    recall.py        semantic recall — search_past_entries over pgvector (layer 2)
    profile.py       rolling LLM-condensed profile (layer 3)
    strengths.py     the "You" passage, written from the whole record of wins
    entries.py       plain-SQL journal: save, recall a day, list wins (layer 1)
    mantras.py       the lines you keep, and their prompt text
    voice.py         speech-to-text + text-to-speech
  models/            SQLAlchemy tables: Entry, Profile, Mantra
  schemas/           request/response models
  core/
    config.py        settings from env / .env
    db.py            SQLAlchemy engine + session
    security.py      Firebase ID-token verification, per-user scoping
    clock.py         what "today" means (Taiwan time)
scripts/
  init_db.py         create the database tables
  deploy_gcp.sh      provision Cloud Run + Cloud SQL + Secret Manager
frontend/            React (Vite) UI behind a Google sign-in gate
Dockerfile           container image for Cloud Run
.gcloudignore        keeps node_modules out of the deploy upload
.github/workflows/ci.yml   ruff + pytest, then deploy on green main
```

## Setup

```bash
# 1. install deps (uv creates the venv from the lockfile)
uv sync

# 2. start local Postgres (pgvector image) and create the tables
docker compose up -d
uv run python -m scripts.init_db

# 3. add your keys
cp .env.example .env    # then edit .env: OPENAI_API_KEY (and ANTHROPIC /
                        # ELEVENLABS if you switch providers),
                        # FIREBASE_CREDENTIALS, optional LANGSMITH_API_KEY

# 4. run the API
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive Swagger UI.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET  | `/health`            | — | Liveness check; no key needed. |
| POST | `/agent`             | ✅ | Typed chat. `{"question", "session_id?"}` → reply; the exchange is saved as a journal entry. |
| POST | `/agent/stream`      | ✅ | Same as `/agent`, but streams the reply token by token. |
| POST | `/transcribe`        | ✅ | Upload recorded audio → text. |
| POST | `/speak`             | ✅ | Text → spoken audio (mp3) for the browser to play. |
| GET  | `/entries?day=`      | ✅ | Recall one day's entries (`YYYY-MM-DD`, defaults to today, Taiwan time). |
| GET  | `/wins`              | ✅ | The most recent entries where a win was recorded. |
| GET  | `/strengths`         | ✅ | The "You" passage, written from your record of wins. |
| POST | `/strengths/refresh` | ✅ | Force a rewrite of that passage. |
| GET  | `/profile`           | ✅ | The long-term profile Minerva has built about you. |
| POST | `/profile/refresh`   | ✅ | Force a re-condense of the profile (normally automatic every few entries). |
| GET  | `/mantras`           | ✅ | The lines you've kept. |
| POST | `/mantras`           | ✅ | Keep a new line. |
| PATCH | `/mantras/{id}`     | ✅ | Reword one. |
| DELETE | `/mantras/{id}`    | ✅ | Drop one. |

Protected endpoints expect `Authorization: Bearer <Firebase ID token>`.

## Web UI

The React (Vite) frontend in `frontend/` has four screens — chat, Wins, You,
and Mantra — behind a Google sign-in gate. With the API running, start it in a
second terminal:

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

It talks to the API at `http://127.0.0.1:8000` (allowed via CORS). In
production the same React build is served by FastAPI itself, from the image.

## Tests and lint

```bash
uv run pytest
uv run ruff check .
```

The LLM, voice, and vector store are mocked and the suite runs against in-memory
SQLite, so it needs no API key and no running Postgres.

## Deploy

Pushing to `main` deploys itself: GitHub Actions runs ruff + pytest, and on
green it builds and rolls out to Cloud Run. It authenticates with **Workload
Identity Federation** — GitHub proves its identity with a short-lived OIDC
token and Google returns a short-lived credential, so no service-account key
exists anywhere.

`scripts/deploy_gcp.sh` provisions the whole thing from scratch on **Google
Cloud**: a Cloud Run service for the API, **Cloud SQL** (Postgres with pgvector)
for the journal and vectors, and **Secret Manager** for every key and the
Firebase service account. Run it after `gcloud auth login`.
