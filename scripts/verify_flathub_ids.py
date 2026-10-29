"""Check that every Flathub ID in src/tuxready/data/apps.json exists. Run before a release:

python scripts/verify_flathub_ids.py
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tuxready.sources import flathub
from tuxready.sources.http import Http

DATA = Path(__file__).resolve().parent.parent / "src" / "tuxready" / "data" / "apps.json"


def main() -> int:
    ids = set()
    for entry in json.loads(DATA.read_text(encoding="utf-8")):
        if entry.get("flatpak"):
            ids.add(entry["flatpak"])
        ids.update(alt["flatpak"] for alt in entry.get("alternatives", []) if alt.get("flatpak"))
    http = Http(refresh=True)
    with ThreadPoolExecutor(8) as pool:
        ordered = sorted(ids)
        found = dict(
            zip(ordered, pool.map(lambda i: flathub.exists(http, i), ordered), strict=True)
        )
    missing = [app_id for app_id, ok in found.items() if not ok]
    print(f"Checked {len(ids)} Flathub IDs, {len(missing)} missing.")
    for app_id in missing:
        print(f"  missing: {app_id}")
    if http.failures:
        print(f"  ({http.failures} requests failed, re-run to be sure)")
    return 1 if missing or http.failures else 0


if __name__ == "__main__":
    sys.exit(main())
