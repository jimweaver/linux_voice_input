import json
import subprocess

SYSTEM_DEFAULT = ("Follow system default", "pulse")


def list_input_sources(run=subprocess.run) -> list[tuple[str, str]]:
    """(label, device name) pairs for the dashboard dropdown.

    Labels come from PipeWire node descriptions (e.g. "Apple Audio Device
    Internal Microphone", "G7"); the device name is the PipeWire node name,
    which sounddevice accepts via the PulseAudio host API.
    """
    sources = [SYSTEM_DEFAULT]
    try:
        result = run(["pw-dump"], capture_output=True, timeout=5)
        nodes = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return sources
    for node in nodes:
        if node.get("type") != "PipeWire:Interface:Node":
            continue
        props = node.get("info", {}).get("props", {})
        if props.get("media.class") != "Audio/Source":
            continue
        name = props.get("node.name")
        if not name or name.endswith(".monitor"):
            continue
        label = props.get("node.description") or props.get("node.nick") or name
        sources.append((label, name))
    return sources


def device_name_for_label(sources: list[tuple[str, str]], label: str) -> str:
    for source_label, name in sources:
        if source_label == label:
            return name
    return label
