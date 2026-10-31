from __future__ import annotations

import dataclasses
import threading
import urllib.parse
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

from tuxready import knowledge
from tuxready.models import Item, Kind, Link, Result, Verdict
from tuxready.sources import anticheat, flathub, steam
from tuxready.sources.http import Http

STEAM_PLAY_HOWTO = (
    "In Steam: Settings → Compatibility → turn on 'Enable Steam Play for all other titles'. "
    "Then install and play as usual."
)

_PROTON_TIERS = {
    "platinum": (
        Verdict.WORKS,
        "Works perfectly through Proton (ProtonDB: Platinum).",
    ),
    "gold": (
        Verdict.WORKS,
        "Works through Proton with minor issues at most (ProtonDB: Gold).",
    ),
    "silver": (
        Verdict.TWEAKS,
        "Runs through Proton, with some issues (ProtonDB: Silver).",
    ),
    "bronze": (
        Verdict.TWEAKS,
        "Runs through Proton, but with noticeable problems (ProtonDB: Bronze).",
    ),
    "borked": (
        Verdict.BLOCKED,
        "Doesn't run on Linux right now (ProtonDB: Borked).",
    ),
}

_TIER_ORDER = ["borked", "bronze", "silver", "gold", "platinum"]

Progress = Callable[[int, int, Result], None]


class Checker:
    def __init__(self, http: Http):
        self.http = http
        self._anticheat: anticheat.AntiCheatDB | None = None
        self._lock = threading.Lock()

    @property
    def anticheat(self) -> anticheat.AntiCheatDB:
        with self._lock:
            if self._anticheat is None:
                self._anticheat = anticheat.AntiCheatDB.load(self.http)
            return self._anticheat

    def check_all(
        self, items: Iterable[Item], progress: Progress | None = None, workers: int = 8
    ) -> list[Result]:
        items = list(items)
        results: list[Result | None] = [None] * len(items)
        done = 0
        done_lock = threading.Lock()

        def run(index: int) -> None:
            nonlocal done
            result = self.check_safely(items[index])
            results[index] = result
            with done_lock:
                done += 1
                if progress:
                    progress(done, len(items), result)

        _ = self.anticheat  # load once up front instead of racing in every thread
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(run, range(len(items))))
        return [r for r in results if r is not None]

    def check_safely(self, item: Item) -> Result:
        try:
            return self.check(item)
        except Exception as error:  # one bad item must not stop the whole scan
            return Result(item, Verdict.UNKNOWN, f"Couldn't check this one ({error}).")

    def check(self, item: Item) -> Result:
        # knowledge base first, it has the alternatives
        if item.steam_appid is not None:
            entry = knowledge.match_appid(item.steam_appid)
            if entry is not None:
                return from_knowledge(item, entry)
        else:
            entry = knowledge.match(item.name)
            if entry is not None and (
                item.kind is None or entry.get("kind", item.kind.value) == item.kind.value
            ):
                return from_knowledge(item, entry)

        if item.kind is Kind.APP:
            return self.check_app(item) or unknown(item)

        ac = self.anticheat.lookup(item.name, item.steam_appid)
        if item.steam_appid is not None or ac is not None or item.kind is Kind.GAME:
            return self.check_game(item, ac)

        # unknown type: try Flathub, then Steam
        app = self.check_app(item)
        if app is not None:
            return app
        found = steam.search(self.http, item.name)
        if found is not None:
            game = dataclasses.replace(item, kind=Kind.GAME, steam_appid=found[0])
            return self.check_game(game, None)
        return unknown(item)

    def check_app(self, item: Item) -> Result | None:
        hit = flathub.find_exact(self.http, item.name)
        if hit is None:
            return None
        app_id = hit["app_id"]
        item = dataclasses.replace(item, kind=Kind.APP)
        return Result(
            item,
            Verdict.NATIVE,
            f"Available for Linux on Flathub ({hit.get('summary') or app_id}).",
            links=[Link("Flathub", flathub.app_url(app_id))],
            how_to=flathub.install_command(app_id),
            flatpak=app_id,
        )

    def check_game(self, item: Item, ac: dict | None) -> Result:
        item = dataclasses.replace(item, kind=Kind.GAME)
        appid = item.steam_appid
        ac_steam_id = str((ac or {}).get("storeIds", {}).get("steam") or "")
        if appid is None and ac_steam_id.isdigit():
            appid = int(ac_steam_id)
            item = dataclasses.replace(item, steam_appid=appid)
        if appid is None:
            found = steam.search(self.http, item.name)
            if found is not None:
                appid = found[0]
                item = dataclasses.replace(item, steam_appid=appid)

        links: list[Link] = []
        info = None
        if appid is not None:
            info = steam.details(self.http, appid)
            if info and item.name.startswith("Steam app "):
                item = dataclasses.replace(item, name=info.get("name") or item.name)
            links += [
                Link("ProtonDB", steam.protondb_url(appid)),
                Link("Steam store", f"https://store.steampowered.com/app/{appid}"),
            ]
        if ac is None:
            ac = self.anticheat.lookup(item.name, appid)
        if ac is not None:
            links.append(Link("AreWeAntiCheatYet", anticheat.page_url(ac)))

        # blocked anti-cheat wins even if ProtonDB says gold
        if ac is not None and ac.get("status") in anticheat.BLOCKING:
            systems = ", ".join(ac.get("anticheats") or []) or "its anti-cheat"
            if ac.get("status") == "Denied":
                why = f"The developer has chosen not to allow Linux in {systems}."
            else:
                why = f"Online play is blocked by {systems} on Linux."
            return Result(
                item,
                Verdict.BLOCKED,
                why + " Offline or single-player modes may still work.",
                links=links,
            )

        ac_note = ""
        if ac is not None and ac.get("status") in anticheat.WORKING:
            ac_note = f" Its anti-cheat ({', '.join(ac.get('anticheats') or [])}) supports Linux."

        if info and (info.get("platforms") or {}).get("linux"):
            return Result(
                item, Verdict.NATIVE, "Has a native Linux version on Steam." + ac_note, links=links
            )

        if appid is not None:
            summary = steam.protondb(self.http, appid)
            tier = (summary or {}).get("tier")
            if tier in _PROTON_TIERS:
                trending = (summary or {}).get("trendingTier")
                if trending not in _PROTON_TIERS:
                    trending = tier
                # Proton keeps improving, so better recent reports describe today
                shown = max(tier, trending, key=_TIER_ORDER.index)
                verdict, text = _PROTON_TIERS[shown]
                text = text.replace("(ProtonDB:", "(Steam version, ProtonDB:")
                if shown != tier:
                    text += f" That's from recent reports; overall it's {tier.capitalize()}."
                elif trending != tier:
                    text += f" Recent reports are {trending.capitalize()}."
                reports = (summary or {}).get("total") or 0
                if reports < 5:
                    text += f" Based on only {reports} report(s)."
                return Result(
                    item,
                    verdict,
                    text + ac_note,
                    links=links,
                    how_to=STEAM_PLAY_HOWTO if verdict is not Verdict.BLOCKED else None,
                )

        if ac is not None and ac.get("status") in anticheat.WORKING:
            return Result(
                item,
                Verdict.WORKS,
                ac_note.strip(),
                links=links,
                how_to="Play it through Steam, or Heroic/Lutris for other stores.",
            )

        if appid is None:
            query = urllib.parse.quote(item.name)
            links.append(Link("Search Lutris", f"https://lutris.net/games?q={query}"))
            return Result(
                item,
                Verdict.UNKNOWN,
                "Not a Steam game we could find. Heroic or Lutris may run it.",
                links=links,
            )
        return Result(
            item,
            Verdict.UNKNOWN,
            "No Linux reports yet on ProtonDB. Try it with Proton.",
            links=links,
            how_to=STEAM_PLAY_HOWTO,
        )


def from_knowledge(item: Item, entry: dict) -> Result:
    kind = Kind(entry["kind"]) if entry.get("kind") else (item.kind or Kind.APP)
    item = dataclasses.replace(item, kind=kind)
    links: list[Link] = []
    how_to = None
    if entry.get("flatpak"):
        links.append(Link("Flathub", flathub.app_url(entry["flatpak"])))
        how_to = flathub.install_command(entry["flatpak"])
    alternatives = []
    alt_flatpaks: dict[str, str] = {}
    for alt in entry.get("alternatives", []):
        alternatives.append(alt["name"])
        if alt.get("flatpak"):
            alt_flatpaks[alt["name"]] = alt["flatpak"]
            links.append(Link(alt["name"], flathub.app_url(alt["flatpak"])))
        elif alt.get("url"):
            links.append(Link(alt["name"], alt["url"]))
    return Result(
        item,
        Verdict(entry["verdict"]),
        entry["summary"],
        alternatives,
        links,
        how_to,
        flatpak=entry.get("flatpak"),
        alt_flatpaks=alt_flatpaks,
        install=entry.get("install"),
    )


def unknown(item: Item) -> Result:
    query = urllib.parse.quote(item.name)
    return Result(
        dataclasses.replace(item, kind=item.kind or Kind.APP),
        Verdict.UNKNOWN,
        "Not in our database and not on Flathub. Check AlternativeTo for Linux options.",
        links=[
            Link(
                "AlternativeTo",
                f"https://alternativeto.net/browse/search/?q={query}&platform=linux",
            ),
            Link("Search Flathub", f"https://flathub.org/apps/search?q={query}"),
        ],
    )
