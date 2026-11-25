#!/usr/bin/env bash
# Interactive setup: stores the OpenAI API key in the config file.
set -euo pipefail
umask 077

CONFIG_DIR="$HOME/.config/linux-voice-input"
CONFIG_FILE="$CONFIG_DIR/config.toml"

echo "linux-voice-input setup"
echo

if [[ -f "$CONFIG_FILE" ]] && grep -q '^api_key' "$CONFIG_FILE"; then
    read -rp "An API key is already stored in $CONFIG_FILE. Replace it? [y/N] " ans
    [[ "${ans:-}" =~ ^[Yy]$ ]] || { echo "Aborted; existing key kept."; exit 0; }
fi

read -rsp "Paste your OpenAI API key (input hidden): " api_key
echo

if [[ -z "$api_key" ]]; then
    echo "Error: empty key." >&2
    exit 1
fi

if command -v curl >/dev/null; then
    printf "Checking key with OpenAI... "
    if printf 'Authorization: Bearer %s\n' "$api_key" | curl -sf -m 15 https://api.openai.com/v1/models -H @- -o /dev/null; then
        echo "ok"
    else
        echo "rejected (bad key or network error)"
        read -rp "Save it anyway? [y/N] " ans
        [[ "${ans:-}" =~ ^[Yy]$ ]] || { echo "Aborted; nothing saved."; exit 1; }
    fi
fi

mkdir -p "$CONFIG_DIR"
if [[ -f "$CONFIG_FILE" ]] && grep -q '^api_key' "$CONFIG_FILE"; then
    printf 's|^api_key.*|api_key = "%s"|\n' "$api_key" | sed -i -f - "$CONFIG_FILE"
elif [[ -f "$CONFIG_FILE" ]]; then
    printf 'api_key = "%s"\n' "$api_key" >> "$CONFIG_FILE"
else
    printf 'api_key = "%s"\nmodel = "gpt-transcribe"\n' "$api_key" > "$CONFIG_FILE"
fi
chmod 600 "$CONFIG_FILE"

echo
echo "Saved to $CONFIG_FILE (readable only by you)."
echo "Start dictating with:  cd $(pwd) && .venv/bin/python -m voice_input"
