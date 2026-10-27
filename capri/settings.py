"""
settings.py — small JSON file with user choices (survives restarts).
Stored in settings.json in the project root (not in git).
"""

import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "settings.json"

DEFAULTS = {
    "wake_word": True,    # listen for «Капри»
}


def load() -> dict:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return {**DEFAULTS, **data}


def save(key: str, value) -> None:
    data = load()
    data[key] = value
    try:
        PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[Settings] Could not save: {e}")
