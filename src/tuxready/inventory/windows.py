"""List programs installed on Windows (reads the same registry keys as 'Apps & features')."""

from __future__ import annotations

import re
import sys

from tuxready.models import Item

_UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)

# Runtimes, drivers, updates and other entries a person never chose to install.
_NOISE = re.compile(
    r"""^(
        microsoft\ visual\ c\+\+ | microsoft\ \.net | \.net\ | microsoft\ asp\.net
      | microsoft\ windows\ desktop\ runtime | windows\ software\ development\ kit | windows\ sdk
      | microsoft\ update\ health | update\ for | security\ update | hotfix
      | microsoft\ edge\ update | microsoft\ edge\ webview | microsoft\ gameinput
      | microsoft\ onedrive\ setup | windows\ pc\ health\ check | microsoft\ xna
      | directx | vulkan\ run\ ?time | openal | physx | nvidia\ physx
      | nvidia\ (graphics|hd\ audio|usbc|frameview|install|update|telemetry|virtual|ngx)
      | intel\(r\) | intel\ (management|rapid|serial|chipset|graphics|wireless|bluetooth)
      | realtek | amd\ (chipset|ryzen\ master\ sdk|install) | synaptics | elan\s
      | microsoft\ (odbc|ole\ db|sql\ server\ (?!management)\w*\ (native|clr|compact|t-sql|lang))
      | vs_ | windows\ driver | driver\ package
      | python\ \d.*\ (launcher|core|exe|tcl|pip|doc|test|dev|utility|add\ to\ path)
      | java\ (auto\ updater|update) | steamworks | epic\ online\ services
      | epic\ games\ launcher\ prerequisites
      | ea\ (app\ )?installer | battleye | easyanticheat | anti\ ?cheat\ ?expert
      | microsoft\ policy\ platform
      # Helpers and runtimes that come bundled with other programs:
      | mozilla\ maintenance\ service | google\ update | microsoft\ windows\ application\ compat
      | microsoft\ system\ clr\ types | microsoft\ sql\ server\ \d+\ management\ objects
      | microsoft\ sql\ server\ data-tier | powershell\ extensions\ for\ sql\ server
      | microsoft\ visual\ studio\ (installer|tools\ for\ applications|setup)
      | office\ 16\ click-to-run\ (extensibility|licensing|localization)
      | teams\ meeting\ add-in | microsoft\ teams\ meeting\ add-in
      | microsoft\ web\ platform\ installer
      | windows\ app\ runtime | microsoft\ windows\ app\ runtime | microsoft\ ui\ xaml
      | adobe\ (genuine|refresh\ manager|acrobat\ update) | ms\ teams\ machine | appcompat
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def is_user_facing(entry: dict) -> bool:
    """Decide whether an uninstall registry entry is a real, user-chosen program."""
    name = (entry.get("DisplayName") or "").strip()
    if not name:
        return False
    if entry.get("SystemComponent") == 1 or entry.get("ParentKeyName"):
        return False
    if (entry.get("ReleaseType") or "").lower() in {"update", "hotfix", "security update"}:
        return False
    key = entry.get("KeyName") or ""
    # Steam games are found more accurately through the Steam library itself.
    if key.startswith("Steam App "):
        return False
    return not _NOISE.match(name)


def clean_name(name: str) -> str:
    """Drop trailing versions and bitness: 'Notepad++ (64-bit x64)' -> 'Notepad++'."""
    name = re.sub(
        r"\s*\((x64|x86|64-bit|32-bit|64-bit x64|remove only|user|machine|all users)\)\s*$",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(r"\s+-\s+[a-z]{2}-[a-z]{2}$", "", name, flags=re.I)  # "Microsoft 365 - en-us"
    name = re.sub(r"\s+(version\s+)?v?\d+(\.\d+)+[\w.+-]*$", "", name, flags=re.I)
    return name.strip()


def read_registry() -> list[dict]:
    """Raw uninstall entries from the registry. Empty when not on Windows."""
    if sys.platform != "win32":
        return []
    import winreg

    entries: list[dict] = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path in _UNINSTALL_KEYS:
            try:
                root = winreg.OpenKey(hive, path)
            except OSError:
                continue
            with root:
                index = 0
                while True:
                    try:
                        sub = winreg.EnumKey(root, index)
                    except OSError:
                        break
                    index += 1
                    entry: dict = {"KeyName": sub}
                    try:
                        with winreg.OpenKey(root, sub) as handle:
                            for value in (
                                "DisplayName",
                                "Publisher",
                                "SystemComponent",
                                "ParentKeyName",
                                "ReleaseType",
                            ):
                                try:
                                    entry[value] = winreg.QueryValueEx(handle, value)[0]
                                except OSError:
                                    pass
                    except OSError:
                        continue
                    entries.append(entry)
    return entries


def scan() -> list[Item]:
    """User-facing installed programs, without duplicates. Empty when not on Windows."""
    seen: dict[str, Item] = {}
    for entry in read_registry():
        if not is_user_facing(entry):
            continue
        name = clean_name(entry["DisplayName"])
        key = name.lower()
        if key not in seen:
            seen[key] = Item(
                name=name, kind=None, source="windows", publisher=entry.get("Publisher")
            )
    return sorted(seen.values(), key=lambda i: i.name.lower())
