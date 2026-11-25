import pytest

from voice_input.config import ConfigError, load_config


def test_defaults_when_no_config_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.api_key == "sk-test"
    assert cfg.model == "gpt-transcribe"
    assert cfg.hotkey == "f9"
    assert cfg.language is None


def test_config_file_overrides(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = tmp_path / "config.toml"
    p.write_text('api_key = "sk-file"\nmodel = "whisper-1"\nlanguage = "en"\n')
    cfg = load_config(p)
    assert (cfg.api_key, cfg.model, cfg.language) == ("sk-file", "whisper-1", "en")


def test_missing_api_key_is_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_config(tmp_path / "nonexistent.toml")


def test_device_defaults_to_pulse_and_is_overridable(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert load_config(tmp_path / "nonexistent.toml").device == "pulse"
    p = tmp_path / "config.toml"
    p.write_text('device = "hw:0,1"\n')
    assert load_config(p).device == "hw:0,1"
