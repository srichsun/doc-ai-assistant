"""Voice in and out.

Speech in: OpenAI Whisper turns recorded audio into text (needs OPENAI_API_KEY).

Speech out: the coach's reply is read aloud. Two interchangeable backends behind
one speak() call — ElevenLabs (real-sounding, the default) and OpenAI TTS (the
simpler fallback) — chosen by config.TTS_PROVIDER, so swapping voices never
touches the callers.
"""
import io
import re

from elevenlabs.client import ElevenLabs
from openai import OpenAI

from app import config

_openai = OpenAI(api_key=config.OPENAI_API_KEY)
_eleven = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)


def _plain(text: str) -> str:
    """Strip Markdown to plain prose before speaking it.

    The coach now replies in Markdown (bold, headers, lists). Reading the raw
    symbols aloud sounds wrong and wastes TTS characters, so we flatten them.
    """
    t = re.sub(r"```.*?```", "", text, flags=re.S)     # code blocks
    t = re.sub(r"`([^`]*)`", r"\1", t)                  # inline code
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)      # links -> text
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M) # headers
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)      # bullets
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.M)      # numbered items
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)          # quotes
    t = re.sub(r"-{3,}", "", t)                          # horizontal rules
    t = re.sub(r"(\*\*|__|\*|_)", "", t)                # bold/italic marks
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def transcribe(audio: bytes, filename: str = "audio.webm") -> str:
    """Turn recorded audio into text with Whisper.

    The SDK looks at the file name's extension to know the audio format, so we
    give the bytes a name.
    """
    buf = io.BytesIO(audio)
    buf.name = filename
    result = _openai.audio.transcriptions.create(
        model=config.STT_MODEL, file=buf
    )
    return result.text


def _speak_openai(text: str, voice: str | None) -> bytes:
    """OpenAI TTS fallback."""
    result = _openai.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice or config.TTS_VOICE,
        input=text,
    )
    return result.read()


def _speak_elevenlabs(text: str, voice: str | None) -> bytes:
    """ElevenLabs TTS — the real-sounding voice. Returns mp3 bytes.

    convert() streams the audio back in chunks; we join them into one blob.
    """
    chunks = _eleven.text_to_speech.convert(
        text=text,
        voice_id=voice or config.ELEVENLABS_VOICE_ID,
        model_id=config.ELEVENLABS_MODEL,
        output_format="mp3_44100_128",
    )
    return b"".join(chunks)


def speak(text: str, voice: str | None = None) -> bytes:
    """Turn text into spoken audio (mp3 bytes) using the configured backend."""
    text = _plain(text)  # don't read Markdown symbols aloud / waste characters
    if config.TTS_PROVIDER == "openai":
        return _speak_openai(text, voice)
    return _speak_elevenlabs(text, voice)
