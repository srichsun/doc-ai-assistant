"""Central configuration, loaded from environment / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CHAT_MODEL = os.getenv("CHAT_MODEL", "claude-haiku-4-5")
MAX_TOKENS = 1024

# Vector store
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")

# Embeddings: "local" (Chroma's built-in all-MiniLM, no key) or "openai" (cloud).
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# One collection per provider — their vectors have different dimensions and
# must not share a collection.
COLLECTION_NAME = f"documents_{EMBEDDING_PROVIDER}"

# Retrieval
CHUNK_SIZE = 500  # characters per chunk
CHUNK_OVERLAP = 50
TOP_K = 4  # how many chunks to retrieve per question
