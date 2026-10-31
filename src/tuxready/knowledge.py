from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from tuxready.text import normalize, starts_with_words


@lru_cache(maxsize=1)
def entries() -> list[dict]:
    raw = resources.files("tuxready").joinpath("data/apps.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    for entry in data:
        entry["_aliases"] = [normalize(name) for name in entry["names"]]
    return data


def match(name: str) -> dict | None:
    # "Adobe Photoshop 2025" matches the alias "adobe photoshop"; longest alias wins
    wanted = normalize(name)
    best: tuple[int, dict] | None = None
    for entry in entries():
        for alias in entry["_aliases"]:
            if starts_with_words(wanted, alias) and (best is None or len(alias) > best[0]):
                best = (len(alias), entry)
    return best[1] if best else None


def match_appid(appid: int) -> dict | None:
    # Steam games match by ID only: name prefixes could hit unrelated games
    return next((e for e in entries() if appid in e.get("steam_appids", ())), None)
