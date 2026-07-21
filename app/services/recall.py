"""Semantic recall over the person's atomic facts, backed by pgvector.

Each fact pulled from an exchange (see app.services.facts) is embedded on its
own and stored in a pgvector collection alongside its category. During a
conversation the coach can call search_past_entries to pull back the facts most
related to what the person is talking about now — the "understands you right
now" layer (semantic memory), separate from the plain-SQL day/wins queries.

Storing one vector per single-topic fact — rather than one per whole turn — is
the point: a search for "health" matches only the health fact, instead of being
diluted by the work and relationship threads that shared the same turn.

PGVector needs a real Postgres with the vector extension, so the store is built
lazily on first use and mocked in tests (SQLite can't run it).
"""
from functools import lru_cache

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from app.core import config

# Kept separate from the SQL `facts` table; PGVector manages its own tables.
# A distinct collection from any earlier per-entry store so fact ids and entry
# ids can never collide.
FACTS_COLLECTION = "facts"

# How many facts to pull back per search. Facts are single sentences — much
# shorter than a whole turn — so we pull more of them than the old per-turn
# recall did, while keeping the prompt size fixed as history grows.
TOP_K = 8


@lru_cache(maxsize=1)
def _facts_store() -> PGVector:
    """The pgvector fact store, built once on first use.

    Needs a live Postgres (with the vector extension) and an OpenAI key for
    embeddings, so we don't build it at import time.
    """
    embeddings = OpenAIEmbeddings(
        model=config.OPENAI_EMBEDDING_MODEL,
        api_key=config.OPENAI_API_KEY,
    )
    return PGVector(
        embeddings=embeddings,
        collection_name=FACTS_COLLECTION,
        connection=config.DATABASE_URL,
        use_jsonb=True,
    )


def index_fact(fact_id: int, text: str, user_id: str, category: str) -> None:
    """Embed one fact into pgvector, keyed by its row id.

    Using the SQL row id as the vector id keeps the two stores in sync and makes
    re-indexing the same fact idempotent (it overwrites, not appends). The user
    id and category ride along as metadata so recall can filter to one person
    and, optionally, to just the categories the coach asked for.
    """
    _facts_store().add_texts(
        [text],
        metadatas=[
            {"fact_id": fact_id, "user_id": user_id, "category": category}
        ],
        ids=[str(fact_id)],
    )


def recall(
    query: str,
    user_id: str,
    categories: list[str] | None = None,
    k: int = TOP_K,
) -> list[str]:
    """Return up to k of one person's facts most relevant to the query.

    When categories is given, the search is restricted to those categories
    (the two metadata keys combine as an implicit AND).
    """
    metadata_filter: dict = {"user_id": user_id}
    if categories:
        metadata_filter["category"] = {"$in": categories}
    docs = _facts_store().similarity_search(query, k=k, filter=metadata_filter)
    return [d.page_content for d in docs]


@tool
def search_past_entries(
    query: str,
    runtime: ToolRuntime[str],
    categories: list[str] | None = None,
) -> str | list[str]:
    """Search what you know about this person for facts related to what they are
    talking about now. Use this to ground your reply in their real history —
    what they've told you before, recurring patterns, or similar feelings —
    instead of guessing. The query should describe the current topic or feeling.

    Optionally narrow the search to one or more categories (omit to search all):
    "about me", "preferences", "people", "work & career", "goals & aspirations",
    "health & habits", "beliefs", "patterns". Pick the categories that fit the
    topic — e.g. ["health & habits", "patterns"] when they're talking about how
    they cope with stress."""
    # `runtime` is injected by LangChain, not chosen by the model — it never
    # appears in the tool schema the model sees. Its context is the caller's uid.
    hits = recall(query, user_id=runtime.context, categories=categories)
    if not hits:
        return "No related past facts found."
    return hits
