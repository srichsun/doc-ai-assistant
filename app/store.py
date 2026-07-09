"""Chroma vector store setup with a pluggable embedding provider.

- "local"  : Chroma's built-in all-MiniLM model. Runs on-device, no API key.
- "openai" : OpenAI text-embedding-3-small. Higher quality, needs OPENAI_API_KEY.

Switching provider changes the collection name (their vector dimensions
differ), so re-run the ingest after switching.
"""
import chromadb
from chromadb.utils import embedding_functions

from app import config

_client = chromadb.PersistentClient(path=config.CHROMA_DIR)


def _embedding_function():
    """Return the embedding function for the configured provider.

    None means "use Chroma's default" (the local all-MiniLM model).
    """
    if config.EMBEDDING_PROVIDER == "openai":
        if not config.OPENAI_API_KEY:
            raise RuntimeError("EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set")
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=config.OPENAI_API_KEY,
            model_name=config.OPENAI_EMBEDDING_MODEL,
        )
    return None  # local default


def get_collection():
    return _client.get_or_create_collection(
        config.COLLECTION_NAME,
        embedding_function=_embedding_function(),
    )
