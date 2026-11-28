import os
import re
import subprocess
import time
from pathlib import Path

from voice_input.config import DEFAULT_CONFIG_PATH, load_config
from voice_input.config_update import set_config_value
from voice_input.devices import device_name_for_label, list_input_sources
from voice_input.history import read_history
from voice_input.usage import summarize

SERVICE_NAME = "linux-voice-input.service"
AUTO_LANGUAGE = "Auto (detect)"
HOTKEY_PRESETS = ["f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12", "scroll_lock", "pause", "cmd+s", "ctrl+alt+s"]
LANGUAGE_PRESETS = [AUTO_LANGUAGE, "en", "zh", "yue"]
MODEL_PRESETS = ["gpt-transcribe", "gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1"]


class ServiceError(Exception):
    pass


def clean_hotkey(text: str) -> str | None:
    hotkey = text.strip().lower()
    if not hotkey or any(c in hotkey for c in ('"', "\\", "\n")) or " " in hotkey:
        return None
    return hotkey


def clean_model(text: str) -> str | None:
    model = text.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", model):
        return None
    return model


def clean_device(text: str) -> str | None:
    device = text.strip()
    if not device:
        return "pulse"
    if any(c in device for c in ('"', "\\", "\n")):
        return None
    return device


def normalize_language(text: str) -> str | None:
    language = text.strip().lower()
    if language in ("", "auto", "auto (detect)"):
        return None
    if not re.fullmatch(r"[a-z]{2,3}(-[a-z]{2})?", language):
        raise ValueError(f"invalid language code: {language!r}")
    return language


def _systemctl_env() -> dict:
    env = dict(os.environ)
    uid = os.getuid()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
    return env


def service_active(run=subprocess.run) -> bool:
    try:
        result = run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            capture_output=True,
            env=_systemctl_env(),
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.decode().strip() == "active"


def set_service(on: bool, run=subprocess.run) -> None:
    verb = "start" if on else "stop"
    try:
        result = run(
            ["systemctl", "--user", verb, SERVICE_NAME],
            capture_output=True,
            env=_systemctl_env(),
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        raise ServiceError(f"systemctl {verb} timed out")
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise ServiceError(detail or f"systemctl {verb} exited {result.returncode}")


def apply_settings(
    config_path: Path,
    hotkey: str,
    language: str | None,
    model: str | None = None,
    device: str | None = None,
    api_key: str | None = None,
    run=subprocess.run,
) -> None:
    config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    set_config_value(config_path, "hotkey", hotkey)
    set_config_value(config_path, "language", language)
    if model is not None:
        set_config_value(config_path, "model", model)
    if device is not None:
        set_config_value(config_path, "device", device)
    if api_key:
        set_config_value(config_path, "api_key", api_key)
    os.chmod(config_path, 0o600)
    try:
        result = run(
            ["systemctl", "--user", "restart", SERVICE_NAME],
            capture_output=True,
            env=_systemctl_env(),
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        raise ServiceError("systemctl restart timed out")
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise ServiceError(detail or "systemctl restart failed")


def _format_usage() -> str:
    s = summarize()
    rows = []
    for label, key in (("Today", "today"), ("Last 7 days", "week"), ("All time", "total")):
        minutes = s[key]["seconds"] / 60.0
        rows.append(f"{label:<12}{minutes:>6.1f} min    ${s[key]['cost']:.4f}")
    return "\n".join(rows)


def _history_row(e: dict) -> tuple[str, str] | None:
    try:
        stamp = time.strftime("%H:%M", time.localtime(float(e["ts"])))
        seconds = float(e["seconds"])
    except (ValueError, TypeError, KeyError):
        return None
    if e.get("status") == "ok":
        text = str(e.get("text", ""))
        flat = text.replace("\n", " ")
        snippet = flat[:40] + ("…" if len(flat) > 40 else "")
        return f"{stamp}  {seconds:>4.1f}s  ✅  {snippet}", text
    return f"{stamp}  {seconds:>4.1f}s  ❌  {e.get('error', '')}", ""


def _format_history(entries: list[dict]) -> str:
    if not entries:
        return "No dictations yet."
    rows = [label for e in entries if (row := _history_row(e)) is not None
            for label in [row[0]]]
    return "\n".join(rows) or "No dictations yet."


def main() -> None:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk, Pango

    try:
        config = load_config()
        current_hotkey = config.hotkey
        current_language = config.language
        current_model = config.model
        current_device = config.device
        current_api_key = config.api_key
    except Exception:
        current_hotkey, current_language = "f9", None
        current_model, current_device = "gpt-transcribe", "pulse"
        current_api_key = None

    window = Gtk.Window(title="Linux Voice Input")
    window.set_border_width(12)
    window.set_default_size(420, -1)
    window.connect("destroy", Gtk.main_quit)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    window.add(box)

    # --- service control ---
    service_frame = Gtk.Frame(label="Dictation service")
    service_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    service_box.set_border_width(8)
    service_frame.add(service_box)
    status_label = Gtk.Label(xalign=0)
    status_label.set_hexpand(True)
    switch = Gtk.Switch()
    service_box.pack_start(status_label, True, True, 0)
    service_box.pack_start(switch, False, False, 0)
    box.pack_start(service_frame, False, False, 0)

    error_label = Gtk.Label(xalign=0)
    error_label.set_line_wrap(True)
    box.pack_start(error_label, False, False, 0)

    def refresh_status(*_args):
        active = service_active()
        status_label.set_text("Running" if active else "Stopped (or not installed)")
        switch.handler_block(switch_handler)
        switch.set_active(active)
        switch.handler_unblock(switch_handler)
        return True

    def on_switch(widget, state):
        try:
            set_service(state)
            error_label.set_text("")
        except ServiceError as exc:
            error_label.set_text(f"Could not {'start' if state else 'stop'} service: {exc}")
            return True  # block the visual state change; refresh_status restores it
        GLib.idle_add(refresh_status)

    switch_handler = switch.connect("state-set", on_switch)

    # --- usage ---
    usage_frame = Gtk.Frame(label="Usage (estimated cost)")
    usage_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    usage_box.set_border_width(8)
    usage_frame.add(usage_box)
    usage_label = Gtk.Label(xalign=0)
    usage_label.set_selectable(True)
    usage_box.pack_start(usage_label, False, False, 0)
    note = Gtk.Label(xalign=0)
    note.set_markup(
        "<small>Costs are local estimates: recorded seconds × OpenAI's published rate.</small>"
    )
    usage_box.pack_start(note, False, False, 0)
    box.pack_start(usage_frame, False, False, 0)

    def refresh_usage(*_args):
        usage_label.set_text(_format_usage())
        return True

    # --- recent dictations ---
    history_frame = Gtk.Frame(label="Recent dictations")
    history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    history_box.set_border_width(8)
    history_frame.add(history_box)
    history_scroll = Gtk.ScrolledWindow()
    history_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    history_scroll.set_min_content_height(120)
    history_scroll.set_max_content_height(240)
    history_list = Gtk.ListBox()
    history_list.set_selection_mode(Gtk.SelectionMode.NONE)
    history_scroll.add(history_list)
    history_box.pack_start(history_scroll, True, True, 0)
    box.pack_start(history_frame, False, False, 0)

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

    def _restore_copy_label(button):
        button.set_label("Copy")
        return False

    def on_copy_clicked(button, text):
        clipboard.set_text(text, -1)
        clipboard.store()
        button.set_label("✓")
        GLib.timeout_add(1000, _restore_copy_label, button)

    def show_full_text(_listbox, row):
        text = getattr(row, "full_text", "")
        if not text:
            return
        dialog = Gtk.Dialog(title="Dictation", transient_for=window, modal=True)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.set_default_size(420, 260)
        scroll = Gtk.ScrolledWindow()
        scroll.set_border_width(8)
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD)
        view.get_buffer().set_text(text)
        scroll.add(view)
        dialog.get_content_area().pack_start(scroll, True, True, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    history_list.connect("row-activated", show_full_text)

    def refresh_history(*_args):
        for child in history_list.get_children():
            history_list.remove(child)
        rows = [row for e in read_history() if (row := _history_row(e)) is not None]
        if not rows:
            history_list.add(Gtk.Label(label="No dictations yet.", xalign=0))
        for label_text, full_text in rows:
            row = Gtk.ListBoxRow()
            row.full_text = full_text
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row_box.set_border_width(2)
            label = Gtk.Label(label=label_text, xalign=0)
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            copy_button = Gtk.Button(label="Copy")
            copy_button.set_sensitive(bool(full_text))
            copy_button.connect("clicked", on_copy_clicked, full_text)
            row_box.pack_start(label, True, True, 0)
            row_box.pack_start(copy_button, False, False, 0)
            row.add(row_box)
            history_list.add(row)
        history_list.show_all()
        return True

    # --- settings ---
    settings_frame = Gtk.Frame(label="Settings")
    grid = Gtk.Grid(column_spacing=12, row_spacing=8)
    grid.set_border_width(8)
    settings_frame.add(grid)

    grid.attach(Gtk.Label(label="Hotkey", xalign=0), 0, 0, 1, 1)
    hotkey_combo = Gtk.ComboBoxText.new_with_entry()
    for preset in HOTKEY_PRESETS:
        hotkey_combo.append_text(preset)
    hotkey_combo.get_child().set_text(current_hotkey)
    grid.attach(hotkey_combo, 1, 0, 1, 1)

    grid.attach(Gtk.Label(label="Language", xalign=0), 0, 1, 1, 1)
    language_combo = Gtk.ComboBoxText.new_with_entry()
    for preset in LANGUAGE_PRESETS:
        language_combo.append_text(preset)
    language_combo.get_child().set_text(current_language or AUTO_LANGUAGE)
    grid.attach(language_combo, 1, 1, 1, 1)

    grid.attach(Gtk.Label(label="Model", xalign=0), 0, 2, 1, 1)
    model_combo = Gtk.ComboBoxText.new_with_entry()
    for preset in MODEL_PRESETS:
        model_combo.append_text(preset)
    model_combo.get_child().set_text(current_model)
    grid.attach(model_combo, 1, 2, 1, 1)

    grid.attach(Gtk.Label(label="Audio device", xalign=0), 0, 3, 1, 1)
    device_combo = Gtk.ComboBoxText.new_with_entry()
    input_sources = list_input_sources()
    label_by_name = {name: label for label, name in input_sources}
    for label, _name in input_sources:
        device_combo.append_text(label)
    current_name = current_device or "pulse"
    device_combo.get_child().set_text(label_by_name.get(current_name, current_name))
    grid.attach(device_combo, 1, 3, 1, 1)

    grid.attach(Gtk.Label(label="API key", xalign=0), 0, 4, 1, 1)
    api_key_entry = Gtk.Entry()
    api_key_entry.set_visibility(False)
    if current_api_key:
        api_key_entry.set_placeholder_text(f"configured (…{current_api_key[-4:]}) — leave blank to keep")
    else:
        api_key_entry.set_placeholder_text("sk-…")
    grid.attach(api_key_entry, 1, 4, 1, 1)

    save_button = Gtk.Button(label="Save & Restart Service")
    grid.attach(save_button, 0, 5, 2, 1)
    feedback = Gtk.Label(xalign=0)
    grid.attach(feedback, 0, 6, 2, 1)
    box.pack_start(settings_frame, False, False, 0)

    def on_save(_button):
        hotkey = clean_hotkey(hotkey_combo.get_child().get_text())
        if hotkey is None:
            feedback.set_text(
                "Invalid hotkey: use a single key name (e.g. f9, scroll_lock) "
                "with no spaces, quotes or backslashes."
            )
            return
        try:
            language = normalize_language(language_combo.get_child().get_text())
        except ValueError:
            feedback.set_text(
                "Invalid language code: use a 2–3 letter code like en, zh, yue, "
                "or Auto (detect)."
            )
            return
        model = clean_model(model_combo.get_child().get_text())
        if model is None:
            feedback.set_text("Invalid model name: use one of the presets.")
            return
        device_text = device_combo.get_child().get_text()
        device = clean_device(device_name_for_label(input_sources, device_text))
        if device is None:
            feedback.set_text("Invalid device name: no quotes or backslashes.")
            return
        try:
            apply_settings(
                DEFAULT_CONFIG_PATH, hotkey, language, model=model, device=device,
                api_key=api_key_entry.get_text().strip() or None,
            )
            feedback.set_text("Saved. Service restarting…")
        except ServiceError as exc:
            feedback.set_text(f"Saved to config, but restart failed: {exc}")
        except OSError as exc:
            feedback.set_text(f"Could not save: {exc}")
            return
        GLib.idle_add(refresh_status)

        def check_restart():
            if service_active():
                feedback.set_text("Saved. Service restarted.")
            else:
                feedback.set_text(
                    "Saved, but the service failed to start — "
                    "the hotkey may be invalid. Fix it and save again."
                )
            GLib.idle_add(refresh_status)
            return False

        GLib.timeout_add_seconds(2, check_restart)

    save_button.connect("clicked", on_save)

    refresh_status()
    refresh_usage()
    refresh_history()
    GLib.timeout_add_seconds(3, refresh_status)
    GLib.timeout_add_seconds(3, refresh_usage)
    GLib.timeout_add_seconds(3, refresh_history)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
