# Changelog

## Unreleased

- Cleaned up comments and docstrings, shorter README
- Plain `...` and `-` instead of typographic characters in the UI
- Dependabot for GitHub Actions and Python dependencies

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
