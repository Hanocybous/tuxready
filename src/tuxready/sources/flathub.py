"""Flathub: the main app store for Linux desktop apps."""

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
    """A Flathub app with the same name as `name`, or None.

    Only exact name matches count, so 'Discord' finds Discord and not a Discord look-alike.
    """
    data = http.post_json(SEARCH, {"query": name}, ttl=7 * DAY)
    hits = (data or {}).get("hits", []) if isinstance(data, dict) else []
    wanted = normalize(name)
    for hit in hits:
        if normalize(hit.get("name", "")) == wanted and hit.get("app_id"):
            return hit
    return None


def exists(http: Http, app_id: str) -> bool:
    return http.get_json(APPSTREAM.format(app_id=app_id), ttl=7 * DAY) is not None
