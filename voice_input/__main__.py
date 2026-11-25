import functools
import sys
import time

from pynput import keyboard

from voice_input.app import App
from voice_input.config import ConfigError, load_config
from voice_input.history import log_history
from voice_input.hotkeys import HotkeyMatcher
from voice_input.notify import notify
from voice_input.recorder import Recorder
from voice_input.transcribe import transcribe
from voice_input.typer import type_text
from voice_input.usage import log_usage


def main() -> None:
    try:
        config = load_config()
        hotkey = HotkeyMatcher(config.hotkey)
    except ConfigError as exc:
        print(f"voice-input: {exc}", file=sys.stderr)
        sys.exit(2)

    app = App(
        config,
        Recorder(device=config.device),
        functools.partial(transcribe, config=config),
        type_text,
        time.sleep,
        usage_logger=log_usage,
        notifier=notify,
        history_logger=log_history,
    )

    def on_press(key):
        if hotkey.on_press(key):
            app.on_toggle()
        elif key == keyboard.Key.esc:
            app.on_cancel()

    def on_release(key):
        hotkey.on_release(key)

    print(
        f"[voice-input] ready — press {config.hotkey.upper()} to start/stop dictation, "
        "Esc to cancel. Ctrl+C here to quit.",
        flush=True,
    )
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
