"""Write a shell script that installs the Linux versions of everything, in one go."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from tuxready import __version__
from tuxready.models import Kind, Result, Verdict

STEAM_ID = "com.valvesoftware.Steam"


@dataclass
class Plan:
    install: list[tuple[str, str]] = field(default_factory=list)  # (flatpak id, comment)
    optional: list[tuple[str, str]] = field(default_factory=list)  # commented out by default
    packages: list[str] = field(default_factory=list)  # names: install with the package manager
    vendor: list[tuple[str, str]] = field(default_factory=list)  # (name, note): maker's website
    web: list[tuple[str, str]] = field(default_factory=list)  # (name, note): use in browser
    instead: list[tuple[str, str]] = field(default_factory=list)  # (name, note): no app to install
    reminders: list[str] = field(default_factory=list)

    def ids(self) -> set[str]:
        return {app_id for app_id, _ in self.install + self.optional}


def plan(results: list[Result]) -> Plan:
    p = Plan()
    chosen: set[str] = set()

    def add(app_id: str, comment: str, optional: bool = False) -> None:
        if app_id in chosen:
            return
        chosen.add(app_id)
        (p.optional if optional else p.install).append((app_id, comment))

    has_games = any(r.item.kind is Kind.GAME and r.verdict is not Verdict.BLOCKED for r in results)
    for r in sorted(results, key=lambda r: r.item.name.lower()):
        name = r.item.name
        if r.is_hardware:
            if r.verdict in (Verdict.TWEAKS, Verdict.BLOCKED) and r.how_to:
                p.reminders.append(f"{name}: {r.how_to}")
            continue
        if r.verdict in (Verdict.BLOCKED, Verdict.NOT_NEEDED, Verdict.UNKNOWN):
            continue
        alts = list(r.alt_flatpaks.items())
        if r.flatpak:
            add(r.flatpak, name)
            for alt_name, app_id in alts:
                add(app_id, f"{alt_name} (another option for {name})", optional=True)
        elif r.verdict in (Verdict.ALTERNATIVE, Verdict.TWEAKS) and alts:
            first_name, first_id = alts[0]
            add(first_id, f"{first_name} (instead of {name})")
            for alt_name, app_id in alts[1:]:
                add(app_id, f"{alt_name} (another option for {name})", optional=True)
        elif r.item.kind is Kind.GAME:
            continue  # games come through Steam (added below)
        elif r.verdict is Verdict.NATIVE:
            if "package" in r.summary.lower():
                p.packages.append(name)
            else:
                p.vendor.append((name, r.summary))
        elif r.verdict is Verdict.WORKS:
            p.web.append((name, r.summary))
            for alt_name, app_id in alts:
                add(app_id, f"{alt_name} (desktop app for {name})", optional=True)
        elif r.verdict in (Verdict.ALTERNATIVE, Verdict.TWEAKS):
            p.instead.append((name, r.summary))
    if has_games and STEAM_ID not in chosen:
        add(STEAM_ID, "Steam (for your games)")
    if has_games:
        p.reminders.append(
            "Steam: Settings → Compatibility → turn on 'Enable Steam Play for all other titles' "
            "so your Windows games run."
        )
    return p


def build(results: list[Result], filename: str = "tuxready-setup.sh") -> str:
    p = plan(results)
    width = max([len(app_id) for app_id in p.ids()] + [20])
    lines = [
        "#!/usr/bin/env bash",
        f"# Linux setup script made by tuxready {__version__} on {date.today().isoformat()}",
        "# https://github.com/Hanocybous/tuxready",
        "#",
        "# Installs the Linux versions of your apps from Flathub.",
        "# Read it first: put a # in front of anything you don't want,",
        "# or remove the # from the optional extras. Then run:",
        "#",
        f"#     bash {filename}",
        "",
        "set -u",
        "",
        "if ! command -v flatpak >/dev/null 2>&1; then",
        '  echo "Flatpak is not installed yet. Set it up first: https://flathub.org/setup"',
        "  exit 1",
        "fi",
        "flatpak remote-add --if-not-exists flathub "
        "https://dl.flathub.org/repo/flathub.flatpakrepo",
        "",
        "apps=(",
    ]
    lines += [f"  {app_id:<{width}}  # {comment}" for app_id, comment in p.install]
    if p.optional:
        lines += ["", "  # Optional extras (remove the # at the start of a line to include it):"]
        lines += [f"  # {app_id:<{width}}  # {comment}" for app_id, comment in p.optional]
    lines += [
        ")",
        "",
        "failed=()",
        'for app in "${apps[@]}"; do',
        '  echo "==> Installing $app"',
        '  flatpak install -y --noninteractive flathub "$app" || failed+=("$app")',
        "done",
        "",
        "echo",
        "if [ ${#failed[@]} -eq 0 ]; then",
        '  echo "All done: ${#apps[@]} apps installed."',
        "else",
        '  echo "Installed $(( ${#apps[@]} - ${#failed[@]} )) of ${#apps[@]}. These failed:"',
        '  printf "  %s\\n" "${failed[@]}"',
        "fi",
    ]
    if p.packages or p.vendor or p.web or p.instead or p.reminders:
        lines += ["", "cat <<'NOTES'", "", "Still to do by hand:"]
        if p.packages:
            lines += ["", "Install with your package manager (dnf, apt, pacman...):"]
            lines += [f"  - {', '.join(p.packages)}"]
        if p.vendor:
            lines += ["", "Download from the maker's website (not on Flathub):"]
            lines += [f"  - {name}: {note}" for name, note in p.vendor]
        if p.web:
            lines += ["", "Use in your web browser:"]
            lines += [f"  - {name}: {note}" for name, note in p.web]
        if p.instead:
            lines += ["", "Nothing to install, but read this:"]
            lines += [f"  - {name}: {note}" for name, note in p.instead]
        if p.reminders:
            lines += ["", "Reminders:"]
            lines += [f"  - {text}" for text in p.reminders]
        lines += ["NOTES"]
    return "\n".join(lines) + "\n"


def write(results: list[Result], path: str | Path) -> Path:
    path = Path(path)
    # Always Unix line endings, even when written on Windows, or bash will choke on it.
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(build(results, path.name))
    try:
        path.chmod(0o755)
    except OSError:
        pass
    return path
