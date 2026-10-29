# tuxready

[![CI](https://github.com/Hanocybous/tuxready/actions/workflows/ci.yml/badge.svg)](https://github.com/Hanocybous/tuxready/actions/workflows/ci.yml)

Thinking about moving from Windows to Linux? tuxready scans your PC and tells you which of
your apps, games and hardware will work, which won't, and what to use instead.

![tuxready screenshot](docs/screenshot.png)

What it checks:

- **Installed programs**: runs natively, works in the browser, or needs an alternative
  (e.g. Photoshop -> Krita or Photopea, Office -> LibreOffice)
- **Steam games**: ProtonDB rating, native Linux version, and whether the anti-cheat
  allows Linux (Valorant and Fortnite don't)
- **Hardware**: NVIDIA (needs the driver), Broadcom Wi-Fi, fingerprint readers, Windows Hello
  cameras, Intel RST/RAID disk mode, Surface and Mac models

You get a readiness score, a report you can save, and a setup script that installs your apps
on the new Linux system.

## Install

**Windows:** download `tuxready-windows-x64.exe` from the
[latest release](https://github.com/Hanocybous/tuxready/releases/latest) and double-click it.
SmartScreen will warn you because the exe isn't signed; click *More info* and *Run anyway*.

**Linux:** download `tuxready-linux-x64` from the same page, or:

```bash
pipx install git+https://github.com/Hanocybous/tuxready
```

The downloads are for 64-bit x86. The Linux binary needs glibc 2.35+ (Ubuntu 22.04, Mint 21,
Fedora 36, Debian 12 or newer); on anything else, use pipx (Python 3.10+). macOS isn't tested.

## Usage

```
tuxready                          scan this PC (installed programs + Steam library)
tuxready "Elden Ring" Photoshop   check specific apps or games
tuxready --list my-apps.txt       check a list, one name per line
tuxready --markdown report.md     save a report
tuxready --setup-script setup.sh  write the install script
tuxready --plain                  text output instead of the interactive view
tuxready --json                   JSON output
```

Run `tuxready --help` for the rest (`--steam-dir`, `--hardware`, `--offline`, ...).

Keys in the interactive view: `f` filter, `/` search, `e` save report, `i` setup script,
`q` quit.

A list file is just names, one per line. Use `game:` or `app:` if a name is ambiguous, or
`steam: <id>` for a Steam game (see [examples/my-apps.txt](examples/my-apps.txt)).

To scan a Windows Steam library from Linux:

```bash
tuxready --steam-dir "/run/media/$USER/Windows/Program Files (x86)/Steam"
```

### Setup script

`tuxready-setup.sh` installs from Flathub the Linux version of each app you have, the first
alternative for apps that don't have one, and Steam if you have games. Other alternatives are
in the file but commented out. Things it can't install (package manager tools, downloads from
the maker's site, web apps, driver notes) are printed at the end. Read it before you run it.

## How it works

- Apps are matched against [apps.json](src/tuxready/data/apps.json), a hand-written list of
  common Windows programs and their Linux alternatives. Anything not in there is looked up on
  [Flathub](https://flathub.org).
- Games are looked up on the Steam store and [ProtonDB](https://www.protondb.com), and checked
  against [AreWeAntiCheatYet](https://areweanticheatyet.com). If the anti-cheat blocks Linux,
  that wins over a good ProtonDB rating.
- Hardware rules are in [hardware.py](src/tuxready/hardware.py) and work offline.

Score: native / works / not needed count 1, tweaks 0.7, alternative 0.5, won't work 0.
Unknowns and hardware aren't counted.

Lookups are cached for a day in `~/.cache/tuxready` (`%LOCALAPPDATA%\tuxready\cache` on
Windows). Only app and game names are sent to those APIs; nothing else leaves your PC.

**Limitations:** only the Steam library is scanned for games, so Epic, GOG, EA and Ubisoft
games need to be checked by name. Game ratings are for the Steam version.

## Building

Tests run on Ubuntu and Windows with Python 3.10 and 3.13 on every push. Release binaries are
built by GitHub Actions with PyInstaller (Windows on `windows-latest`, Linux on Ubuntu 22.04),
and each release has a `SHA256SUMS.txt`.

```bash
pip install -e . pytest && pytest
pip install pyinstaller
pyinstaller --onefile --name tuxready --collect-data tuxready --collect-data textual \
  --collect-submodules rich._unicode_data packaging/entry.py
```

## Contributing

The easiest way to help is adding or fixing entries in `apps.json`, no Python needed. See
[CONTRIBUTING.md](CONTRIBUTING.md). If tuxready gets something wrong,
[open an issue](https://github.com/Hanocybous/tuxready/issues).

## License

MIT. Game data comes from ProtonDB and AreWeAntiCheatYet, both community projects.
