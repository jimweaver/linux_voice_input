import json
import re
from pathlib import Path


def set_config_value(path: Path, key: str, value: str | None) -> None:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    lines = path.read_text().splitlines(keepends=True) if path.exists() else []
    # json.dumps produces a valid TOML basic string: quotes, backslashes and
    # control characters are escaped, so values can never inject TOML lines.
    rendered = None if value is None else f"{key} = {json.dumps(value)}\n"
    out = []
    replaced = False
    for line in lines:
        if pattern.match(line):
            if rendered is not None and not replaced:
                out.append(rendered)
                replaced = True
            # value is None → drop the line; duplicates are dropped too
        else:
            out.append(line)
    if rendered is not None and not replaced:
        out.append(rendered)
    path.write_text("".join(out))
