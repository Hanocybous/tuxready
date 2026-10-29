"""Steam store lookups and ProtonDB ratings."""

from __future__ import annotations

import urllib.parse

from tuxready.sources.http import DAY, Http
from tuxready.text import normalize

PROTONDB_SUMMARY = "https://www.protondb.com/api/v1/reports/summaries/{appid}.json"
STORE_DETAILS = (
    "https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic,platforms"
)
STORE_SEARCH = "https://store.steampowered.com/api/storesearch/?term={term}&cc=us&l=en"


def protondb(http: Http, appid: int) -> dict | None:
    """ProtonDB summary, e.g. {'tier': 'gold', 'total': 2107, ...}."""
    data = http.get_json(PROTONDB_SUMMARY.format(appid=appid))
    return data if isinstance(data, dict) else None


def protondb_url(appid: int) -> str:
    return f"https://www.protondb.com/app/{appid}"


def details(http: Http, appid: int) -> dict | None:
    """Store details: name, type and platforms ({'windows': True, 'linux': False, ...})."""
    data = http.get_json(STORE_DETAILS.format(appid=appid), ttl=7 * DAY)
    entry = (data or {}).get(str(appid)) if isinstance(data, dict) else None
    if not entry or not entry.get("success"):
        return None
    return entry.get("data")


def search(http: Http, name: str) -> tuple[int, str] | None:
    """Find a Steam game whose name matches `name` exactly (ignoring case and symbols)."""
    url = STORE_SEARCH.format(term=urllib.parse.quote(name))
    data = http.get_json(url, ttl=7 * DAY)
    wanted = normalize(name)
    for hit in (data or {}).get("items", []) if isinstance(data, dict) else []:
        if hit.get("type") == "app" and normalize(hit.get("name", "")) == wanted:
            return int(hit["id"]), hit["name"]
    return None
