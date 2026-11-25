import subprocess
from types import SimpleNamespace

import pytest

from voice_input.typer import TyperError, type_text

NO_XCLIP = lambda c: None  # noqa: E731


def ok_run(calls):
    def run(argv, **kw):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=b"old clip", stderr=b"")

    return run


def test_empty_text_is_noop():
    calls = []
    type_text("   ", runner=ok_run(calls), which=NO_XCLIP, sleeper=lambda s: None)
    assert calls == []


def test_text_passed_verbatim_no_shell():
    calls = []
    type_text(
        "héllo\nit's $HOME", runner=ok_run(calls), which=NO_XCLIP, sleeper=lambda s: None
    )
    argv = calls[0]
    assert argv[0] == "xdotool"
    assert "héllo\nit's $HOME" in argv
    assert "--clearmodifiers" in argv


def test_nonzero_exit_raises():
    def run(argv, **kw):
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"err")

    with pytest.raises(TyperError):
        type_text("hi", runner=run, which=NO_XCLIP, sleeper=lambda s: None)


def test_paste_sets_clipboard_pastes_and_restores():
    calls = []
    type_text(
        "你好",
        runner=ok_run(calls),
        which=lambda c: "/usr/bin/xclip",
        sleeper=lambda s: None,
    )
    assert calls[0] == ["xdotool", "getactivewindow"]  # window id probe
    assert calls[1][0] == "xprop" and "WM_CLASS" in calls[1]  # class probe
    assert calls[2] == ["xclip", "-o", "-selection", "clipboard"]  # save old
    assert calls[3][:2] == ["xclip", "-selection"]  # set new text
    assert calls[4][:2] == ["xdotool", "key"] and "ctrl+v" in calls[4]  # paste
    assert calls[5][:2] == ["xclip", "-selection"]  # restore old


def test_paste_restores_users_clipboard_content():
    inputs = []

    def run(argv, **kw):
        if "input" in kw:
            inputs.append(kw["input"])
        return SimpleNamespace(returncode=0, stdout=b"old clip", stderr=b"")

    type_text("你好", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert inputs[0] == "你好".encode()
    assert inputs[1] == b"old clip"


def test_falls_back_to_xdotool_type_without_xclip():
    calls = []
    type_text("hi", runner=ok_run(calls), which=NO_XCLIP, sleeper=lambda s: None)
    assert calls[0][:2] == ["xdotool", "type"]


def test_falls_back_when_paste_fails():
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        rc = 1 if argv[:2] == ["xdotool", "key"] else 0
        return SimpleNamespace(returncode=rc, stdout=b"old", stderr=b"err")

    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert calls[-1][:2] == ["xdotool", "type"]


def test_initial_clipboard_read_error_falls_back_to_type():
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if argv[:2] == ["xclip", "-o"]:
            raise OSError("xclip died")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert calls[-1][:2] == ["xdotool", "type"]


def test_restore_error_does_not_mask_paste_failure():
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if argv[:2] == ["xdotool", "key"]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"err")
        if argv[:2] == ["xclip", "-selection"] and "input" in kw and kw["input"] == b"old":
            raise OSError("restore died")
        return SimpleNamespace(returncode=0, stdout=b"old", stderr=b"")

    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert calls[-1][:2] == ["xdotool", "type"]


def test_restore_nonzero_after_successful_paste_does_not_raise():
    def run(argv, **kw):
        rc = 1 if (argv[:2] == ["xclip", "-selection"] and kw.get("input") == b"old") else 0
        return SimpleNamespace(returncode=rc, stdout=b"old", stderr=b"err")

    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)


def test_xclip_set_does_not_pipe_stderr():
    # xclip forks a selection-serving child that inherits fds; a PIPEd
    # stderr never reaches EOF and subprocess.run hangs forever (real bug:
    # daemon stuck in BUSY after first paste)
    import subprocess as sp

    kwargs_seen = []

    def run(argv, **kw):
        kwargs_seen.append(kw)
        return SimpleNamespace(returncode=0, stdout=b"old", stderr=b"")

    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    set_call = kwargs_seen[3]
    assert set_call.get("stderr") is sp.DEVNULL
    assert set_call.get("stdout") is sp.DEVNULL


def test_all_subprocess_calls_have_timeout():
    kwargs_seen = []

    def run(argv, **kw):
        kwargs_seen.append(kw)
        return SimpleNamespace(returncode=0, stdout=b"old", stderr=b"")

    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert all("timeout" in kw for kw in kwargs_seen)


def test_subprocess_timeout_falls_back_to_type():
    import subprocess as sp

    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if argv[:2] == ["xdotool", "key"]:
            raise sp.TimeoutExpired(cmd=argv, timeout=5)
        return SimpleNamespace(returncode=0, stdout=b"old", stderr=b"")

    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert calls[-1][:2] == ["xdotool", "type"]


def _run_with_wm_class(prop_line: bytes, calls=None):
    def run(argv, **kw):
        if calls is not None:
            calls.append(argv)
        if argv[:2] == ["xdotool", "getactivewindow"]:
            return SimpleNamespace(returncode=0, stdout=b"123\n", stderr=b"")
        if argv[0] == "xprop":
            return SimpleNamespace(returncode=0, stdout=prop_line, stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"old clip", stderr=b"")

    return run


def _key_calls(calls):
    return [c for c in calls if c[:2] == ["xdotool", "key"]]


def test_paste_uses_ctrl_shift_v_in_terminal():
    calls = []
    run = _run_with_wm_class(
        b'WM_CLASS(STRING) = "xfce4-terminal", "Xfce4-terminal"\n', calls
    )
    type_text("你好", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert "ctrl+shift+v" in _key_calls(calls)[0]


def test_paste_uses_ctrl_shift_v_in_termius():
    calls = []
    run = _run_with_wm_class(
        b'WM_CLASS(STRING) = "termius", "termius"\n', calls
    )
    type_text("你好", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert "ctrl+shift+v" in _key_calls(calls)[0]


def test_paste_uses_ctrl_v_in_browser():
    calls = []
    run = _run_with_wm_class(b'WM_CLASS(STRING) = "firefox", "Firefox"\n', calls)
    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert "ctrl+v" in _key_calls(calls)[0]


def test_paste_defaults_to_ctrl_v_when_class_query_fails():
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if argv[:2] == ["xdotool", "getactivewindow"]:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"err")
        return SimpleNamespace(returncode=0, stdout=b"old clip", stderr=b"")

    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert "ctrl+v" in _key_calls(calls)[0]  # unknown window -> paste with ctrl+v


def test_paste_defaults_to_ctrl_v_when_class_query_raises():
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if argv[:2] == ["xdotool", "getactivewindow"]:
            raise OSError("no X")
        return SimpleNamespace(returncode=0, stdout=b"old", stderr=b"")

    type_text("hi", runner=run, which=lambda c: "/usr/bin/xclip", sleeper=lambda s: None)
    assert "ctrl+v" in _key_calls(calls)[0]
