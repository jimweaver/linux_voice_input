import pytest

from voice_input.app import App
from voice_input.config import Config
from voice_input.transcribe import TranscribeError


class FakeRecorder:
    sample_rate = 16000

    def __init__(self, wav=None):
        self.wav = wav if wav is not None else b"\x00" * (44 + 2 * 16000)  # 1.0 s PCM16 mono
        self.start_calls = 0
        self.stopped = False

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stopped = True
        return self.wav


class ExplodingRecorder(FakeRecorder):
    def stop(self):
        raise RuntimeError("device unplugged")


class FakeTranscriber:
    def __init__(self, text="hi"):
        self.text = text
        self.calls = []

    def __call__(self, wav):
        self.calls.append(wav)
        return self.text


class FailingTranscriber:
    def __call__(self, wav):
        raise TranscribeError("boom")


class FakeTyper:
    def __init__(self):
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)


def make_app(wav=None, transcriber=None, recorder=None):
    config = Config(api_key="sk", model="m", hotkey="f9", language=None, device="pulse")
    recorder = recorder if recorder is not None else FakeRecorder(wav)
    transcriber = transcriber if transcriber is not None else FakeTranscriber()
    typer = FakeTyper()
    app = App(config, recorder, transcriber, typer, lambda seconds: None)
    app.recorder = recorder
    app.transcriber = transcriber
    app.typer = typer
    return app


def drain(app):
    app.join_worker()


def test_toggle_starts_and_stops_recording():
    app = make_app()
    app.on_toggle()
    assert app.state == "RECORDING"
    app.on_toggle()
    drain(app)
    assert app.state == "IDLE"
    assert app.typer.calls == ["hi"]


def test_toggle_ignored_while_busy():
    app = make_app()
    app.state = "BUSY"
    app.on_toggle()
    assert app.recorder.start_calls == 0


def test_too_short_recording_skips_api():
    app = make_app(wav=b"")
    app.on_toggle()
    app.on_toggle()
    drain(app)
    assert app.transcriber.calls == []
    assert app.typer.calls == []


def test_transcribe_error_recovers_to_idle():
    app = make_app(transcriber=FailingTranscriber())
    app.on_toggle()
    app.on_toggle()
    drain(app)
    assert app.state == "IDLE"
    assert app.typer.calls == []


def test_esc_cancels_recording():
    app = make_app()
    app.on_toggle()
    app.on_cancel()
    assert app.state == "IDLE"
    assert app.recorder.stopped and app.typer.calls == []


def test_very_short_recording_skips_api():
    wav = b"\x00" * (44 + 2 * 1600)  # 0.1 s of PCM16 mono at 16 kHz
    app = make_app(wav=wav)
    app.on_toggle()
    app.on_toggle()
    drain(app)
    assert app.transcriber.calls == []
    assert app.typer.calls == []
    assert app.state == "IDLE"


def test_stop_failure_recovers_to_idle():
    app = make_app(recorder=ExplodingRecorder())
    app.on_toggle()
    app.on_toggle()
    drain(app)
    assert app.state == "IDLE"
    assert app.typer.calls == []


def test_usage_logged_after_transcription():
    app = make_app()
    calls = []
    app.usage_logger = lambda seconds, model: calls.append((seconds, model))
    app.on_toggle()
    app.on_toggle()
    drain(app)
    assert calls == [(pytest.approx(1.0, abs=0.01), "m")]


class FakeNotifier:
    def __init__(self):
        self.calls = []

    def __call__(self, summary, body="", urgent=False, persist=False):
        self.calls.append((summary, body, urgent, persist))


class FakeHistory:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds, model, text="", status="ok", error=""):
        self.calls.append(
            {"seconds": seconds, "model": model, "status": status, "text": text, "error": error}
        )


def make_observed_app(**kwargs):
    app = make_app(**kwargs)
    app.notifier = FakeNotifier()
    app.history_logger = FakeHistory()
    return app


def test_notifies_recording_then_transcribing_then_done():
    app = make_observed_app()
    app.on_toggle()
    assert app.notifier.calls[0][0].startswith("🔴 錄緊")
    app.on_toggle()
    assert any(c[0].startswith("⏳ 轉寫緊") for c in app.notifier.calls)
    drain(app)
    assert any(c[0].startswith("✅ 完成") for c in app.notifier.calls)


def test_recording_and_transcribing_notifications_persist_terminal_ones_do_not():
    app = make_observed_app()
    app.on_toggle()
    recording = app.notifier.calls[0]
    assert recording[0].startswith("🔴 錄緊") and recording[3] is True
    app.on_toggle()
    transcribing = [c for c in app.notifier.calls if c[0].startswith("⏳ 轉寫緊")]
    assert transcribing and transcribing[0][3] is True
    drain(app)
    done = app.notifier.calls[-1]
    assert done[0].startswith("✅ 完成") and done[3] is False


def test_history_logged_on_success():
    app = make_observed_app()
    app.on_toggle()
    app.on_toggle()
    drain(app)
    assert len(app.history_logger.calls) == 1
    entry = app.history_logger.calls[0]
    assert entry["status"] == "ok" and entry["text"] == "hi" and entry["model"] == "m"


def test_history_error_and_urgent_notify_on_transcription_failure():
    app = make_observed_app(transcriber=FailingTranscriber())
    app.on_toggle()
    app.on_toggle()
    drain(app)
    entry = app.history_logger.calls[0]
    assert entry["status"] == "error" and "boom" in entry["error"]
    assert any(c[2] for c in app.notifier.calls)  # some notification was urgent


class FailingTyper:
    def __call__(self, text):
        raise RuntimeError("no display")


def test_typing_failure_logged_and_urgent():
    app = make_observed_app()
    app.typer = FailingTyper()
    app.on_toggle()
    app.on_toggle()
    drain(app)
    entry = app.history_logger.calls[0]
    assert entry["status"] == "error" and "no display" in entry["error"]
    assert any(c[2] for c in app.notifier.calls)


def test_cancel_notifies():
    app = make_observed_app()
    app.on_toggle()
    app.on_cancel()
    assert any("ancel" in c[0] for c in app.notifier.calls)
    assert app.history_logger.calls == []


class EmptyTranscriber:
    def __call__(self, wav):
        return "   "


def test_history_logged_when_no_speech_recognized():
    app = make_observed_app(transcriber=EmptyTranscriber())
    app.on_toggle()
    app.on_toggle()
    drain(app)
    entry = app.history_logger.calls[0]
    assert entry["status"] == "empty"


def test_history_logged_when_recording_too_short():
    app = make_observed_app(wav=b"")
    app.on_toggle()
    app.on_toggle()
    drain(app)
    entry = app.history_logger.calls[0]
    assert entry["status"] == "too_short"
