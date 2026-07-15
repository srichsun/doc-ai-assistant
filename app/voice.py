"""Voice in and out.

Speech in: OpenAI Whisper turns recorded audio into text (needs OPENAI_API_KEY).

Speech out: the coach's reply is read aloud. Two interchangeable backends behind
one speak() call — ElevenLabs (real-sounding, the default) and OpenAI TTS (the
simpler fallback) — chosen by config.TTS_PROVIDER, so swapping voices never
touches the callers.
"""
import io

from elevenlabs.client import ElevenLabs
from openai import OpenAI

from app import config

_openai = OpenAI(api_key=config.OPENAI_API_KEY)
_eleven = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)


def transcribe(audio: bytes, filename: str = "audio.webm") -> str:
    """Turn recorded audio into text with Whisper.

    The SDK looks at the file name's extension to know the audio format, so we
    give the bytes a name.
    """
    buf = io.BytesIO(audio)
    buf.name = filename
    result = _openai.audio.transcriptions.create(model="whisper-1", file=buf)
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
    if config.TTS_PROVIDER == "openai":
        return _speak_openai(text, voice)
    return _speak_elevenlabs(text, voice)
