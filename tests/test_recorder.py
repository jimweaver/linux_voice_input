import io
import wave

import numpy as np

from voice_input.recorder import Recorder


class FakeStream:
    def __init__(self, frames, callback):
        self._frames = frames
        self._callback = callback
        self.active = False

    def start(self):
        self.active = True
        for indata, frames, time, status in self._frames:
            self._callback(indata, frames, time, status)

    def stop(self):
        self.active = False

    def close(self):
        pass


def test_stop_without_start_returns_empty():
    assert Recorder().stop() == b""


def test_device_passed_to_stream(monkeypatch):
    captured = {}

    class FakeSD:
        @staticmethod
        def InputStream(**kwargs):
            captured.update(kwargs)
            return FakeStream([], None)

    import voice_input.recorder as recorder_module

    monkeypatch.setattr(recorder_module, "sd", FakeSD)
    Recorder(device="pulse").start()
    assert captured["device"] == "pulse"


def test_wav_roundtrip_with_injected_stream(monkeypatch):
    frames = [(np.full((1600, 1), 1000, dtype=np.int16), None, None, None)] * 3
    rec = Recorder()
    monkeypatch.setattr(rec, "_open_stream", lambda cb: FakeStream(frames, cb))
    monkeypatch.setattr(
        "voice_input.recorder.trim_silence",
        lambda pcm, sample_rate, **kw: pcm,  # isolate WAV encoding from trimming
    )
    rec.start()
    wav = rec.stop()
    assert wav[:4] == b"RIFF"
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert w.getnframes() == 4800


def test_trim_silence_cuts_head_and_tail_with_pad():
    from voice_input.recorder import trim_silence

    sr = 16000
    pcm = np.concatenate(
        [
            np.zeros(8000, dtype=np.int16),
            np.full(1600, 2000, dtype=np.int16),
            np.zeros(8000, dtype=np.int16),
        ]
    ).reshape(-1, 1)
    out = trim_silence(pcm, sample_rate=sr)
    assert len(out) == 1600 + 2 * 1600  # signal + 100 ms pad each side


def test_trim_silence_explicit_threshold_keeps_speech_above_it():
    from voice_input.recorder import trim_silence

    pcm = np.full((3200, 1), 600, dtype=np.int16)
    assert len(trim_silence(pcm, sample_rate=16000, threshold=500)) == 3200


def test_trim_silence_auto_threshold_keeps_quiet_speech_on_quiet_mic():
    from voice_input.recorder import trim_silence

    # T2 MacBook mic: noise floor ~6 median, speech ~300
    noise = np.full((8000, 1), 6, dtype=np.int16)
    speech = np.full((3200, 1), 300, dtype=np.int16)
    pcm = np.concatenate([noise, speech, noise], axis=0)
    out = trim_silence(pcm, sample_rate=16000)
    assert len(out) >= 3200  # speech survives (plus padding)


def test_trim_silence_keeps_quiet_trailing_speech_after_loud_speech():
    from voice_input.recorder import trim_silence

    sr = 16000
    noise = np.full((int(0.3 * sr), 1), 30, dtype=np.int16)
    loud = np.full((5 * sr, 1), 3000, dtype=np.int16)
    quiet_tail = np.full((1 * sr, 1), 400, dtype=np.int16)
    tail_noise = np.full((int(0.2 * sr), 1), 30, dtype=np.int16)
    pcm = np.concatenate([noise, loud, quiet_tail, tail_noise], axis=0)
    out = trim_silence(pcm, sample_rate=sr)
    # the quiet final sentence must survive: output spans loud + tail speech
    assert len(out) > len(loud) + len(quiet_tail)


def test_trim_silence_keeps_soft_tail_when_noise_floor_is_near_zero():
    from voice_input.recorder import trim_silence

    # Real capture from a quiet room on the T2 MacBook: speech peaks ~1600,
    # soft trailing words dip to ~85, ambient per-sample p10 ~2.
    sr = 16000
    speech_loud = np.full((3 * sr, 1), 1600, dtype=np.int16)
    speech_soft_tail = np.full((3 * sr, 1), 85, dtype=np.int16)
    silence = np.full((2 * sr, 1), 5, dtype=np.int16)
    pcm = np.concatenate([speech_loud, speech_soft_tail, silence], axis=0)
    out = trim_silence(pcm, sample_rate=sr)
    assert len(out) > len(speech_loud) + len(speech_soft_tail)


def test_trim_silence_keeps_whispered_speech_just_above_ambient():
    from voice_input.recorder import trim_silence

    sr = 16000
    whisper = np.full((2 * sr, 1), 45, dtype=np.int16)
    silence = np.full((1 * sr, 1), 5, dtype=np.int16)
    pcm = np.concatenate([silence, whisper, silence], axis=0)
    out = trim_silence(pcm, sample_rate=sr)
    assert len(out) > len(whisper)


def test_trim_silence_auto_threshold_still_drops_ambient_noise():
    from voice_input.recorder import trim_silence

    pcm = np.full((3200, 1), 41, dtype=np.int16)  # observed ambient max
    assert len(trim_silence(pcm, sample_rate=16000)) == 0


def test_trim_silence_all_quiet_returns_empty():
    from voice_input.recorder import trim_silence

    pcm = np.full((3200, 1), 100, dtype=np.int16)
    assert len(trim_silence(pcm, sample_rate=16000)) == 0


def test_stop_all_silence_returns_empty_bytes(monkeypatch):
    frames = [(np.zeros((1600, 1), dtype=np.int16), None, None, None)] * 3
    rec = Recorder()
    monkeypatch.setattr(rec, "_open_stream", lambda cb: FakeStream(frames, cb))
    rec.start()
    assert rec.stop() == b""


def test_normalize_peak_amplifies_quiet_audio_to_target():
    from voice_input.recorder import normalize_peak

    pcm = np.full((1600, 1), 1000, dtype=np.int16)
    out = normalize_peak(pcm)
    assert int(np.abs(out.astype(np.int32)).max()) == 16384


def test_normalize_peak_leaves_loud_audio_alone():
    from voice_input.recorder import normalize_peak

    pcm = np.full((1600, 1), 20000, dtype=np.int16)
    out = normalize_peak(pcm)
    assert int(np.abs(out.astype(np.int32)).max()) == 20000


def test_normalize_peak_caps_gain_so_noise_is_not_pumped_forever():
    from voice_input.recorder import normalize_peak

    pcm = np.full((1600, 1), 100, dtype=np.int16)
    out = normalize_peak(pcm)
    assert int(np.abs(out.astype(np.int32)).max()) == 3200  # 32x cap


def test_normalize_peak_empty_and_silent_are_safe():
    from voice_input.recorder import normalize_peak

    assert len(normalize_peak(np.zeros((0, 1), dtype=np.int16))) == 0
    assert int(normalize_peak(np.zeros((100, 1), dtype=np.int16)).max()) == 0


def test_stop_normalizes_quiet_recording(monkeypatch):
    frames = [(np.full((1600, 1), 1000, dtype=np.int16), None, None, None)] * 3
    rec = Recorder()
    monkeypatch.setattr(rec, "_open_stream", lambda cb: FakeStream(frames, cb))
    rec.start()
    wav = rec.stop()
    with wave.open(io.BytesIO(wav)) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    assert int(np.abs(pcm.astype(np.int32)).max()) == 16384


def test_stop_writes_raw_and_trimmed_wavs_when_debug_dir_set(monkeypatch, tmp_path):
    frames = [(np.full((1600, 1), 1000, dtype=np.int16), None, None, None)] * 3
    rec = Recorder()
    monkeypatch.setattr(rec, "_open_stream", lambda cb: FakeStream(frames, cb))
    monkeypatch.setenv("LVI_DEBUG_DIR", str(tmp_path))
    rec.start()
    rec.stop()
    names = [p.name for p in tmp_path.iterdir()]
    assert any(n.endswith("_raw.wav") for n in names)
    assert any(n.endswith("_trimmed.wav") for n in names)
