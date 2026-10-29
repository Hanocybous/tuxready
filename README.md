# tuxready 🐧

[![CI](https://github.com/Hanocybous/tuxready/actions/workflows/ci.yml/badge.svg)](https://github.com/Hanocybous/tuxready/actions/workflows/ci.yml)
![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows)
![Linux](https://img.shields.io/badge/Linux-x64-FCC624?logo=linux&logoColor=black)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**Will your apps and games work on Linux? Find out before you switch.**

tuxready scans your Windows PC (installed programs and your Steam library) and tells you,
one by one, what will work on Linux, what won't, and what to use instead.

![tuxready screenshot](docs/screenshot.png)

| You have | tuxready tells you |
|---|---|
| Discord, Spotify, Chrome | ✅ Runs natively, with the install command |
| Elden Ring, Cyberpunk 2077 | ✅ Works through Proton (ProtonDB rating) |
| Valorant, Fortnite, Apex Legends | ❌ Blocked by anti-cheat |
| Photoshop, Microsoft Office | 🔁 Use an alternative: Krita / Photopea, LibreOffice / Office on the web |
| Norton, CCleaner, driver updaters | 💤 Not needed on Linux |

It also checks your **hardware** for the usual trouble spots before you switch: NVIDIA
graphics (needs a driver), Broadcom Wi-Fi (may not work on first boot), fingerprint readers,
Windows Hello cameras, Intel RST/RAID disk mode, Surface and Mac models.

At the end you get a **readiness score**, a report you can share, and a **setup script**:
copy it to your new Linux install and run it to install all your apps in one go.

## Quick start

### On Windows (before switching)

1. Download `tuxready-windows-x64.exe` from the [latest release](https://github.com/Hanocybous/tuxready/releases/latest).
2. Double-click it. That's it: it scans your PC and shows the results.

> Windows SmartScreen may warn about an "unrecognized app" because the file isn't code-signed.
> Click **More info → Run anyway**. You can check the file against `SHA256SUMS.txt` on the release page.

### On Linux (already switched, or checking from a live USB)

```bash
pipx install git+https://github.com/Hanocybous/tuxready   # or download tuxready-linux-x64 from Releases
tuxready "Elden Ring" Photoshop Discord
```

Or point it at the Steam library on your Windows drive:

```bash
tuxready --steam-dir "/run/media/$USER/Windows/Program Files (x86)/Steam"
```

## Supported systems

| | Windows 10 / 11 | Linux | macOS |
|---|:-:|:-:|:-:|
| Ready-made download | ✅ `tuxready-windows-x64.exe` | ✅ `tuxready-linux-x64` | — |
| Install with pipx (Python 3.10+) | ✅ | ✅ | ⚠️ untested |
| Scan installed programs | ✅ | — (you've already switched) | — |
| Scan Steam library | ✅ | ✅ native, Flatpak and Snap Steam | — |
| Hardware check | ✅ | ✅ | — |
| Check apps and games by name | ✅ | ✅ | ⚠️ untested |
| Setup script | ✅ writes it, run it on Linux | ✅ | — |

- The downloads are for **64-bit x86** PCs. On ARM (e.g. Snapdragon laptops, Raspberry Pi),
  install with pipx instead.
- The Linux download needs **glibc 2.35 or newer**: Ubuntu 22.04+, Linux Mint 21+, Fedora 36+,
  Debian 12+, Arch, and anything newer. On older systems, use pipx.
- The interactive view works best in **Windows Terminal** (built into Windows 11) and any Linux
  terminal. If it looks wrong in an older console, use `--plain` for a text report.

### How it's built and tested

Every push runs the tests on **Ubuntu** and **Windows** with **Python 3.10 and 3.13**
([CI](.github/workflows/ci.yml)). On Windows, the test also scans the test machine's real
registry and hardware, so the Windows code runs for real.

Each release is built by GitHub Actions ([release workflow](.github/workflows/release.yml)),
not on someone's PC:

| Download | Built on | With |
|---|---|---|
| `tuxready-windows-x64.exe` | Windows Server (latest) | Python 3.13 + PyInstaller, one file |
| `tuxready-linux-x64` | Ubuntu 22.04 | Python 3.13 + PyInstaller, one file |
| `tuxready-*.whl` / `.tar.gz` | Ubuntu (latest) | Python package for pipx/pip |

Each binary is smoke-tested before upload, and `SHA256SUMS.txt` on the release page lets you
check that your download wasn't tampered with:

```bash
sha256sum -c SHA256SUMS.txt --ignore-missing            # Linux
Get-FileHash .\tuxready-windows-x64.exe -Algorithm SHA256  # Windows (PowerShell)
```

To build a binary yourself:

```bash
pip install . pyinstaller
pyinstaller --onefile --name tuxready --collect-data tuxready --collect-data textual \
  --collect-submodules rich._unicode_data packaging/entry.py   # -> dist/tuxready
```

## Usage

```
tuxready                          scan this PC (installed programs + Steam library)
tuxready "Elden Ring" Photoshop   check specific apps or games
tuxready --list my-apps.txt       check a list, one name per line
tuxready --markdown report.md     also save a shareable Markdown report
tuxready --setup-script setup.sh  also write a script that installs your Linux apps
tuxready --hardware Discord       check hardware too when giving names (--no-hardware to skip)
tuxready --plain                  print a text report instead of the interactive view
tuxready --json                   machine-readable output
tuxready --offline                use cached data only
```

In the interactive view: **↑/↓** browse, **f** filter (problems only, won't work, …),
**/** search, **e** save report, **i** write the setup script, **q** quit.

### The setup script

Press **i** (or use `--setup-script`) to get `tuxready-setup.sh`. It installs, from Flathub:

- the Linux version of every app you use that has one (Discord, Spotify, OBS…)
- the top alternative for apps that don't (Krita for Photoshop, LibreOffice for Office…)
- Steam, if you have games

Other good alternatives are listed in the script too, commented out, so you can switch them
on. Apps that come from the maker's website, web-only apps and hardware reminders (like
installing the NVIDIA driver) are printed at the end. Open the file and read it before running:

```bash
bash tuxready-setup.sh
```

A list file looks like [`examples/my-apps.txt`](examples/my-apps.txt):

```
Discord
Adobe Photoshop
game: Elden Ring
steam: 1172470
```

## How it decides

| Source | Used for |
|---|---|
| Built-in knowledge base ([`apps.json`](src/tuxready/data/apps.json)) | ~150 common Windows programs: verdict and best Linux alternatives |
| [AreWeAntiCheatYet](https://areweanticheatyet.com) | Whether a game's anti-cheat allows Linux |
| [ProtonDB](https://www.protondb.com) | How well a Windows game runs through Proton |
| Steam store | Native Linux versions, and matching game names to Steam IDs |
| [Flathub](https://flathub.org) | Whether an app is available for Linux |

Anti-cheat that blocks Linux overrides everything else, because a game with a Gold rating is
still unplayable online if the anti-cheat kicks you.

Hardware rules are built in ([`hardware.py`](src/tuxready/hardware.py)) and work offline. On
Windows they read the device list through PowerShell; on Linux, from `/sys`.

### Limitations

- **Games are checked against Steam.** Ratings are for the Steam version of each game, and only
  your Steam library is scanned. Games from Epic, GOG, EA or Ubisoft aren't detected yet, but
  you can check them by name (`tuxready "Game name"`). tuxready tells you when it spots one of
  those launchers.
- Fingerprint readers can't be judged automatically; tuxready shows the USB ID to look up.

**The score** counts each app and game (hardware is shown separately): ✅ native/works/not needed = 1, 🔧 tweaks = 0.7,
🔁 alternative = 0.5, ❌ won't work = 0. Unknown items are left out.

Results are cached for a day (`~/.cache/tuxready` or `%LOCALAPPDATA%\tuxready\cache`), so a second run is instant.

## Privacy

tuxready doesn't upload your program list anywhere. It only sends individual app or game
**names** to the public Steam, ProtonDB and Flathub APIs to look them up. There's no telemetry
and no account.

## Contributing

The most useful contribution is **improving the knowledge base**: adding a program people
commonly use, or fixing a verdict that's out of date. It's a single JSON file, so no Python
is needed. See [CONTRIBUTING.md](CONTRIBUTING.md).

Wrong result? [Open an issue](https://github.com/Hanocybous/tuxready/issues) with the name
exactly as tuxready shows it.

## License

MIT. Game data comes from ProtonDB and AreWeAntiCheatYet, which are community projects; please
support them.
