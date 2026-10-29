import shutil
import subprocess
import sys

import pytest

from tuxready import hardware, report, setupscript
from tuxready.checker import Checker
from tuxready.hardware import Device
from tuxready.models import Item, Kind, Result, Verdict
from tuxready.sources.anticheat import AntiCheatDB


class NoNetwork:
    failures = 0

    def get_json(self, url, ttl=0):
        return None

    def post_json(self, url, body, ttl=0):
        return None


def check(*names, source="windows"):
    checker = Checker(NoNetwork())
    checker._anticheat = AntiCheatDB([])
    return checker.check_all([Item(n, None, source) for n in names])


def test_plan_installs_natives_and_first_alternative():
    results = check(
        "Discord",
        "Adobe Photoshop 2025",
        "Notepad++",
        "Norton 360",
        "1Password",
        "Microsoft Teams",
        "Valorant",
    )
    p = setupscript.plan(results)
    installed = [app_id for app_id, _ in p.install]
    assert "com.discordapp.Discord" in installed
    assert "org.kde.krita" in installed  # first desktop alternative to Photoshop
    assert "org.gimp.GIMP" in [app_id for app_id, _ in p.optional]
    assert "org.kde.kate" in installed  # Notepad++
    assert "1Password" in [name for name, _ in p.vendor]
    assert "Microsoft Teams" in [name for name, _ in p.web]
    assert not any("Norton" in c or "Valorant" in c for _, c in p.install)


def test_plan_adds_steam_for_games_and_hardware_reminders():
    games = [
        Result(Item("Elden Ring", Kind.GAME, "steam", steam_appid=1245620), Verdict.WORKS, "Works")
    ]
    hw = hardware.check([Device("gpu", "NVIDIA GeForce RTX 3070", "10de", "2484")])
    p = setupscript.plan(games + hw)
    assert ("com.valvesoftware.Steam", "Steam (for your games)") in p.install
    assert any("NVIDIA" in text for text in p.reminders)
    assert any("Steam Play" in text for text in p.reminders)


UNIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="needs a Unix bash"
)


@UNIX_ONLY
def test_script_is_valid_bash(tmp_path):
    results = check("Discord", "Adobe Photoshop", "1Password", "WhatsApp")
    path = setupscript.write(results, tmp_path / "setup.sh")
    text = path.read_text()
    assert text.startswith("#!/usr/bin/env bash")
    assert "\r" not in text
    assert "com.discordapp.Discord" in text
    assert subprocess.run(["bash", "-n", str(path)]).returncode == 0


@UNIX_ONLY
def test_script_runs_with_fake_flatpak(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    log = tmp_path / "calls.log"
    (fake / "flatpak").write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
    (fake / "flatpak").chmod(0o755)
    path = setupscript.write(check("Discord", "Spotify"), tmp_path / "setup.sh")
    run = subprocess.run(
        ["bash", str(path)], capture_output=True, text=True, env={"PATH": f"{fake}:/usr/bin:/bin"}
    )
    assert run.returncode == 0, run.stderr
    assert "All done: 2 apps installed." in run.stdout
    calls = log.read_text()
    assert "install -y --noninteractive flathub com.discordapp.Discord" in calls
    assert "remote-add --if-not-exists flathub" in calls


def test_notes_steam_only_and_other_launchers():
    scan = check("Discord", source="windows") + [
        Result(Item("Elden Ring", Kind.GAME, "steam", steam_appid=1), Verdict.WORKS, "ok")
    ]
    notes = report.notes(scan)
    assert any("Steam version" in n for n in notes)
    assert any("Only your Steam library" in n for n in notes)

    with_epic = scan + check("Epic Games Launcher", "GOG GALAXY")
    notes = report.notes(with_epic)
    assert any("Epic Games, GOG Galaxy" in n for n in notes)
    assert not any("Only your Steam library" in n for n in notes)


def test_notes_when_only_hardware_found():
    hw = hardware.check([Device("gpu", "AMD Radeon RX 6600", "1002", "73ff")])
    assert any("No apps or games were found" in n for n in report.notes(hw))


def test_script_sections():
    results = check("Git", "Node.js", "1Password", "Microsoft Teams", "CrystalDiskInfo")
    p = setupscript.plan(results)
    assert {"Git", "Node.js"} <= set(p.packages)
    assert [name for name, _ in p.vendor] == ["1Password"]
    assert [name for name, _ in p.web] == ["Microsoft Teams"]
    assert [name for name, _ in p.instead] == ["CrystalDiskInfo"]
    text = setupscript.build(results)
    assert "Install with your package manager" in text
    assert "Nothing to install, but read this" in text
