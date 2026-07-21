"""Central configuration, loaded from environment / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

# --- LLM ("the coach's brain") ---
# Swappable via LangChain wrappers — set LLM_PROVIDER to "openai" (ChatGPT) or
# "anthropic" (Claude). OPENAI_API_KEY doubles as the key for STT and
# embeddings below, regardless of which provider is chosen as the brain.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_CHAT_MODEL = os.getenv("ANTHROPIC_CHAT_MODEL", "claude-haiku-4-5")
# gpt-5.x-chat-latest is the model family that powers ChatGPT itself — the
# warm, structured style the product is known for. (gpt-4o was two+ years old.)
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.3-chat-latest")
# Ceiling, not a target — length is driven by the prompt. Sized from real
# replies (persona + tools), which run 340-480 completion tokens; this leaves
# ~4x headroom for a longer day without letting a runaway generation drag on.
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))

# --- Database (journal entries) ---
# Defaults to the local Postgres from docker-compose; tests point this at an
# in-memory SQLite instead.
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://coach:coach@localhost:5433/coach"
)

# --- Speech-to-text & embeddings (both OpenAI, regardless of LLM_PROVIDER) ---
# gpt-4o-mini-transcribe is newer and more accurate than whisper-1, at a
# similar price.
STT_MODEL = os.getenv("STT_MODEL", "gpt-4o-mini-transcribe")
# Embedding model for semantic recall over past entries (pgvector).
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# --- Voice output (TTS) ---
# "google" (Cloud TTS — covered by GCP credit, generous free tier, British
# voices) is the default; "elevenlabs" and "openai" are swappable alternatives.
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "google")
# Google Cloud TTS (used when TTS_PROVIDER=google). Chirp3-HD "Callirrhoe" is a
# natural British female. Rate stays at 1.0: slowing her down was meant to sound
# calm and just sounded robotic — the unhurried feeling comes from the writing,
# not from dragging out the delivery.
GOOGLE_TTS_VOICE = os.getenv("GOOGLE_TTS_VOICE", "en-GB-Chirp3-HD-Callirrhoe")
GOOGLE_TTS_LANG = os.getenv("GOOGLE_TTS_LANG", "en-GB")
GOOGLE_TTS_RATE = float(os.getenv("GOOGLE_TTS_RATE", "1.0"))
# OpenAI TTS voice (used when TTS_PROVIDER=openai): coral/shimmer/nova are warm
# and female; fable is British-leaning. Any of the gpt-4o-mini-tts voices work.
TTS_VOICE = os.getenv("TTS_VOICE", "coral")
# ElevenLabs (used when TTS_PROVIDER=elevenlabs). The user's chosen library
# voice; override ELEVENLABS_VOICE_ID to pick another.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "NtS6nEHDYMQC9QczMQuq")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")

# --- Firebase ---
# Admin service-account file, used to verify sign-in tokens.
FIREBASE_CREDENTIALS = os.getenv(
    "FIREBASE_CREDENTIALS", "secrets/firebase-admin.json"
)

# --- Observability (LangSmith) ---
# LangChain auto-traces every chain/agent call when these env vars are
# present — setting the API key is enough. We default tracing on and name the
# project so traces are grouped in the LangSmith UI.
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
if LANGSMITH_API_KEY:
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", os.getenv("LANGSMITH_PROJECT", "performance-coach"))


def missing_required_settings() -> list[str]:
    """Which settings the app can't serve without, given how it's configured.

    Only what every request needs: the coach's own key, and OpenAI's for the
    embeddings behind semantic recall. TTS keys are deliberately not here — if
    speech fails the app still works, and /speak already answers 503.
    """
    missing = []
    if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY (LLM_PROVIDER=openai)")
    if LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY (LLM_PROVIDER=anthropic)")
    if LLM_PROVIDER not in ("openai", "anthropic"):
        missing.append(f"LLM_PROVIDER must be openai or anthropic, got {LLM_PROVIDER!r}")
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY (speech-to-text and recall embeddings)")
    return missing
