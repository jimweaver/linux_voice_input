import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "linux-voice-input" / "config.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    api_key: str
    model: str
    hotkey: str
    language: str | None
    device: str | None


def load_config(path: Path | None = None) -> Config:
    path = path if path is not None else DEFAULT_CONFIG_PATH
    data = {}
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)

    api_key = os.environ.get("OPENAI_API_KEY") or data.get("api_key")
    if not api_key:
        raise ConfigError(
            "No OpenAI API key found. Set the OPENAI_API_KEY environment variable "
            f"or add api_key to {path}."
        )

    return Config(
        api_key=api_key,
        model=data.get("model", "gpt-transcribe"),
        hotkey=data.get("hotkey", "f9"),
        language=data.get("language"),
        device=data.get("device", "pulse"),
    )
