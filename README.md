# Dear Me

**English** · [中文](README.zh-TW.md)

> 🌐 **Live showcase / 線上展示頁 → https://srichsun.github.io/dearme/**
>
> 🚀 **Live app / 線上試用 → https://daily-coach-592904365774.asia-east1.run.app/**

**An AI journal for energy, wins, and gratitude.** One day, one page. Write it,
read it back, and watch what the weeks are actually made of.

Dear Me is not a chatbot you talk to all day. You write the day down once, rate
your energy, and press one button. It pulls out what you won and what you were
grateful for, files them into a memory that grows, and draws your energy over
time — so the pattern you can't see from inside a hard week is obvious from a
month away.

The engineering that makes that possible is **memory**: three layers that let
the record grow forever while every prompt stays a fixed, bounded size.

## Why three layers of memory

A general chatbot forgets you the moment the tab closes. Feeding it your whole
history every turn is expensive and eventually overflows the context window.
Dear Me splits memory into three layers, each answering a different question:

| Layer | Backed by | Answers | AI? |
|-------|-----------|---------|-----|
| **1. The journal** | Postgres (plain SQL) | "What happened, and when?" — one row per day, queried by date | No AI, just SQL |
| **2. Semantic recall** | Atomic facts in pgvector | "What do I know that bears on *this question*?" — individual facts, filed by category | An LLM splits a day into facts; embeddings + vector search find them |
| **3. The rolling read** | LLM-condensed summary | "Who is this person?" — who you are, what you repeat, what your energy responds to | An LLM re-condenses it |

Every answer is assembled as **the rolling read + the facts recalled for this
question**. The journal can grow forever; the prompt does not, because layers 2
and 3 keep only a fixed slice of it.

## The data flows one way

```
   the journal you write                    asking about it
   ─────────────────────                    ───────────────
   entries  (one row per day)               your question
      │  press "Read today" — one LLM call      │
      ▼                                          ▼  vector + category search
   facts    (5–10 single-topic, embedded)  ──►  the facts that bear on it
      │  press "Read me" — one LLM call          │  + the rolling read
      ▼                                          ▼
   profiles (who you are / patterns / energy) ─► the answer, naming the days
```

**No arrow points back up.** Asking questions writes nothing: no entry, no
fact, no profile update. What it knows comes from what you sat down and
wrote, never from what you said in passing. That isn't a rule the code keeps
to — the call doesn't exist on that path, and a test deliberately leaves the
fact extractor unmocked so that adding one back fails loudly.

## Design decisions worth explaining

**Memory is stored as atomic facts, not whole entries.** The first version
embedded each conversation turn whole. That broke as soon as it met real use:
someone writing for three minutes covers work, health and family in one breath,
and averaging all three into a single 1536-dimension vector means a search for
"health" gets diluted by the other two threads. Retrieval degraded into "find a
day that felt similar" rather than "find the relevant moment".

So each day is now split by an LLM into 5–10 single-topic facts, each filed
under one of ten fixed categories (`about me`, `preferences`, `people`,
`work & career`, `goals & aspirations`, `health & habits`, `beliefs`,
`patterns`, `wins`, `gratitude`) and embedded on its own. The split is a
rewrite, not a cut: "work stalled but I ran anyway" becomes a standalone "you
keep running even when exhausted", which still makes sense retrieved months
later with no surrounding context. At retrieval, similarity search runs
*alongside* the model's own judgement — the agent names the categories worth
searching as a tool argument, so the two narrow the field together.

Worth saying what this is *not* for: if the answer already sits in one passage
(documentation Q&A, a clause in a contract), plain chunk-and-embed is cheaper
and just as good. Extraction earns its cost only when the answer has to be
*assembled* from scattered evidence — which is exactly what "what actually
drains me?" requires.

**Changing the product dissolved an architecture problem instead of solving
it.** In the chat version, fact extraction ran on every turn, which put an LLM
call and a round of embeddings between the person and their reply. The fix
looked like a job queue: Celery, Redis, a worker that can't scale to zero —
about £35/month of infrastructure to hide a delay. Turning the product into a
journal moved extraction behind a button the person presses deliberately, and
the whole problem went away. No queue, no broker, no worker. **The cheapest
solution to a latency problem is often a product decision, not an
infrastructure one.**

**There is no conversation-memory component.** An earlier version kept a
LangGraph checkpointer so the agent could remember the current conversation. It
was removed: every question is already written to Postgres, so an in-memory
copy was a second source of truth that vanished on restart and never crossed
devices. Each turn rebuilds today's thread by replaying it from the database.
Deleting a component proved more about the design than adding a framework
would have.

**A day is uid + date, not a browser session** — and the date is drawn in
**Taiwan time** (`app/core/clock.py`). A UTC day boundary would cut the day at
8am local, halfway through a morning. The same definition gives the journal its
central rule for free: one entry per person per day, enforced by a unique index
rather than a check in the service layer. Writing a second entry for a day
isn't refused, it's impossible. Only today is writable, and no endpoint takes a
date to write to, so backfilling a day you missed is unreachable rather than
forbidden.

**Writing is free; the analysis is metered.** The allowance was originally
shared between editing the text and re-running the analysis. Real use showed
that was the wrong thing to charge for — a day gets written in passes, a note
at lunch and the rest at midnight, and counting those punishes keeping up with
your own day. Storing text costs nothing, so writing is unlimited. The three-a-
day allowance sits entirely on analysis: the part that spends a model call, and
the part that should settle once the day is actually over.

**Self-rated energy has ten steps, not a hundred.** It is shown as a
percentage, but chosen from 1–10. Nobody can tell their own 67 from their 71,
and a scale finer than the judgement behind it makes the chart look precise
while meaning less. Unrated days are drawn as a gap, never a zero and never a
joined line — a line would claim the days between were somewhere on the way
from one to the other, which is a claim about days that have no rating at all.

## The four screens

| Screen | What it is |
|--------|------------|
| **Record** | Your energy over 7 or 30 days, today's entry (typed or dictated), and one folded card per day behind it with that day's wins and gratitude. |
| **Reading** | Who you are, what you repeat, and what your energy responds to. Rebuilt only when you ask. |
| **Ask** | Questions about your own journal, streamed and read aloud, each answer naming the days it drew on. Read-only, and the thread ends with the day. |
| **Mantras** | Lines you keep for yourself, injected into the prompt so your own words can be handed back to you. |

## What's under the hood

- **Writing** — type it, or dictate it: **OpenAI `gpt-4o-mini-transcribe`**
  turns recorded audio into text and appends it to the day, so an entry can be
  spoken in passes. The browser reports its own recording format (Chrome makes
  webm, iOS Safari makes mp4) rather than the code assuming one.
- **Analysis** — one structured-output call breaks the day into single-topic
  facts, each filed under a fixed category (`app/services/facts.py`).
  Re-analysing replaces the day's facts in both Postgres and pgvector rather
  than leaving two readings of the same day in memory.
- **Asking** — a LangChain agent (`create_agent`) driven by **OpenAI
  `gpt-5.3-chat-latest`**, with a single `search_past_entries` tool it calls on
  its own. The tool takes an optional list of categories, so the model narrows
  the search itself instead of relying on vector distance alone. Every fact
  comes back stamped with the journal day it was written about — read from the
  SQL row, not the vector metadata, so re-analysing a day never makes it cite
  the day it was re-read. Claude is a supported alternative:
  `LLM_PROVIDER=anthropic`.
- **Voice out** — answers are read aloud with **Google Cloud TTS**
  (`en-GB-Chirp3-HD-Callirrhoe`). ElevenLabs and OpenAI TTS sit behind the same
  `speak()` call via `TTS_PROVIDER`. Synthesis latency grows superlinearly with
  length, so the frontend splits the reply into ~220-character sentences and
  plays each while fetching the next — the first sound arrives in about a
  second.
- **Accounts** — **Firebase Auth (Google sign-in)** in the browser. The backend
  verifies the ID token with the Firebase Admin SDK and scopes every entry,
  every recall and the reading to that one person. A lookup by id is scoped by
  uid in the query itself, so a guessed id reads as "no such entry" rather than
  being loaded and then rejected.
- **Observability** — **LangSmith** traces every chain and agent call.

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
| Orchestration | **LangChain** | Agent + tool loop in one industry-standard stack, instead of hand-rolling it. |
| LLM | **OpenAI** `gpt-5.3-chat-latest` | The family that powers ChatGPT itself; Claude swappable via `LLM_PROVIDER`. |
| Speech-to-text | **OpenAI** `gpt-4o-mini-transcribe` | Newer and more accurate than `whisper-1` at a similar price. |
| Text-to-speech | **Google Cloud TTS** | Real British accent, generous free tier; ElevenLabs / OpenAI behind the same call. |
| Journal store | **Postgres + pgvector** | One database holds the entries, the extracted facts, and their vectors (LangChain `PGVector`). |
| Embeddings | **OpenAI** `text-embedding-3-small` | One vector per atomic fact, so a search matches a single topic. |
| Auth | **Firebase Auth** (Google) | No passwords handled here; per-user scoping from a verified uid. |
| Tracing | **LangSmith** | Every chain/agent call is traced. |
| Frontend | **React (Vite)** | Four mobile-first screens; **Recharts** for the energy chart. |
| Lint | **ruff** | Lint and format in one fast tool. |
| CI/CD | **GitHub Actions** | ruff + pytest on every push; green main deploys itself. |
| Deploy | **Google Cloud** | Cloud Run + Cloud SQL (Postgres + pgvector) + Secret Manager. |

## Project layout

```
app/
  main.py            FastAPI app: mounts the router, migrates on boot, serves the built frontend
  api/
    router.py        collects every route module
    deps.py          CurrentUid — annotate a route with it to require sign-in
    routes/          health · journal · coach · questions · profile · mantras · voice
  services/
    entries.py       the journal: one row per day, only today writable (layer 1)
    facts.py         splits a day into atomic facts, filed by category
    recall.py        semantic recall — search_past_entries over pgvector (layer 2)
    profile.py       the rolling read, in three sections (layer 3)
    questions.py     the question thread — the only table the read path may write
    agent.py         LangChain agent (create_agent + tool + prompt injection)
    chat_model.py    builds the chat model chosen by LLM_PROVIDER
    mantras.py       the lines you keep, and their prompt text
    voice.py         speech-to-text + text-to-speech
  models/            SQLAlchemy tables: Entry, Fact, Profile, Question, Mantra
  schemas/           request/response models
  core/
    config.py        settings from env / .env
    db.py            SQLAlchemy engine + session
    security.py      Firebase ID-token verification, per-user scoping
    clock.py         what "today" means (Taiwan time)
migrations/          Alembic: one file per schema change, applied in order
scripts/
  backfill_facts.py  extract facts for entries that don't have any yet
  deploy_gcp.sh      first-run provisioning: Cloud Run + Cloud SQL + Secret Manager
frontend/src/
  App.jsx            the shell: auth, four tabs
  tabs/              Record · Insights · Ask · Mantras
  EnergyChart.jsx    the bar-per-day chart (Recharts)
  energy.js          how a rating looks: bands, colours, percentages
  speech.js          recording and reading aloud
  api.js             authenticated fetch
Dockerfile           container image for Cloud Run
.github/workflows/ci.yml   ruff + pytest, then deploy on green main
```

## Setup

```bash
# 1. install deps (uv creates the venv from the lockfile)
uv sync

# 2. start local Postgres (pgvector image) and run the migrations
docker compose up -d
uv run alembic upgrade head

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
| GET  | `/health`                   | — | Liveness check; no key needed. |
| POST | `/entries`                  | ✅ | Write or rewrite today. Unmetered. |
| GET  | `/entries?days=7`           | ✅ | The last N journal days, oldest first, each with its wins and gratitude. |
| POST | `/entries/{id}/analyze`     | ✅ | Pull the day's facts out of what was written. Three a day; `409` after that. |
| GET  | `/profile`                  | ✅ | The rolling read, plus how many days it's behind. |
| POST | `/profile/refresh`          | ✅ | Rebuild it. Only ever runs when asked. |
| POST | `/agent/stream`             | ✅ | Ask about the journal; the answer streams token by token. Writes nothing but the question. |
| GET  | `/questions?day=`           | ✅ | One day's questions and answers (defaults to today). |
| GET  | `/questions/days`           | ✅ | The days you asked anything — the history list. |
| POST | `/transcribe`               | ✅ | Upload recorded audio → text. |
| POST | `/speak`                    | ✅ | Text → spoken audio (mp3) for the browser to play. |
| GET  | `/mantras`                  | ✅ | The lines you've kept. |
| POST | `/mantras`                  | ✅ | Keep a new line. |
| PATCH | `/mantras/{id}`            | ✅ | Reword one. |
| DELETE | `/mantras/{id}`           | ✅ | Drop one. |

Protected endpoints expect `Authorization: Bearer <Firebase ID token>`.

## Web UI

The React (Vite) frontend in `frontend/` has four mobile-first screens behind a
Google sign-in gate. With the API running, start it in a second terminal:

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

It talks to the API at `http://127.0.0.1:8000` (allowed via CORS). In
production the same React build is served by FastAPI itself, from the image.

## Schema changes

Schema is versioned with **Alembic**. Change a model, then:

```bash
uv run alembic revision --autogenerate -m "what changed"   # writes the migration
uv run alembic upgrade head                                # applies it
uv run alembic downgrade -1                                # undoes it
uv run alembic check                                       # models vs database
```

The app runs `alembic upgrade head` on boot, so a deploy migrates itself and a
fresh database builds from empty. That also means **a push to `main` applies
your migration to production** — there is no second confirmation, so run a data
migration against a restored copy first.

`migrations/env.py` hides LangChain's `langchain_pg_*` tables from autogenerate.
They aren't in `Base.metadata` because LangChain creates them, so without that
filter every migration would try to drop them — and every embedding with them.

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
