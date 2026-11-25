# linux-voice-input

Hotkey dictation for Linux (X11). Press F9, speak, then press F9 again to
insert the transcript into the focused window. Press Esc to cancel a recording.
The app pastes with Ctrl+V in GUI apps and Ctrl+Shift+V in recognized terminals.
It falls back to typing keystrokes when clipboard pasting fails.

Desktop notifications show each state: 🔴 錄緊 recording, ⏳ 轉寫緊
transcribing, ✅ 完成 done — and failures pop a critical notification.
The app trims leading and trailing silence before uploading audio to OpenAI
and retries transient API failures.

## Install

Use a Linux desktop in an X11 session, Python 3.11 or newer, and a microphone.
On Debian or Ubuntu, install the system dependencies and clone the repository:

```bash
sudo apt-get install -y python3-venv libportaudio2 xdotool xclip x11-utils libnotify-bin
git clone https://github.com/jimweaver/linux_voice_input.git ~/linux-voice-input
cd ~/linux-voice-input
python3 -m venv .venv
.venv/bin/pip install -e .
```

If pip needs to build `evdev` from source, install `build-essential` and
`python3-dev`, then retry the pip command.

## Configure

Create your own [OpenAI API key](https://platform.openai.com/api-keys) in an
API project with billing and access to the transcription model. OpenAI charges
API usage to that project. The app sends recorded audio to OpenAI for
transcription and stores recent dictation history locally.

Run the setup script to save the key in your local config file at
`~/.config/linux-voice-input/config.toml` with permissions `0600`.

```bash
./setup.sh
```

You can also set `OPENAI_API_KEY` in the environment of the process that runs
the app. The environment value takes precedence over the config file.
Use the config file for the systemd service unless you have configured its
environment separately. Keep API keys out of Git.

Config options in `~/.config/linux-voice-input/config.toml`:

```toml
api_key = "YOUR_OPENAI_API_KEY"
model = "gpt-transcribe"           # An OpenAI file transcription model available to your API project
hotkey = "f9"                      # a pynput Key name, a single character, or a combo like "cmd+s"
language = "en"                    # optional; omit for auto-detection
device = "pulse"                   # audio input; "pulse" follows the system default source
```

Hotkey combos use `cmd`/`ctrl`/`alt`/`shift` joined with `+`, e.g.
`"cmd+s"`, `"ctrl+alt+v"`. With modifiers, the combo must match exactly
(cmd+s does not fire on cmd+shift+s). The Mac `fn` key is handled by the
keyboard firmware and is invisible to Linux, so it cannot be used.
XFCE does not bind Super+S, so `cmd+s` conflicts with nothing on the
default desktop (note: `<Alt><Super>s` starts the orca screen reader).

On Apple hardware running Asahi Linux the physical **⌘ Command** key is
mapped to **Control** by the keymap (so ⌘S arrives as Ctrl+S), and the
**fn** key never reaches X11. Because Ctrl+S means Save in most apps,
use `ctrl+alt+s` — physical ⌘⌥S — which is bound to nothing in XFCE.

## Run

From the project directory, run the app in your X11 terminal:

```bash
.venv/bin/python -m voice_input
```

To run it in the background on a desktop that uses systemd user services, keep
the checkout at `~/linux-voice-input` and run the following in your X11 terminal:

```bash
install -Dm644 packaging/linux-voice-input.service ~/.config/systemd/user/linux-voice-input.service
systemctl --user import-environment DISPLAY
if [ -n "${XAUTHORITY:-}" ]; then systemctl --user import-environment XAUTHORITY; fi
systemctl --user daemon-reload
systemctl --user enable --now linux-voice-input
systemctl --user status linux-voice-input
```

The service can start at login when your desktop passes the X11 environment
to the systemd user manager. Stop the terminal instance before enabling the
service so only one process handles the hotkey.

## Dashboard

The optional dashboard needs GTK 3 and PyGObject. On Debian or Ubuntu, install
the system bindings and create a separate environment using the distribution's
Python so it can import them:

```bash
sudo apt-get install -y python3-gi gir1.2-gtk-3.0
cd ~/linux-voice-input
/usr/bin/python3 -m venv --system-site-packages .venv-dashboard
.venv-dashboard/bin/pip install -e .
.venv-dashboard/bin/python -m voice_input.dashboard
```

- **Dictation service** — status and an on/off switch (start/stop the systemd service).
- **Usage (estimated cost)** — minutes dictated and estimated cost for today,
  the last 7 days, and all time. Costs are local estimates (recorded seconds ×
  OpenAI's published rate), not your OpenAI bill. Data lives in
  `~/.local/share/linux-voice-input/usage.jsonl`.
- **Recent dictations** — the last 10 attempts with duration, status and a
  text snippet (failures show the error). Data lives in
  `~/.local/share/linux-voice-input/history.jsonl`.
- **Settings** — hotkey, language, model, audio device and API key;
  *Save & Restart Service* writes the config (permissions 600) and restarts
  the daemon. Language "Auto (detect)" lets the API detect. The API key field
  is write-only: leave it blank to keep the configured key.

## Develop

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

## License

The [MIT License](LICENSE) permits commercial use, modification, and
redistribution, provided you include the copyright and license notice in
copies or substantial portions of the software.
