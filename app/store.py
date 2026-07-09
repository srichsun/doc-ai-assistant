"""Chroma vector store setup.

Uses Chroma's built-in embedding model (all-MiniLM, runs locally, no API key).
The model downloads once on first use.
"""
import chromadb

from app import config

_client = chromadb.PersistentClient(path=config.CHROMA_DIR)


def get_collection():
    return _client.get_or_create_collection(config.COLLECTION_NAME)
