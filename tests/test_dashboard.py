import subprocess

import pytest

from voice_input.dashboard import (
    ServiceError,
    apply_settings,
    clean_hotkey,
    normalize_language,
    service_active,
    set_service,
)


def test_service_active_true_and_false():
    ok = lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=b"active\n")
    dead = lambda *a, **k: subprocess.CompletedProcess(a, 3, stdout=b"inactive\n")
    assert service_active(run=ok) is True
    assert service_active(run=dead) is False


def test_service_active_systemctl_missing():
    def boom(*a, **k):
        raise OSError("bus error")

    assert service_active(run=boom) is False


def test_service_active_systemctl_timeout():
    def hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="systemctl", timeout=5)

    assert service_active(run=hang) is False


def test_set_service_timeout_raises_service_error():
    def hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="systemctl", timeout=5)

    with pytest.raises(ServiceError):
        set_service(True, run=hang)


def test_set_service_raises_on_failure():
    bad = lambda *a, **k: subprocess.CompletedProcess(a, 1, stderr=b"nope")
    with pytest.raises(ServiceError):
        set_service(True, run=bad)


def test_apply_settings_writes_and_restarts(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('api_key = "sk"\n')
    calls = []
    apply_settings(
        p, "f10", "yue",
        run=lambda *a, **k: calls.append(a) or subprocess.CompletedProcess(a, 0),
    )
    text = p.read_text()
    assert 'hotkey = "f10"' in text and 'language = "yue"' in text
    assert any("restart" in " ".join(c[0]) for c in calls)


def test_apply_settings_auto_language_removes_key(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('language = "en"\n')
    apply_settings(p, "f9", None, run=lambda *a, **k: subprocess.CompletedProcess(a, 0))
    assert "language" not in p.read_text()


def test_clean_hotkey():
    assert clean_hotkey(" F9 ") == "f9"
    assert clean_hotkey("scroll_lock") == "scroll_lock"
    assert clean_hotkey("") is None
    assert clean_hotkey('f9"') is None
    assert clean_hotkey("a b") is None
    assert clean_hotkey("f\\9") is None


def test_normalize_language():
    assert normalize_language("Auto (detect)") is None
    assert normalize_language("AUTO") is None
    assert normalize_language("auto ") is None
    assert normalize_language("") is None
    assert normalize_language(" Yue ") == "yue"
    assert normalize_language("EN") == "en"
    assert normalize_language("zh-cn") == "zh-cn"


def test_normalize_language_rejects_invalid_codes():
    with pytest.raises(ValueError):
        normalize_language("english!")
    with pytest.raises(ValueError):
        normalize_language("f9\"; drop table")


def test_apply_settings_writes_model_device_api_key_and_chmod(tmp_path):
    import os

    p = tmp_path / "config.toml"
    p.write_text('hotkey = "f9"\n')
    apply_settings(
        p, "f9", None, model="whisper-1", device="hw:1,0", api_key="sk-new",
        run=lambda *a, **k: subprocess.CompletedProcess(a, 0),
    )
    text = p.read_text()
    assert 'model = "whisper-1"' in text
    assert 'device = "hw:1,0"' in text
    assert 'api_key = "sk-new"' in text
    assert os.stat(p).st_mode & 0o777 == 0o600


def test_apply_settings_blank_api_key_keeps_existing(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('api_key = "sk-old"\n')
    apply_settings(
        p, "f9", None, model=None, device=None, api_key="",
        run=lambda *a, **k: subprocess.CompletedProcess(a, 0),
    )
    assert 'api_key = "sk-old"' in p.read_text()


def test_clean_model():
    from voice_input.dashboard import clean_model

    assert clean_model(" GPT-4o-Transcribe ") == "gpt-4o-transcribe"
    assert clean_model("gpt-4o-mini-transcribe") == "gpt-4o-mini-transcribe"
    assert clean_model("") is None
    assert clean_model("bad model!") is None


def test_clean_device():
    from voice_input.dashboard import clean_device

    assert clean_device("") == "pulse"
    assert clean_device(" hw:1,0 ") == "hw:1,0"
    assert clean_device("Apple T2 Audio: Codec Input (hw:0,3)") == \
        "Apple T2 Audio: Codec Input (hw:0,3)"
    assert clean_device('de"vice') is None
    assert clean_device("de\\vice") is None
    assert clean_device("de\nvice") is None


def test_format_history_shows_status_duration_and_snippet():
    from voice_input.dashboard import _format_history

    entries = [
        {"ts": 1793742268.0, "seconds": 6.5, "status": "ok", "text": "你好世界" * 20, "error": ""},
        {"ts": 1793742268.0, "seconds": 0.0, "status": "error", "text": "", "error": "boom"},
    ]
    out = _format_history(entries)
    assert "✅" in out and "❌" in out
    assert "6.5" in out and "boom" in out
    assert "…" in out  # long text is truncated


def test_format_history_empty():
    from voice_input.dashboard import _format_history

    assert _format_history([]) == "No dictations yet."


def test_history_row_returns_label_and_full_text():
    from voice_input.dashboard import _history_row

    long_text = "你好世界" * 20
    entry = {"ts": 1793742268.0, "seconds": 6.5, "status": "ok", "text": long_text, "error": ""}
    label, full_text = _history_row(entry)
    assert "✅" in label and "…" in label
    assert full_text == long_text  # untruncated, newlines preserved


def test_history_row_failed_entry_has_empty_full_text():
    from voice_input.dashboard import _history_row

    entry = {"ts": 1793742268.0, "seconds": 0.0, "status": "error", "text": "", "error": "boom"}
    label, full_text = _history_row(entry)
    assert "❌" in label and "boom" in label
    assert full_text == ""


def test_history_row_skips_unparseable_entry():
    from voice_input.dashboard import _history_row

    assert _history_row({"ts": "nope", "seconds": 1.0}) is None


def test_clean_hotkey_accepts_modifier_combos():
    assert clean_hotkey("cmd+s") == "cmd+s"
    assert clean_hotkey(" CMD+S ") == "cmd+s"
    assert clean_hotkey("ctrl+alt+s") == "ctrl+alt+s"
