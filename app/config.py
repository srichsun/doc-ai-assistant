"""Central configuration, loaded from environment / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

# LLM. The coach's "brain" is swappable via LangChain wrappers — set
# LLM_PROVIDER to "openai" (ChatGPT) or "anthropic" (Claude).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CHAT_MODEL = os.getenv("CHAT_MODEL", "claude-haiku-4-5")          # used if anthropic
# gpt-5.x-chat-latest is the model family that powers ChatGPT itself — the
# warm, structured style the product is known for. (gpt-4o was two+ years old.)
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.3-chat-latest")
# Effectively uncapped so the coach can write long, unhurried, detailed
# reflections. This is a ceiling, not a target — length is driven by the prompt.
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8192"))

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

# Voice output (TTS). "elevenlabs" (real-sounding, paid plan) is the default;
# "openai" (coral etc.) is a swappable fallback on the OpenAI key.
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs")
# OpenAI TTS voice (used when TTS_PROVIDER=openai): coral/shimmer/nova are warm
# and female; fable is British-leaning. Any of the gpt-4o-mini-tts voices work.
TTS_VOICE = os.getenv("TTS_VOICE", "coral")
# ElevenLabs (used when TTS_PROVIDER=elevenlabs). The user's chosen library
# voice; override ELEVENLABS_VOICE_ID to pick another.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pybnebx822VR3K7e82BT")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# Firebase Admin service-account file, used to verify sign-in tokens.
FIREBASE_CREDENTIALS = os.getenv(
    "FIREBASE_CREDENTIALS", "secrets/firebase-admin.json"
)

# Observability (LangSmith). LangChain auto-traces every chain/agent call when
# these env vars are present — setting the API key is enough. We default
# tracing on and name the project so traces are grouped in the LangSmith UI.
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
if LANGSMITH_API_KEY:
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", os.getenv("LANGSMITH_PROJECT", "daily-coach"))

# One collection per provider — their vectors have different dimensions and
# must not share a collection.
COLLECTION_NAME = f"documents_{EMBEDDING_PROVIDER}"

# Retrieval
CHUNK_SIZE = 500  # characters per chunk
CHUNK_OVERLAP = 50
TOP_K = 4  # how many chunks to retrieve per question
