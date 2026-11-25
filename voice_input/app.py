import io
import shutil
import subprocess
import threading
import wave

import numpy as np

from voice_input.config import Config

IDLE = "IDLE"
RECORDING = "RECORDING"
BUSY = "BUSY"


def _beep(frequency: float = 880.0, duration: float = 0.08) -> None:
    if not shutil.which("paplay"):
        return
    t = np.linspace(0, duration, int(16000 * duration), endpoint=False)
    tone = (np.sin(2 * np.pi * frequency * t) * 8000).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(tone.tobytes())
    try:
        subprocess.Popen(
            ["paplay", "-"], stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).communicate(buf.getvalue())
    except OSError:
        pass


def _log(message: str) -> None:
    print(f"[voice-input] {message}", flush=True)


class App:
    def __init__(self, config: Config, recorder, transcriber, typer, sleeper,
                 usage_logger=None, notifier=None, history_logger=None):
        self.config = config
        self.recorder = recorder
        self.transcriber = transcriber
        self.typer = typer
        self.sleeper = sleeper
        self.usage_logger = usage_logger
        self.notifier = notifier
        self.history_logger = history_logger
        self.state = IDLE
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def _notify(self, summary: str, body: str = "", urgent: bool = False, persist: bool = False) -> None:
        if self.notifier is None:
            return
        try:
            self.notifier(summary, body, urgent=urgent, persist=persist)
        except Exception as exc:
            _log(f"notification failed: {exc}")

    def _log_history(self, seconds: float, text: str = "", status: str = "ok", error: str = "") -> None:
        if self.history_logger is None:
            return
        try:
            self.history_logger(seconds, self.config.model, text=text, status=status, error=error)
        except Exception as exc:
            _log(f"history logging failed: {exc}")

    def on_toggle(self) -> None:
        with self._lock:
            if self.state == IDLE:
                try:
                    self.recorder.start()
                except Exception as exc:
                    _log(f"could not start recording (microphone available?): {exc}")
                    return
                self.state = RECORDING
                _log("recording… press the hotkey again to stop, Esc to cancel")
                _beep()
                self._notify(
                    "🔴 錄緊 Recording…",
                    f"press {self.config.hotkey.upper()} again to stop, Esc to cancel",
                    persist=True,
                )
            elif self.state == RECORDING:
                self.state = BUSY
                _beep(660.0)
                self._notify("⏳ 轉寫緊 Transcribing…", persist=True)
                self._worker = threading.Thread(target=self._process, daemon=True)
                self._worker.start()
            else:
                _log("busy transcribing, hotkey ignored")

    def on_cancel(self) -> None:
        with self._lock:
            if self.state != RECORDING:
                return
            self.recorder.stop()
            self.state = IDLE
            _log("recording cancelled")
            self._notify("Cancelled")

    def _process(self) -> None:
        try:
            wav = self.recorder.stop()
            seconds = (len(wav) - 44) / 2 / self.recorder.sample_rate if wav else 0.0
            if not wav or seconds < 0.4:
                _log(f"recording too short ({seconds:.2f}s), nothing transcribed")
                self._notify("錄音太短 Too short", "nothing transcribed")
                self._log_history(
                    seconds, status="too_short", error=f"recording too short ({seconds:.2f}s)"
                )
                return
            _log("transcribing…")
            try:
                text = self.transcriber(wav)
            except Exception as exc:
                _log(f"transcription failed: {exc}")
                self._notify("Dictation failed", str(exc), urgent=True)
                self._log_history(seconds, status="error", error=str(exc))
                return
            if not text.strip():
                _log("transcription was empty, nothing typed")
                self._notify("聽唔到嘢 No speech recognized", "nothing typed")
                self._log_history(seconds, status="empty", error="no speech recognized")
                return
            if self.usage_logger is not None:
                try:
                    self.usage_logger(seconds, self.config.model)
                except Exception as exc:
                    _log(f"usage logging failed: {exc}")
            _log(f"typing {len(text)} chars: {text!r}")
            self.sleeper(0.15)
            try:
                self.typer(text)
            except Exception as exc:
                _log(f"typing failed: {exc}")
                self._notify("Typing failed", str(exc), urgent=True)
                self._log_history(seconds, text=text, status="error", error=str(exc))
                return
            self._notify("✅ 完成 Done", f"{len(text)} chars typed")
            self._log_history(seconds, text=text, status="ok")
        except Exception as exc:
            _log(f"recording failed: {exc}")
        finally:
            with self._lock:
                self.state = IDLE

    def join_worker(self) -> None:
        if self._worker is not None:
            self._worker.join()
            self._worker = None
