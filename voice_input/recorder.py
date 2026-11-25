import io
import os
import time
import wave

import numpy as np
import sounddevice as sd


def _log(message: str) -> None:
    print(f"[voice-input] {message}", flush=True)


def _to_wav(pcm: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def trim_silence(
    pcm: np.ndarray, sample_rate: int, threshold: int | None = None, pad_ms: int = 100
) -> np.ndarray:
    if len(pcm) == 0:
        return pcm
    amplitude = np.abs(pcm.astype(np.int32)).max(axis=1)
    if threshold is None:
        # auto: five times the p10 noise-floor estimate, floored at 40 and
        # capped at 250. Real captures on the T2 MacBook show soft trailing
        # speech dipping to ~70 peak and whispered speech down to ~45, while
        # ambient noise stays <= ~41 and is usually far below — the floor
        # must sit as low as possible so whispering is not cut entirely
        # (floors of 100 and then 50 both ate real speech). The cap keeps
        # long recordings from scaling p10 (which then measures the speech
        # waveform itself) high enough to cut the same tails. Trimming is a
        # cost optimization only — when in doubt, keep the audio.
        threshold = max(40, min(int(np.percentile(amplitude, 10)) * 5, 250))
    voiced = np.nonzero(amplitude > threshold)[0]
    if len(voiced) == 0:
        return pcm[:0]
    pad = int(sample_rate * pad_ms / 1000)
    start = max(0, int(voiced[0]) - pad)
    end = min(len(pcm), int(voiced[-1]) + pad + 1)
    return pcm[start:end]


NORMALIZE_TARGET = 16384  # 0.5 full scale — comfortable level for transcription
NORMALIZE_MAX_GAIN = 32.0


def normalize_peak(
    pcm: np.ndarray, target: int = NORMALIZE_TARGET, max_gain: float = NORMALIZE_MAX_GAIN
) -> np.ndarray:
    if len(pcm) == 0:
        return pcm
    peak = int(np.abs(pcm.astype(np.int32)).max())
    if peak == 0 or peak >= target:
        return pcm
    gain = min(target / peak, max_gain)
    return np.rint(pcm.astype(np.float64) * gain).astype(np.int16)


class Recorder:
    def __init__(self, sample_rate: int = 16000, device: str | None = None):
        self.sample_rate = sample_rate
        self.device = device
        self.is_recording = False
        self._frames: list[np.ndarray] = []
        self._stream = None

    def _open_stream(self, callback):
        return sd.InputStream(
            device=self.device,
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            callback=callback,
        )

    def start(self) -> None:
        self._frames = []
        self._stream = self._open_stream(self._on_audio)
        self._stream.start()
        self.is_recording = True

    def _on_audio(self, indata, frames, time, status) -> None:
        self._frames.append(indata.copy())

    def stop(self) -> bytes:
        if not self.is_recording:
            return b""
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self.is_recording = False
        if not self._frames:
            return b""
        raw = np.concatenate(self._frames, axis=0)
        self._frames = []
        trimmed = normalize_peak(trim_silence(raw, sample_rate=self.sample_rate))
        _log(
            f"captured {len(raw) / self.sample_rate:.2f}s, "
            f"kept {len(trimmed) / self.sample_rate:.2f}s after silence trim"
        )
        debug_dir = os.environ.get("LVI_DEBUG_DIR")
        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
            with open(os.path.join(debug_dir, f"{stamp}_raw.wav"), "wb") as f:
                f.write(_to_wav(raw, self.sample_rate))
            with open(os.path.join(debug_dir, f"{stamp}_trimmed.wav"), "wb") as f:
                f.write(_to_wav(trimmed, self.sample_rate))
        if len(trimmed) == 0:
            return b""
        return _to_wav(trimmed, self.sample_rate)
