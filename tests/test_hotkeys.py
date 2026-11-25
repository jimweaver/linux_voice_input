import pytest
from pynput import keyboard

from voice_input.config import ConfigError
from voice_input.hotkeys import HotkeyMatcher


def press_and_release(matcher, key):
    pressed = matcher.on_press(key)
    matcher.on_release(key)
    return pressed


def test_single_key_fires_without_modifiers():
    m = HotkeyMatcher("f9")
    assert m.on_press(keyboard.Key.f9) is True


def test_single_key_still_fires_with_stray_modifiers():
    # backward compatibility: hotkey "f9" fires even while shift is held
    m = HotkeyMatcher("f9")
    m.on_press(keyboard.Key.shift)
    assert m.on_press(keyboard.Key.f9) is True


def test_cmd_s_fires_only_with_cmd_held():
    m = HotkeyMatcher("cmd+s")
    assert press_and_release(m, keyboard.KeyCode.from_char("s")) is False
    m.on_press(keyboard.Key.cmd)
    assert m.on_press(keyboard.KeyCode.from_char("s")) is True
    m.on_release(keyboard.KeyCode.from_char("s"))
    m.on_release(keyboard.Key.cmd)


def test_cmd_s_does_not_fire_with_extra_modifier():
    m = HotkeyMatcher("cmd+s")
    m.on_press(keyboard.Key.cmd)
    m.on_press(keyboard.Key.shift)
    assert press_and_release(m, keyboard.KeyCode.from_char("s")) is False


def test_right_cmd_counts_as_cmd():
    m = HotkeyMatcher("cmd+s")
    m.on_press(keyboard.Key.cmd_r)
    assert press_and_release(m, keyboard.KeyCode.from_char("s")) is True


def test_autorepeat_does_not_refire_while_held():
    m = HotkeyMatcher("cmd+s")
    m.on_press(keyboard.Key.cmd)
    assert m.on_press(keyboard.KeyCode.from_char("s")) is True
    assert m.on_press(keyboard.KeyCode.from_char("s")) is False  # autorepeat
    assert m.on_press(keyboard.KeyCode.from_char("s")) is False
    m.on_release(keyboard.KeyCode.from_char("s"))
    assert m.on_press(keyboard.KeyCode.from_char("s")) is True  # fresh press fires again


def test_single_key_autorepeat_does_not_refire():
    m = HotkeyMatcher("f9")
    assert m.on_press(keyboard.Key.f9) is True
    assert m.on_press(keyboard.Key.f9) is False
    m.on_release(keyboard.Key.f9)
    assert m.on_press(keyboard.Key.f9) is True


def test_fn_rejected_with_clear_error():
    with pytest.raises(ConfigError, match="fn"):
        HotkeyMatcher("fn+cmd+s")


def test_unknown_modifier_rejected():
    with pytest.raises(ConfigError):
        HotkeyMatcher("banana+s")


def test_unknown_trigger_key_rejected():
    with pytest.raises(ConfigError):
        HotkeyMatcher("cmd+banana!")


def test_multi_modifier_combo():
    m = HotkeyMatcher("ctrl+alt+s")
    m.on_press(keyboard.Key.ctrl)
    assert press_and_release(m, keyboard.KeyCode.from_char("s")) is False
    m.on_press(keyboard.Key.alt)
    assert press_and_release(m, keyboard.KeyCode.from_char("s")) is True


def test_modifier_release_stops_combo():
    m = HotkeyMatcher("cmd+s")
    m.on_press(keyboard.Key.cmd)
    m.on_release(keyboard.Key.cmd)
    assert press_and_release(m, keyboard.KeyCode.from_char("s")) is False
