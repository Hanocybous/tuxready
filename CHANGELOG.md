# Changelog

## Unreleased

- Cleaned up comments and docstrings, shorter README
- Plain `...` and `-` instead of typographic characters in the UI
- Dependabot for GitHub Actions and Python dependencies
- Better recent ProtonDB reports now beat an older, lower overall rating
- App-list entries can match Steam games by ID (`steam_appids`), e.g. Wallpaper Engine
- 13 more apps known (Tailscale, LTspice, Virtual Desktop, Overwolf, ...)
- Riot Client/Vanguard, device drivers and helper tools no longer show up as separate apps
- Fixed version numbers left in names like "FurMark 2.10.2 x64"
- Shorter GPU names on Linux ("Intel Arc Graphics 130V/140V GPU", "NVIDIA GeForce RTX 4070")
- The Type column shows the hardware part (GPU, Wi-Fi, ...); JSON `source` for hardware is now that part type

## 0.1.0 - 2026-10-29

First release.

- Scans installed Windows programs (registry) and Steam libraries on Windows and Linux
- Checks apps against a built-in list of ~170 programs and Flathub
- Checks games against ProtonDB, the Steam store and AreWeAntiCheatYet
- Hardware check: NVIDIA, Broadcom Wi-Fi, fingerprint readers, Windows Hello cameras,
  Intel RST/RAID, Surface and Mac models
- Readiness score, Markdown/JSON reports and a Flathub setup script
- Interactive terminal view, plus `--plain` and `--json` output
- Windows `.exe` and Linux binary built by GitHub Actions
