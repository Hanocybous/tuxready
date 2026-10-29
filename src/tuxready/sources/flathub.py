from __future__ import annotations

from tuxready.sources.http import DAY, Http
from tuxready.text import normalize

SEARCH = "https://flathub.org/api/v2/search"
APPSTREAM = "https://flathub.org/api/v2/appstream/{app_id}"


def app_url(app_id: str) -> str:
    return f"https://flathub.org/apps/{app_id}"


def install_command(app_id: str) -> str:
    return f"flatpak install flathub {app_id}"


def find_exact(http: Http, name: str) -> dict | None:
    # exact names only, so "Discord" doesn't match a Discord client clone
    data = http.post_json(SEARCH, {"query": name}, ttl=7 * DAY)
    hits = (data or {}).get("hits", []) if isinstance(data, dict) else []
    wanted = normalize(name)
    for hit in hits:
        if normalize(hit.get("name", "")) == wanted and hit.get("app_id"):
            return hit
    return None


def exists(http: Http, app_id: str) -> bool:
    return http.get_json(APPSTREAM.format(app_id=app_id), ttl=7 * DAY) is not None
