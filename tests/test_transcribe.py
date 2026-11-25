import pytest

import voice_input.transcribe as transcribe_module
from voice_input.config import Config
from voice_input.transcribe import TranscribeError, transcribe


class _FakeTranscriptions:
    def __init__(self, captured):
        self._captured = captured

    def create(self, model, file, **kwargs):
        self._captured["model"] = model
        self._captured["filename"] = file[0]
        self._captured.update(kwargs)

        class _Result:
            text = "  hello world  "

        return _Result()


class FakeClient:
    def __init__(self, captured):
        self.audio = type("Audio", (), {"transcriptions": _FakeTranscriptions(captured)})()


class FailingClient:
    def __init__(self):
        def _boom(**kwargs):
            raise RuntimeError("network down")

        self.audio = type(
            "Audio", (), {"transcriptions": type("T", (), {"create": staticmethod(_boom)})()}
        )()


def _config(**overrides):
    base = {"api_key": "sk", "model": "whisper-1", "hotkey": "f9", "language": "en", "device": "pulse"}
    return Config(**{**base, **overrides})


def test_transcribe_sends_wav_and_returns_text(monkeypatch):
    captured = {}
    monkeypatch.setattr(transcribe_module, "_client", lambda key: FakeClient(captured))
    text = transcribe(b"RIFF....", _config())
    assert text == "hello world"
    assert captured["model"] == "whisper-1"
    assert captured["language"] == "en"
    assert captured["filename"].endswith(".wav")


def test_api_error_wrapped(monkeypatch):
    monkeypatch.setattr(transcribe_module, "_client", lambda key: FailingClient())
    with pytest.raises(TranscribeError):
        transcribe(b"RIFF....", _config(model="m", language=None))


def test_none_language_not_sent(monkeypatch):
    captured = {}
    monkeypatch.setattr(transcribe_module, "_client", lambda key: FakeClient(captured))
    transcribe(b"RIFF....", _config(language=None))
    assert "language" not in captured


def test_client_has_timeout(monkeypatch):
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return FakeClient({})

    monkeypatch.setattr(transcribe_module.openai, "OpenAI", fake_openai)
    transcribe(b"RIFF....", _config())
    assert captured.get("timeout") == 30.0


def test_client_uses_retries(monkeypatch):
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return FakeClient({})

    monkeypatch.setattr(transcribe_module.openai, "OpenAI", fake_openai)
    transcribe(b"RIFF....", _config())
    assert captured.get("max_retries") == 2
