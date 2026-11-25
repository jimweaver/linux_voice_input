from datetime import date

import pytest

from voice_input.usage import cost_of, log_usage, summarize


def test_cost_of_known_and_unknown_models():
    assert cost_of("gpt-transcribe", 60.0) == pytest.approx(0.0045)
    assert cost_of("whisper-1", 60.0) == pytest.approx(0.006)
    assert cost_of("some-future-model", 60.0) == pytest.approx(0.0045)


def test_log_and_summarize_today_week_total(tmp_path):
    log = tmp_path / "usage.jsonl"
    log_usage(30.0, "gpt-transcribe", path=log)
    log_usage(30.0, "whisper-1", path=log)
    s = summarize(log)
    assert s["today"]["seconds"] == pytest.approx(60.0)
    assert s["today"]["cost"] == pytest.approx(30 / 60 * 0.0045 + 30 / 60 * 0.006)
    assert s["week"]["seconds"] == pytest.approx(60.0)
    assert s["total"]["seconds"] == pytest.approx(60.0)


def test_summarize_skips_corrupt_lines(tmp_path):
    log = tmp_path / "usage.jsonl"
    log.write_text(
        '{"ts": 1, "seconds": 5, "model": "gpt-transcribe"}\nNOT JSON\n{"ts": "x"}\n'
    )
    s = summarize(log, today=date(1970, 1, 1))
    assert s["total"]["seconds"] == pytest.approx(5.0)


def test_summarize_missing_file(tmp_path):
    s = summarize(tmp_path / "nope.jsonl")
    assert s["total"] == {"seconds": 0.0, "cost": 0.0}


def test_summarize_skips_absurd_timestamps(tmp_path):
    log = tmp_path / "usage.jsonl"
    log.write_text(
        '{"ts": 1e300, "seconds": 5, "model": "gpt-transcribe"}\n'
        '{"ts": -1e300, "seconds": 5, "model": "gpt-transcribe"}\n'
        '{"ts": 1, "seconds": 5, "model": "gpt-transcribe"}\n'
    )
    s = summarize(log, today=date(1970, 1, 1))
    assert s["total"]["seconds"] == pytest.approx(5.0)
