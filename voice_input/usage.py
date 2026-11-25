import json
import time
from datetime import date, timedelta
from pathlib import Path

DEFAULT_LOG = Path.home() / ".local" / "share" / "linux-voice-input" / "usage.jsonl"

# USD per minute of audio, per OpenAI's published pricing.
RATES = {
    "gpt-transcribe": 0.0045,
    "whisper-1": 0.006,
    "gpt-4o-transcribe": 0.006,
    "gpt-4o-mini-transcribe": 0.003,
}
DEFAULT_RATE = 0.0045  # my call: unknown future models billed at the flagship rate


def cost_of(model: str, seconds: float) -> float:
    return seconds / 60.0 * RATES.get(model, DEFAULT_RATE)


def log_usage(seconds: float, model: str, path: Path = DEFAULT_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"ts": time.time(), "seconds": seconds, "model": model}) + "\n")


def summarize(path: Path = DEFAULT_LOG, today: date | None = None) -> dict:
    today = today or date.today()
    week_start = today - timedelta(days=6)
    buckets = {
        "today": {"seconds": 0.0, "cost": 0.0},
        "week": {"seconds": 0.0, "cost": 0.0},
        "total": {"seconds": 0.0, "cost": 0.0},
    }
    if not path.exists():
        return buckets
    for line in path.read_text().splitlines():
        try:
            entry = json.loads(line)
            seconds = float(entry["seconds"])
            ts = float(entry["ts"])
            model = str(entry.get("model", ""))
            day = date.fromtimestamp(ts)
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
        cost = cost_of(model, seconds)
        buckets["total"]["seconds"] += seconds
        buckets["total"]["cost"] += cost
        if day >= week_start:
            buckets["week"]["seconds"] += seconds
            buckets["week"]["cost"] += cost
        if day == today:
            buckets["today"]["seconds"] += seconds
            buckets["today"]["cost"] += cost
    return buckets
