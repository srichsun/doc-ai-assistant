# Doc AI Assistant

**English** · [中文](README.zh-TW.md)

A **RAG (Retrieval-Augmented Generation) document Q&A API**. You load a
set of documents (product docs, policies, FAQs), and users ask questions in
natural language. The service retrieves the relevant passages and asks Claude to
answer **using only those passages**, returning the answer together with its
sources. If the answer isn't in the documents, it says so instead of guessing.

The demo knowledge base is a product **customer-support assistant** (plans,
returns policy, warranty). Swap the files in `data/` and it becomes an internal
knowledge base, a technical-docs bot, etc.

## Why RAG (and not just ChatGPT)

A general chatbot doesn't know your private documents, and pasting whole
documents into every prompt is expensive and hits context limits. RAG retrieves
only the relevant chunks, so answers are **cheaper, grounded, and cite their
source** — which is exactly what companies build in-house.

## Architecture

```
                ingest (offline)                     query (per request)
  data/*.pdf,*.md ──> chunk ──> embed ──> Chroma      question
                                            │            │
                                            └── retrieve top-k chunks
                                                         │
                                        build prompt (context + question)
                                                         │
                                              Claude (Anthropic API)
                                                         │
                                             answer + source citations
```

- **Embeddings** run locally via Chroma's built-in model — no API key needed to
  ingest or retrieve.
- Only the **answer generation** step (`/agent`) calls the Anthropic API.

## Tech choices

| Piece         | Choice     | Why not the alternative |
|---------------|------------|-------------------------|
| Web framework | FastAPI    | Async + type hints + auto Swagger docs; lighter than Django for an API. |
| Packaging     | uv         | One tool for venv + lockfile, much faster than pip/poetry. |
| Vector store  | Chroma     | Embedded, zero infra; no SaaS account (Pinecone) or extra DB (pgvector). |
| LLM           | Claude     | Clean Anthropic SDK; model configurable, defaults to `claude-haiku-4-5` (cheap for dev). |
| Embeddings    | Chroma local (all-MiniLM) | No API key or cost by default; swap to a cloud model when needed. |

## Project layout

```
app/
  config.py   settings from env / .env
  main.py     FastAPI routes: /health, /search, /agent
  llm.py      shared Anthropic client
  store.py    Chroma client + pluggable embedding provider
  rag.py      read/chunk/ingest + retrieve
  tools.py    agent tools: search_documents, lookup_order
  agent.py    tool-use loop (Claude picks the tools)
  sessions.py in-memory conversation history
scripts/
  ingest.py   CLI to load data/ into the vector store
data/          your source documents (gitignored)
tests/         pytest (LLM + retrieval mocked, no API key needed)
```

## Setup

```bash
# 1. install deps (uv creates the venv from the lockfile)
uv sync

# 2. add your Anthropic key (only needed for /agent)
cp .env.example .env         # then edit .env and paste your key

# 3. load documents into the vector store (downloads the embedding model once)
uv run python -m scripts.ingest

# 4. run the API
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive Swagger UI.

## Endpoints

| Method | Path         | Description |
|--------|--------------|-------------|
| GET    | `/health`    | Liveness check. |
| GET    | `/search?q=` | Return the top-k retrieved chunks (retrieval sanity check; no LLM, no key). |
| POST   | `/agent`     | Agent: Claude picks tools. `{"question", "session_id?"}` → `{"answer", "tools_used", "sources", "session_id"}`. |

`/agent` requires `ANTHROPIC_API_KEY`.

```bash
curl -X POST http://127.0.0.1:8000/agent \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the status of order 1001, and can I still return it?"}'
```

## How the agent decides

Retrieval is exposed as a `search_documents` **tool** (plus a `lookup_order`
tool), and Claude decides *which* tools to call and *how many times* — not a
fixed "always retrieve, then answer" pipeline. A question like "what's the
status of order 1001 and can I return it?" makes the agent call **both**
tools on its own. It also keeps conversation memory via `session_id`, so
follow-ups ("when will it arrive?") keep context.

## Design decisions & trade-offs

- **Local embeddings by default** — free and offline for development; the
  `openai` provider is one env var away when higher retrieval quality is worth
  the cost. One collection per provider (their vector dimensions differ).
- **Paragraph-aware chunking** — packing whole paragraphs instead of cutting
  every N characters keeps chunks as clean semantic units and measurably lowered
  retrieval distance on sample queries.
- **Grounded answers** — the system prompt tells the model to answer only from
  tool results and say "I don't know" otherwise, which avoids hallucinated
  policy answers. `/agent` returns the sources it searched so answers are
  auditable.
- **In-memory sessions** — fine for a demo; a real deployment would use Redis or
  a database so history survives restarts and scales across workers.

## Web UI

A minimal React (Vite) chat frontend lives in `frontend/`. With the API
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

The LLM call and retrieval are mocked, so the suite runs without an API key.

## Roadmap

Done: pluggable embeddings, paragraph-aware chunking, the agent (tool use),
multi-turn memory, and a React chat frontend with tool/source citations.
Still to do:

- PDF upload UI (plus a backend `/ingest` endpoint).
- Deploy a live demo (deferred — a public `/agent` spends the owner's API
  key, so it needs a gate first).
