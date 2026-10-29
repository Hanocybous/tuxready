# Contributing to tuxready

Thanks for helping people move to Linux!

## Add or fix an app (no Python needed)

Everything tuxready knows about Windows programs is in
[`src/tuxready/data/apps.json`](src/tuxready/data/apps.json). Each entry looks like this:

```json
{"names": ["adobe photoshop", "photoshop"], "verdict": "alternative",
 "summary": "Photoshop does not run on Linux. Photopea copies its interface in the browser; ...",
 "alternatives": [{"name": "Photopea (in your browser)", "url": "https://www.photopea.com"},
                  {"name": "Krita", "flatpak": "org.kde.krita"}]}
```

- **names**: lower-case names to match. A name also matches anything that *starts* with it
  as whole words, so `"adobe photoshop"` matches "Adobe Photoshop 2025". Avoid short, generic
  names that could match games (e.g. `"rust"` would match the game Rust).
- **verdict**: one of `native`, `works`, `not_needed`, `tweaks`, `alternative`, `blocked`.
- **summary**: one or two plain sentences for someone new to Linux.
- **flatpak**: (optional) Flathub ID when the app itself runs natively.
- **alternatives**: (optional) each with a `flatpak` ID or a `url`.
- **kind**: (optional) `"game"` for games listed here, e.g. Roblox.

Before opening a pull request, run:

```bash
python scripts/verify_flathub_ids.py   # checks every Flathub ID exists
pytest
```

## Add a hardware rule

Hardware rules live in [`src/tuxready/hardware.py`](src/tuxready/hardware.py), matched by PCI/USB
vendor ID (e.g. `10de` = NVIDIA) and device name. Add a test in `tests/test_hardware.py` with the
device as Windows or Linux reports it. To see what tuxready detects on your machine:

```bash
python -c "from tuxready import hardware; print(*hardware.detect(), sep='\n')"
```

## Working on the code

```bash
git clone https://github.com/Hanocybous/tuxready && cd tuxready
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e . pytest ruff
pytest && ruff check src tests
python -m tuxready "Elden Ring" Discord
```

Layout:

| Path | What it does |
|---|---|
| `inventory/windows.py` | Reads installed programs from the Windows registry and filters out noise (drivers, runtimes) |
| `inventory/steam.py` | Finds Steam libraries and installed games (Windows and Linux) |
| `sources/` | Steam, ProtonDB, AreWeAntiCheatYet and Flathub lookups, with an on-disk cache |
| `checker.py` | Turns all of that into one verdict per item |
| `hardware.py` | Detects GPUs, Wi-Fi, fingerprint readers etc. and applies the hardware rules |
| `setupscript.py` | Builds the `tuxready-setup.sh` install script |
| `report.py` | Score, text, Markdown and JSON output |
| `tui.py` | The interactive view (built with [Textual](https://textual.textualize.io)) |

Tests never touch the network: `tests/test_checker.py` swaps in a fake HTTP client.

## Releasing

Bump `version` in `pyproject.toml` and `src/tuxready/__init__.py`, then:

```bash
git tag v0.2.0 && git push --tags
```

GitHub Actions builds the Windows `.exe`, the Linux binary and the Python package, and
attaches them to a new release.
