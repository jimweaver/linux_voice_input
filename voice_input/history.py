import json
import time
from pathlib import Path

DEFAULT_HISTORY = Path.home() / ".local" / "share" / "linux-voice-input" / "history.jsonl"
TRIM_ABOVE = 1000
TRIM_TO = 500


def log_history(
    seconds: float,
    model: str,
    text: str = "",
    status: str = "ok",
    error: str = "",
    path: Path = DEFAULT_HISTORY,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.time(),
        "seconds": seconds,
        "model": model,
        "status": status,
        "text": text,
        "error": error,
    }
    line = json.dumps(entry)
    existing = path.read_text().splitlines() if path.exists() else []
    if len(existing) >= TRIM_ABOVE:
        path.write_text("\n".join(existing[-TRIM_TO:]) + "\n" + line + "\n")
    else:
        with path.open("a") as f:
            f.write(line + "\n")


def read_history(limit: int = 10, path: Path = DEFAULT_HISTORY) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in reversed(path.read_text().splitlines()):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
        if len(entries) >= limit:
            break
    return entries
