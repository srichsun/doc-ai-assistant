# Daily Coach

**English** · [中文](README.zh-TW.md)

> 🌐 **Live showcase / 線上展示頁 → https://srichsun.github.io/doc-ai-assistant/**

A **voice AI life coach** you talk to every day. You speak; it listens, reflects
back what it hears, helps you notice your small wins and the patterns in how you
live — and, unlike a stateless chatbot, it **remembers**. You can look back on
any day, watch your wins add up, and over time it genuinely gets to know you.

The core idea is **three layers of memory** so the coach can carry a huge,
ever-growing history while every prompt stays a fixed, bounded size — the cost
and context never blow up no matter how long you use it.

## Why three layers of memory

A general chatbot forgets you the moment the tab closes. Feeding it your whole
history every turn is expensive and eventually overflows the context window.
Daily Coach splits memory into three layers, each answering a different question:

| Layer | Backed by | Answers | AI? |
|-------|-----------|---------|-----|
| **1. Structured log** | Postgres (plain SQL) | "What happened, and when?" — recall a day, this month's wins, mood trends | No AI, just SQL |
| **2. Semantic recall** | pgvector + OpenAI embeddings | "What past moment is relevant to *right now*?" — the coach pulls back similar entries mid-conversation | Embeddings + vector search |
| **3. Rolling profile** | LLM-condensed summary | "Who is this person?" — goals, habits, triggers, what helps — injected into every reply | An LLM re-condenses it |

Every prompt is assembled as **profile + relevant recalled past + today's
context**. The journal in Postgres can grow forever; the prompt does not, because
layers 2 and 3 keep only a fixed slice of it. That rolling profile — the coach
steadily learning who you are — is exactly what a stateless chatbot cannot do.

## How a day with the coach flows

```
  you speak ──► Whisper (STT) ──► LangChain life-coach agent
                                        │
             ┌──────────────────────────┼───────────────────────────┐
             │ profile injected          │ search_past_entries tool  │
             │ (layer 3, every turn)     │ → pgvector (layer 2)      │
             └──────────────────────────┼───────────────────────────┘
                                        ▼
                                   Claude replies
                                        │
                       ┌────────────────┴────────────────┐
                       ▼                                  ▼
              ElevenLabs (TTS)                  save entry to Postgres (layer 1)
              reads it aloud                    + embed it into pgvector (layer 2)
                                                + periodically re-condense profile (layer 3)
```

So one exchange both **answers you now** and **feeds all three memory layers**
for next time.

## What's under the hood

- **Voice in** — OpenAI **Whisper** turns your recorded audio into text.
- **The coach** — a LangChain agent (`create_agent`) driven by **Claude**
  (`ChatAnthropic`), with a single `search_past_entries` tool it calls on its own
  whenever recalling a past moment would help. The profile is injected each turn
  via a dynamic prompt.
- **Voice out** — the reply is read aloud with **ElevenLabs** (a warm British
  voice); OpenAI TTS is a drop-in fallback behind the same `speak()` call.
- **Accounts** — **Firebase Auth (Google sign-in)** in the browser. The backend
  verifies the ID token with the Firebase Admin SDK and scopes every entry,
  every recall, and the profile to that one person. Protected endpoints require
  sign-in.
- **Observability** — **LangSmith** traces every chain and agent call.

## Privacy

The public repo, the showcase page, and the deployed demo use **seed / fake data
only**. Real journal entries stay on your machine and are gitignored, no API keys
live in the repo, and the deployed `/talk` endpoint is gated behind sign-in — so
nobody spends your keys or reads your journal.

## Tech stack

| Piece | Choice | Why |
|-------|--------|-----|
| Web framework | **FastAPI** | Async, type hints, auto Swagger docs; light for an API. |
| Packaging | **uv** | One tool for venv + lockfile, far faster than pip/poetry. |
| Orchestration | **LangChain** | Agent + RAG + memory in one industry-standard stack, instead of hand-rolling the tool loop. |
| LLM | **Claude** via `ChatAnthropic` | The coach's replies and the profile-condensing calls. |
| Speech-to-text | **OpenAI Whisper** | Robust transcription of recorded audio. |
| Text-to-speech | **ElevenLabs** | Warm, real-sounding voice; OpenAI TTS as fallback. |
| Journal store | **Postgres + pgvector** | One database holds both the SQL entries and the vectors (LangChain `PGVector`). |
| Embeddings | **OpenAI** `text-embedding-3-small` | Powers semantic recall. |
| Auth | **Firebase Auth** (Google) | No passwords handled here; per-user scoping from a verified uid. |
| Tracing | **LangSmith** | Every chain/agent call is traced. |
| Frontend | **React (Vite)** | Minimal chat screen with mic recording + spoken replies. |
| CI | **GitHub Actions** | ruff + pytest on every push. |
| Deploy | **Google Cloud** | Cloud Run + Cloud SQL (Postgres + pgvector) + Secret Manager. |

## Project layout

```
app/
  main.py      FastAPI routes: /health /agent /talk /speak /entries /wins /profile
  agent.py     LangChain life-coach agent (create_agent + Claude + search tool + profile injection)
  recall.py    semantic recall — search_past_entries tool over pgvector (layer 2)
  profile.py   rolling LLM-condensed profile (layer 3)
  entries.py   plain-SQL journal: save, recall a day, list wins (layer 1)
  voice.py     Whisper (STT) + ElevenLabs / OpenAI (TTS)
  auth.py      Firebase ID-token verification, per-user scoping
  db.py        SQLAlchemy engine + session
  models.py    Entry and Profile tables
  config.py    settings from env / .env
scripts/
  init_db.py     create the database tables
  deploy_gcp.sh  deploy to Cloud Run + Cloud SQL + Secret Manager
frontend/        React (Vite) chat UI with mic + Google sign-in gate
Dockerfile       container image for Cloud Run
.github/workflows/ci.yml   ruff + pytest
```

## Setup

```bash
# 1. install deps (uv creates the venv from the lockfile)
uv sync

# 2. start local Postgres (pgvector image) and create the tables
docker compose up -d
uv run python -m scripts.init_db

# 3. add your keys
cp .env.example .env    # then edit .env: ANTHROPIC / OPENAI / ELEVENLABS keys,
                        # FIREBASE_CREDENTIALS, optional LANGSMITH_API_KEY

# 4. run the API
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive Swagger UI.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET  | `/health`          | — | Liveness check; no key needed. |
| POST | `/agent`           | ✅ | Typed chat. `{"question", "session_id?"}` → reply; the exchange is saved as a journal entry. |
| POST | `/talk`            | ✅ | Upload recorded audio → Whisper transcribes → coach replies; also returns the transcript. |
| POST | `/speak`           | — | Text → spoken audio (mp3) for the browser to play. |
| GET  | `/entries?day=`    | ✅ | Recall one day's entries (`YYYY-MM-DD`, defaults to today). |
| GET  | `/wins`            | ✅ | The most recent entries where a win was recorded. |
| GET  | `/profile`         | ✅ | The long-term profile the coach has built about you. |
| POST | `/profile/refresh` | ✅ | Force a re-condense of the profile (normally automatic every few entries). |

Protected endpoints expect `Authorization: Bearer <Firebase ID token>`.

## Web UI

A minimal React (Vite) frontend lives in `frontend/`: a chat screen with mic
recording and spoken replies, behind a Google sign-in gate. With the API
running, start it in a second terminal:

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

It talks to the API at `http://127.0.0.1:8000` (allowed via CORS).

## Tests

```bash
uv run pytest
```

The LLM, voice, and vector store are mocked and the suite runs against in-memory
SQLite, so it needs no API key and no running Postgres. CI (GitHub Actions) runs
`ruff check` + `pytest` on every push.

## Deploy

`scripts/deploy_gcp.sh` provisions the whole thing on **Google Cloud**: a Cloud
Run service for the API, **Cloud SQL** (Postgres with pgvector) for the journal
and vectors, and **Secret Manager** for every key and the Firebase service
account. Run it after `gcloud auth login`.
