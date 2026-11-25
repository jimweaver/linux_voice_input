import re
import shutil
import subprocess
import time


class TyperError(Exception):
    pass


def _log(message: str) -> None:
    print(f"[voice-input] {message}", flush=True)


# WM_CLASS values (lowercase) whose paste shortcut is Ctrl+Shift+V
TERMINAL_CLASSES = {
    "xfce4-terminal",
    "xterm",
    "uxterm",
    "gnome-terminal",
    "gnome-terminal-server",
    "konsole",
    "alacritty",
    "kitty",
    "wezterm",
    "foot",
    "tilix",
    "terminator",
    "terminology",
    "st",
    "urxvt",
    "hyper",
    "termius",
}


def _active_window_classes(runner) -> set[str]:
    try:
        wid = runner(["xdotool", "getactivewindow"], capture_output=True, timeout=5)
        if wid.returncode != 0:
            return set()
        prop = runner(["xprop", "-id", wid.stdout.decode().strip(), "WM_CLASS"],
                      capture_output=True, timeout=5)
        if prop.returncode != 0:
            return set()
    except (OSError, subprocess.SubprocessError):
        return set()
    return {s.lower() for s in re.findall(r'"([^"]*)"', prop.stdout.decode(errors="replace"))}


def _check(result, what: str) -> None:
    if result.returncode != 0:
        detail = getattr(result, "stderr", b"") or b""
        raise TyperError(f"{what} failed: {detail.decode(errors='replace')}")


def _paste(text: str, runner, sleeper) -> None:
    window_classes = _active_window_classes(runner)
    paste_keys = "ctrl+shift+v" if window_classes & TERMINAL_CLASSES else "ctrl+v"
    try:
        saved = runner(["xclip", "-o", "-selection", "clipboard"],
                       capture_output=True, timeout=5)
    except OSError as exc:
        raise TyperError(f"xclip read failed: {exc}") from exc
    old = saved.stdout if saved.returncode == 0 else b""
    # stdout/stderr MUST be DEVNULL here: xclip forks a selection-serving
    # child that inherits any pipe we hand it, and a PIPEd stream never
    # reaches EOF — subprocess.run then hangs forever (daemon stuck BUSY).
    _check(
        runner(["xclip", "-selection", "clipboard"], input=text.encode(),
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5),
        "xclip set",
    )
    try:
        _check(
            runner(["xdotool", "key", "--clearmodifiers", paste_keys],
                   capture_output=True, timeout=5),
            "xdotool key",
        )
        sleeper(0.3)
    finally:
        try:
            runner(["xclip", "-selection", "clipboard"], input=old,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.SubprocessError) as exc:
            _log(f"could not restore clipboard: {exc}")


def _type_keys(text: str, runner) -> None:
    _check(
        runner(["xdotool", "type", "--clearmodifiers", "--delay", "12", "--", text],
               capture_output=True, timeout=30),
        "xdotool",
    )


def type_text(text: str, runner=None, which=None, sleeper=None) -> None:
    runner = runner or subprocess.run
    which = which or shutil.which
    sleeper = sleeper or time.sleep
    if not text.strip():
        return
    if which("xclip"):
        try:
            _paste(text, runner, sleeper)
            return
        except (TyperError, OSError, subprocess.TimeoutExpired) as exc:
            _log(f"paste failed ({exc}), falling back to keystrokes")
    _type_keys(text, runner)
