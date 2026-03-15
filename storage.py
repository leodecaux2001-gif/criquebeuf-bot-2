from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_FILE = Path(__file__).with_name("state.json")


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"matches": {}}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"matches": {}}
        data.setdefault("matches", {})
        return data
    except Exception:
        return {"matches": {}}


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_FILE)
