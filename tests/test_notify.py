from voice_input.notify import notify


def test_notify_calls_notify_send_with_replace_id():
    calls = []
    notify("🔴 錄緊 Recording…", run=lambda *a, **k: calls.append(a[0]))
    assert calls[0][:2] == ["notify-send", "-r"]


def test_notify_urgent_uses_critical():
    calls = []
    notify("Dictation failed", "boom", urgent=True, run=lambda *a, **k: calls.append(a[0]))
    assert "critical" in calls[0]


def test_notify_persist_uses_zero_timeout():
    calls = []
    notify("🔴 錄緊 Recording…", persist=True, run=lambda *a, **k: calls.append(a[0]))
    i = calls[0].index("-t")
    assert calls[0][i + 1] == "0"


def test_notify_default_timeout_is_transient():
    calls = []
    notify("x", run=lambda *a, **k: calls.append(a[0]))
    i = calls[0].index("-t")
    assert calls[0][i + 1] == "2000"


def test_notify_swallows_errors():
    def boom(*a, **k):
        raise OSError("missing")

    notify("x", run=boom)  # must not raise
