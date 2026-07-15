"""Voice backend tests — no real API calls; the TTS clients are faked."""
from app import config, voice


def test_speak_uses_elevenlabs_by_default(monkeypatch):
    captured = {}

    def fake_convert(text, voice_id, model_id, output_format):
        captured.update(text=text, voice_id=voice_id)
        return [b"aa", b"bb"]  # streamed chunks

    monkeypatch.setattr(config, "TTS_PROVIDER", "elevenlabs")
    monkeypatch.setattr(voice._eleven.text_to_speech, "convert", fake_convert)

    out = voice.speak("hello there")

    assert out == b"aabb"  # chunks joined
    assert captured["text"] == "hello there"
    assert captured["voice_id"] == config.ELEVENLABS_VOICE_ID


def test_speak_falls_back_to_openai_when_configured(monkeypatch):
    class _Result:
        def read(self):
            return b"openai-mp3"

    monkeypatch.setattr(config, "TTS_PROVIDER", "openai")
    monkeypatch.setattr(
        voice._openai.audio.speech, "create", lambda **kw: _Result()
    )

    assert voice.speak("hi") == b"openai-mp3"
