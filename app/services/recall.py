"""Semantic recall over past journal entries, backed by pgvector.

Each saved entry's text is embedded and stored in a pgvector collection that
lives in the same Postgres as the entries table. During a conversation the
coach can call search_past_entries to pull back the moments most related to
what the person is talking about now — that's the "understands you right now"
layer (episodic memory), separate from the plain-SQL day/wins queries.

PGVector needs a real Postgres with the vector extension, so the store is
built lazily on first use and mocked in tests (SQLite can't run it).
"""
from functools import lru_cache

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from app.core import config

# Kept separate from the SQL `entries` table; PGVector manages its own tables.
COLLECTION_NAME = "journal_entries"

# How many past snippets to pull back per search — fixed so the prompt size
# stays constant no matter how large the history grows.
TOP_K = 4


@lru_cache(maxsize=1)
def _store() -> PGVector:
    """The pgvector store, built once on first use.

    Needs a live Postgres (with the vector extension) and an OpenAI key for
    embeddings, so we don't build it at import time.
    """
    embeddings = OpenAIEmbeddings(
        model=config.OPENAI_EMBEDDING_MODEL,
        api_key=config.OPENAI_API_KEY,
    )
    return PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=config.DATABASE_URL,
        use_jsonb=True,
    )


def index_entry(entry_id: int, text: str, user_id: str) -> None:
    """Embed one journal entry's text into pgvector, keyed by its row id.

    Using the SQL row id as the vector id keeps the two stores in sync and
    makes re-indexing the same entry idempotent (it overwrites, not appends).
    The user id rides along as metadata so recall can filter to one person.
    """
    _store().add_texts(
        [text],
        metadatas=[{"entry_id": entry_id, "user_id": user_id}],
        ids=[str(entry_id)],
    )


def recall(query: str, user_id: str, k: int = TOP_K) -> list[str]:
    """Return up to k of one person's past entry snippets most relevant to the query."""
    docs = _store().similarity_search(
        query, k=k, filter={"user_id": user_id}
    )
    return [d.page_content for d in docs]


@tool
def search_past_entries(query: str, runtime: ToolRuntime[str]) -> str | list[str]:
    """Search the person's past journal entries for moments related to what
    they are talking about now. Use this to ground your reply in their real
    history — what they said before, recurring patterns, or similar feelings —
    instead of guessing. The query should describe the current topic or feeling."""
    # `runtime` is injected by LangChain, not chosen by the model — it never
    # appears in the tool schema the model sees. Its context is the caller's uid.
    hits = recall(query, user_id=runtime.context)
    if not hits:
        return "No related past entries found."
    return hits
