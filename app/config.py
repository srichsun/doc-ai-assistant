"""Central configuration, loaded from environment / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CHAT_MODEL = os.getenv("CHAT_MODEL", "claude-haiku-4-5")
MAX_TOKENS = 1024

# Database (journal entries). Defaults to the local Postgres from
# docker-compose; tests point this at an in-memory SQLite instead.
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://coach:coach@localhost:5433/coach"
)

# Vector store
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")

# Embeddings: "local" (Chroma's built-in all-MiniLM, no key) or "openai" (cloud).
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# Voice: which OpenAI TTS voice reads replies aloud. "fable" is British-ish.
TTS_VOICE = os.getenv("TTS_VOICE", "fable")

# Firebase Admin service-account file, used to verify sign-in tokens.
FIREBASE_CREDENTIALS = os.getenv(
    "FIREBASE_CREDENTIALS", "secrets/firebase-admin.json"
)

# One collection per provider — their vectors have different dimensions and
# must not share a collection.
COLLECTION_NAME = f"documents_{EMBEDDING_PROVIDER}"

# Retrieval
CHUNK_SIZE = 500  # characters per chunk
CHUNK_OVERLAP = 50
TOP_K = 4  # how many chunks to retrieve per question
