"""Readiness score, notes, and the plain-text, Markdown and JSON reports."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date

from tuxready import __version__
from tuxready.models import Kind, Result, Verdict
from tuxready.text import normalize, starts_with_words

ORDER = list(Verdict)
ATTENTION = {Verdict.BLOCKED, Verdict.ALTERNATIVE, Verdict.TWEAKS, Verdict.UNKNOWN}

# Game stores whose libraries tuxready can't scan (yet).
OTHER_LAUNCHERS = {
    "epic games launcher": "Epic Games",
    "gog galaxy": "GOG Galaxy",
    "ea app": "EA app",
    "ea desktop": "EA app",
    "origin": "EA Origin",
    "ubisoft connect": "Ubisoft Connect",
    "uplay": "Ubisoft Connect",
    "battle net": "Battle.net",
    "battlenet": "Battle.net",
    "amazon games": "Amazon Games",
    "xbox": "Xbox app",
}


@dataclass
class Score:
    percent: int | None  # None when nothing could be rated
    counts: Counter
    rated: int
    total: int

    @property
    def headline(self) -> str:
        if self.percent is None:
            return "Not enough information for a score yet"
        return f"{self.percent}% ready for Linux"

    @property
    def mood(self) -> str:
        if self.percent is None:
            return ""
        if self.percent >= 90:
            return "You're ready. Go for it!"
        if self.percent >= 70:
            return "Mostly ready: a few things need alternatives or tweaks."
        if self.percent >= 40:
            return "Doable, but plan for some changes, or dual-boot for a while."
        return "Several blockers. Consider dual-booting, or wait a bit."


def split(results: list[Result]) -> tuple[list[Result], list[Result]]:
    """(apps and games, hardware)."""
    return [r for r in results if not r.is_hardware], [r for r in results if r.is_hardware]


def score(results: list[Result]) -> Score:
    """Score for apps and games. Hardware is reported separately and not scored."""
    software, _ = split(results)
    counts = Counter(r.verdict for r in software)
    rated = [r for r in software if r.verdict.weight is not None]
    if not rated:
        return Score(None, counts, 0, len(software))
    total = sum(r.verdict.weight for r in rated)  # type: ignore[misc]
    return Score(round(100 * total / len(rated)), counts, len(rated), len(software))


def hardware_line(results: list[Result]) -> str:
    _, hardware = split(results)
    if not hardware:
        return ""
    attention = sum(r.verdict in ATTENTION for r in hardware)
    if not attention:
        return f"Hardware: all {len(hardware)} checked parts work on Linux."
    return f"Hardware: {attention} of {len(hardware)} checked parts need attention."


def notes(results: list[Result]) -> list[str]:
    """Things the user should know about how far the results reach."""
    out: list[str] = []
    software, _ = split(results)
    has_games = any(r.item.kind is Kind.GAME for r in software)
    scanned_pc = any(r.item.source in ("steam", "windows") for r in software)
    launchers = sorted(
        {
            label
            for r in software
            for alias, label in OTHER_LAUNCHERS.items()
            if starts_with_words(normalize(r.item.name), alias)
        }
    )
    if not software:
        out.append(
            "No apps or games were found on this PC. Check them by name: "
            'tuxready "Elden Ring" Discord, or tuxready --list my-apps.txt'
        )
    if has_games:
        out.append(
            "Game results are for the Steam version of each game (ratings come from Steam and "
            "ProtonDB)."
        )
    if launchers:
        out.append(
            f"You also use {', '.join(launchers)}. Games from those stores aren't scanned "
            "yet; check them by name."
        )
    elif scanned_pc:
        out.append(
            "Only your Steam library was scanned for games. Games from Epic, GOG, EA or other "
            "stores aren't detected yet; add them by name to check them."
        )
    return out


def sort_results(results: list[Result]) -> list[Result]:
    """Problems first, so the things that need attention are at the top. Hardware last."""
    priority = {
        Verdict.BLOCKED: 0,
        Verdict.ALTERNATIVE: 1,
        Verdict.TWEAKS: 2,
        Verdict.UNKNOWN: 3,
        Verdict.WORKS: 4,
        Verdict.NATIVE: 5,
        Verdict.NOT_NEEDED: 6,
    }
    return sorted(results, key=lambda r: (r.is_hardware, priority[r.verdict], r.item.name.lower()))


def counts_line(s: Score) -> str:
    return "   ".join(f"{v.icon} {v.label}: {s.counts[v]}" for v in ORDER if s.counts[v])


def _plain_entry(r: Result, show_kind: bool = True, icon: str = "•") -> list[str]:
    kind = f" [{r.item.kind.value}]" if show_kind and r.item.kind else ""
    lines = [f"  {icon} {r.item.name}{kind} — {r.summary}"]
    if r.alternatives:
        lines.append(f"      Try: {', '.join(r.alternatives)}")
    if r.how_to:
        label = "Install" if r.verdict is Verdict.NATIVE and r.flatpak else "How"
        lines.append(f"      {label}: {r.how_to}")
    return lines


def plain(results: list[Result]) -> str:
    s = score(results)
    software, hardware = split(results)
    lines = [f"tuxready: {s.headline}", s.mood, counts_line(s)]
    if hardware:
        lines.append(hardware_line(results))
    lines += [f"Note: {note}" for note in notes(results)]
    current = None
    for r in sort_results(software):
        if r.verdict is not current:
            current = r.verdict
            lines += ["", f"{current.icon} {current.label.upper()}"]
        lines += _plain_entry(r)
    if hardware:
        lines += ["", "🖥  HARDWARE"]
        for r in sort_results(hardware):
            lines += _plain_entry(r, show_kind=False, icon=r.verdict.icon)
    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def markdown(results: list[Result]) -> str:
    s = score(results)
    software, hardware = split(results)
    out = [
        f"# My Linux readiness: {s.percent if s.percent is not None else '?'}%",
        "",
        f"*{s.mood}*" if s.mood else "",
        "",
        f"{counts_line(s)}",
        "",
    ]
    out += [f"> {note}" for note in notes(results)]
    out += ["", "| | Name | Type | Verdict | Notes |", "|---|---|---|---|---|"]
    out += [_md_row(r, with_kind=True) for r in sort_results(software)]
    if hardware:
        out += [
            "",
            "## Hardware",
            "",
            hardware_line(results),
            "",
            "| | Part | Verdict | Notes |",
            "|---|---|---|---|",
        ]
        out += [_md_row(r, with_kind=False) for r in sort_results(hardware)]
    out += [
        "",
        f"Generated by [tuxready](https://github.com/Hanocybous/tuxready) {__version__} "
        f"on {date.today().isoformat()}.",
    ]
    return "\n".join(out) + "\n"


def _md_row(r: Result, with_kind: bool) -> str:
    text = r.summary
    if r.alternatives:
        text += " **Try:** " + ", ".join(r.alternatives)
    first_link = f" [{r.links[0].title}]({r.links[0].url})" if r.links else ""
    kind = f" {r.item.kind.value if r.item.kind else ''} |" if with_kind else ""
    return (
        f"| {r.verdict.icon} | {_md(r.item.name)} |{kind} {r.verdict.label} | "
        f"{_md(text)}{first_link} |"
    )


def to_json(results: list[Result]) -> str:
    s = score(results)
    return (
        json.dumps(
            {
                "tuxready": __version__,
                "score": s.percent,
                "counts": {v.value: s.counts[v] for v in ORDER},
                "notes": notes(results),
                "results": [r.to_dict() for r in sort_results(results)],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
