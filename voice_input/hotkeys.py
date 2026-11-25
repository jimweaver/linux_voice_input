from pynput import keyboard

from voice_input.config import ConfigError

MODIFIER_GROUPS = {
    "cmd": {keyboard.Key.cmd, keyboard.Key.cmd_r},
    "ctrl": {keyboard.Key.ctrl, keyboard.Key.ctrl_r},
    "alt": {keyboard.Key.alt, keyboard.Key.alt_r},
    "shift": {keyboard.Key.shift, keyboard.Key.shift_r},
}


def _resolve_trigger(name: str):
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    try:
        return keyboard.Key[name]
    except KeyError:
        raise ConfigError(
            f"Unknown hotkey key {name!r}. Use a single character or a pynput Key "
            "name such as f9, f8, scroll_lock, pause."
        )


class HotkeyMatcher:
    """Matches a hotkey spec like "f9" or "cmd+s" against pynput key events.

    With no modifiers, the trigger fires regardless of modifier state
    (legacy behavior). With modifiers, the pressed modifier groups must
    match exactly. Auto-repeated presses of a held trigger fire only once.
    """

    def __init__(self, spec: str):
        parts = [p.strip() for p in spec.strip().lower().split("+") if p.strip()]
        if not parts:
            raise ConfigError("Empty hotkey spec.")
        modifiers = set()
        for name in parts[:-1]:
            if name == "fn":
                raise ConfigError(
                    "The fn key is handled by the Mac keyboard firmware and is "
                    "invisible to Linux — use cmd/ctrl/alt/shift instead."
                )
            if name not in MODIFIER_GROUPS:
                raise ConfigError(
                    f"Unknown modifier {name!r}. Use cmd, ctrl, alt or shift."
                )
            modifiers.add(name)
        self.modifiers = modifiers
        self.trigger = _resolve_trigger(parts[-1])
        self._pressed: set[str] = set()
        self._trigger_held = False

    def _modifier_of(self, key) -> str | None:
        for name, keys in MODIFIER_GROUPS.items():
            if key in keys:
                return name
        return None

    def on_press(self, key) -> bool:
        modifier = self._modifier_of(key)
        if modifier is not None:
            self._pressed.add(modifier)
            return False
        if key != self.trigger:
            return False
        if self.modifiers and self._pressed != self.modifiers:
            return False
        if self._trigger_held:
            return False
        self._trigger_held = True
        return True

    def on_release(self, key) -> None:
        modifier = self._modifier_of(key)
        if modifier is not None:
            self._pressed.discard(modifier)
        elif key == self.trigger:
            self._trigger_held = False
