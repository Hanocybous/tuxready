"""Anti-cheat status from the community-run AreWeAntiCheatYet project."""

from __future__ import annotations

from tuxready.sources.http import Http
from tuxready.text import compact, normalize

URL = "https://raw.githubusercontent.com/AreWeAntiCheatYet/AreWeAntiCheatYet/HEAD/games.json"
SITE = "https://areweanticheatyet.com"

# AreWeAntiCheatYet statuses that mean online play does not work on Linux.
BLOCKING = {"Denied", "Broken"}
WORKING = {"Supported", "Running"}


class AntiCheatDB:
    def __init__(self, games: list[dict]):
        self.by_steam: dict[int, dict] = {}
        self.by_name: dict[str, dict] = {}
        self.by_compact: dict[str, dict] = {}
        for game in games:
            steam_id = (game.get("storeIds") or {}).get("steam")
            if steam_id and str(steam_id).isdigit():
                self.by_steam[int(steam_id)] = game
            if game.get("name"):
                self.by_name.setdefault(normalize(game["name"]), game)
                self.by_compact.setdefault(compact(game["name"]), game)

    @classmethod
    def load(cls, http: Http) -> AntiCheatDB:
        data = http.get_json(URL)
        return cls(data if isinstance(data, list) else [])

    def lookup(self, name: str, steam_appid: int | None = None) -> dict | None:
        if steam_appid is not None and steam_appid in self.by_steam:
            return self.by_steam[steam_appid]
        wanted = normalize(name)
        found = self.by_name.get(wanted) or self.by_compact.get(compact(name))
        if found is not None or len(wanted) < 4:
            return found
        # Short Windows names like "NIKKE" for "Nikke: Goddess of Victory": accept a
        # name that starts with the same words, but only when exactly one game does.
        matches = [g for key, g in self.by_name.items() if key.startswith(wanted + " ")]
        return matches[0] if len(matches) == 1 else None

    def __len__(self) -> int:
        return len(self.by_name)


def page_url(game: dict) -> str:
    slug = game.get("slug")
    return f"{SITE}/game/{slug}" if slug else SITE
