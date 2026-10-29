"""Read a plain-text list of things to check, one per line.

# comments are ignored
Photoshop              -> tuxready works out whether it's an app or a game
game: Elden Ring       -> force "game"
app: Discord           -> force "app"
steam: 1245620         -> a Steam game by its ID
"""

from __future__ import annotations

from collections.abc import Iterable

from tuxready.models import Item, Kind


def parse_lines(lines: Iterable[str]) -> list[Item]:
    items: list[Item] = []
    seen: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind: Kind | None = None
        appid: int | None = None
        prefix, sep, rest = line.partition(":")
        prefix = prefix.strip().lower()
        if sep and prefix in {"game", "app", "steam"}:
            line = rest.strip()
            if prefix == "steam":
                kind = Kind.GAME
                try:
                    appid = int(line)
                except ValueError:
                    pass
            else:
                kind = Kind(prefix)
        if not line:
            continue
        key = f"{appid or line.lower()}"
        if key in seen:
            continue
        seen.add(key)
        name = f"Steam app {appid}" if appid else line
        items.append(Item(name=name, kind=kind, source="list", steam_appid=appid))
    return items


def read(path: str) -> list[Item]:
    if path == "-":
        import sys

        return parse_lines(sys.stdin)
    with open(path, encoding="utf-8-sig") as handle:  # Notepad may add a BOM
        return parse_lines(handle)
