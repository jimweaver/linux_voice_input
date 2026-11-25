from voice_input.history import log_history, read_history


def test_log_and_read_roundtrip(tmp_path):
    p = tmp_path / "h.jsonl"
    log_history(6.5, "gpt-transcribe", text="你好", path=p)
    entries = read_history(path=p)
    assert entries[0]["text"] == "你好" and entries[0]["status"] == "ok"


def test_read_history_newest_first_and_limit(tmp_path):
    p = tmp_path / "h.jsonl"
    for i in range(15):
        log_history(1.0, "m", text=str(i), path=p)
    entries = read_history(limit=10, path=p)
    assert [e["text"] for e in entries] == [str(i) for i in range(14, 4, -1)]


def test_read_history_skips_bad_lines(tmp_path):
    p = tmp_path / "h.jsonl"
    p.write_text(
        'not json\n{"ts":1,"seconds":2,"model":"m","status":"ok","text":"a","error":""}\n'
    )
    assert len(read_history(path=p)) == 1


def test_trim_to_500_when_over_1000(tmp_path):
    p = tmp_path / "h.jsonl"
    p.write_text("\n".join("{}" for _ in range(1000)) + "\n")
    log_history(1.0, "m", path=p)
    assert len(p.read_text().splitlines()) == 501
