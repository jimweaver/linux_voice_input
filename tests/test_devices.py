import json
import subprocess

import pytest

from voice_input.devices import device_name_for_label, list_input_sources

PW_DUMP = [
    {"type": "PipeWire:Interface:Client", "info": {"props": {}}},
    {
        "type": "PipeWire:Interface:Node",
        "info": {
            "props": {
                "media.class": "Audio/Source",
                "node.name": "alsa_input.pci-0000_01_00.3.HiFi__Mic__source",
                "node.description": "Apple Audio Device Internal Microphone",
            }
        },
    },
    {
        "type": "PipeWire:Interface:Node",
        "info": {
            "props": {
                "media.class": "Audio/Source",
                "node.name": "ps4_bt_mic",
                "node.description": "PS4 Bluetooth Microphone (experimental)",
            }
        },
    },
    {
        "type": "PipeWire:Interface:Node",
        "info": {
            "props": {
                "media.class": "Audio/Source",
                "node.name": "bluez_input.00:02:5B:0A:2A:60",
                "node.description": "G7",
            }
        },
    },
    {
        "type": "PipeWire:Interface:Node",
        "info": {
            "props": {
                "media.class": "Audio/Source",
                "node.name": "alsa_output.pci.hdmi-stereo.monitor",
            }
        },
    },
    {
        "type": "PipeWire:Interface:Node",
        "info": {"props": {"media.class": "Audio/Sink", "node.name": "speakers"}},
    },
]


def fake_run(payload=PW_DUMP):
    def run(*a, **k):
        return subprocess.CompletedProcess(a, 0, stdout=json.dumps(payload).encode())

    return run


def test_list_input_sources_has_system_default_first_then_friendly_names():
    sources = list_input_sources(run=fake_run())
    assert sources == [
        ("Follow system default", "pulse"),
        (
            "Apple Audio Device Internal Microphone",
            "alsa_input.pci-0000_01_00.3.HiFi__Mic__source",
        ),
        ("PS4 Bluetooth Microphone (experimental)", "ps4_bt_mic"),
        ("G7", "bluez_input.00:02:5B:0A:2A:60"),
    ]


def test_list_input_sources_falls_back_to_node_name_without_description():
    payload = [
        {
            "type": "PipeWire:Interface:Node",
            "info": {"props": {"media.class": "Audio/Source", "node.name": "mystery_mic"}},
        }
    ]
    assert list_input_sources(run=fake_run(payload))[-1] == ("mystery_mic", "mystery_mic")


def test_list_input_sources_survives_pw_dump_failure():
    def boom(*a, **k):
        raise OSError("no pipewire")

    assert list_input_sources(run=boom) == [("Follow system default", "pulse")]


def test_device_name_for_label_maps_and_passes_through_unknown():
    sources = [("Follow system default", "pulse"), ("G7", "bluez_input.aa")]
    assert device_name_for_label(sources, "G7") == "bluez_input.aa"
    assert device_name_for_label(sources, "Follow system default") == "pulse"
    assert device_name_for_label(sources, "custom raw name") == "custom raw name"
