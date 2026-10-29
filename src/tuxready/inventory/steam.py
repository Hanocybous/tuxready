from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from tuxready.models import Item, Kind

_TOKEN = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])|([^\s{}"]+)')

# Steam installs these as "apps", but they are tools, not games.
_TOOL_APPIDS = {
    228980,  # Steamworks Common Redistributables
    1070560,  # Steam Linux Runtime 1.0 (scout)
    1391110,  # Steam Linux Runtime 2.0 (soldier)
    1628350,  # Steam Linux Runtime 3.0 (sniper)
    1493710,  # Proton Experimental
    2180100,  # Proton Hotfix
    2348590,  # Proton 8.0
    2805730,  # Proton 9.0
    250820,  # SteamVR
}
_TOOL_NAME = re.compile(r"^(Proton\b|Steam Linux Runtime|Steamworks|SteamVR)", re.IGNORECASE)


def parse_vdf(text: str) -> dict:
    """Parse Valve's KeyValues text format (used by .vdf and .acf files)."""
    root: dict = {}
    stack = [root]
    pending_key: str | None = None
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    for match in _TOKEN.finditer(text):
        quoted, brace, bare = match.groups()
        if brace == "{":
            new: dict = {}
            stack[-1][pending_key if pending_key is not None else ""] = new
            stack.append(new)
            pending_key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            pending_key = None
        else:
            token = quoted if quoted is not None else bare
            token = token.replace('\\"', '"').replace("\\\\", "\\")
            if pending_key is None:
                pending_key = token
            else:
                stack[-1][pending_key] = token
                pending_key = None
    return root


def default_steam_roots() -> list[Path]:
    home = Path.home()
    candidates: list[Path] = []
    if sys.platform == "win32":
        candidates += _windows_registry_steam_paths()
        for env in ("ProgramFiles(x86)", "ProgramFiles"):
            if os.environ.get(env):
                candidates.append(Path(os.environ[env]) / "Steam")
    else:
        candidates += [
            home / ".steam" / "steam",
            home / ".steam" / "root",
            home / ".local" / "share" / "Steam",
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
            home / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
        ]
    return candidates


def _windows_registry_steam_paths() -> list[Path]:
    try:
        import winreg
    except ImportError:
        return []
    found = []
    for hive, key, value in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    ):
        try:
            with winreg.OpenKey(hive, key) as handle:
                found.append(Path(winreg.QueryValueEx(handle, value)[0]))
        except OSError:
            continue
    return found


def library_dirs(steam_root: Path) -> list[Path]:
    steamapps = _steamapps(steam_root)
    if steamapps is None:
        return []
    dirs = [steamapps]
    vdf = steamapps / "libraryfolders.vdf"
    if vdf.is_file():
        data = parse_vdf(vdf.read_text(encoding="utf-8", errors="replace"))
        folders = data.get("libraryfolders") or data.get("LibraryFolders") or {}
        for entry in folders.values():
            path = entry.get("path") if isinstance(entry, dict) else entry
            if not path:
                continue
            candidate = _steamapps(Path(path))
            if candidate is not None:
                dirs.append(candidate)
    return dirs


def _steamapps(base: Path) -> Path | None:
    for name in ("steamapps", "SteamApps"):
        if (base / name).is_dir():
            return base / name
    return None


def read_manifest(path: Path) -> Item | None:
    data = parse_vdf(path.read_text(encoding="utf-8", errors="replace"))
    state = data.get("AppState") or data.get("appstate") or {}
    try:
        appid = int(state.get("appid", ""))
    except ValueError:
        return None
    name = (state.get("name") or "").strip()
    if not name or appid in _TOOL_APPIDS or _TOOL_NAME.match(name):
        return None
    return Item(name=name, kind=Kind.GAME, source="steam", steam_appid=appid)


def scan(extra_roots: Iterable[Path] = (), use_defaults: bool = True) -> list[Item]:
    roots = list(extra_roots) + (default_steam_roots() if use_defaults else [])
    seen_dirs: set[Path] = set()
    games: dict[int, Item] = {}
    for root in roots:
        for lib in library_dirs(Path(root)):
            real = lib.resolve()
            if real in seen_dirs:
                continue
            seen_dirs.add(real)
            for manifest in sorted(lib.glob("appmanifest_*.acf")):
                try:
                    item = read_manifest(manifest)
                except OSError:
                    continue
                if item is not None and item.steam_appid is not None:
                    games.setdefault(item.steam_appid, item)
    return sorted(games.values(), key=lambda i: i.name.lower())
