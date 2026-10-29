"""Core data types shared across the app."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Kind(str, Enum):
    APP = "app"
    GAME = "game"


class Verdict(str, Enum):
    """How well something will work on Linux, best first."""

    NATIVE = "native"
    WORKS = "works"
    NOT_NEEDED = "not_needed"
    TWEAKS = "tweaks"
    ALTERNATIVE = "alternative"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return VERDICT_LABELS[self]

    @property
    def icon(self) -> str:
        return VERDICT_ICONS[self]

    @property
    def weight(self) -> float | None:
        """Contribution to the readiness score. None means 'left out of the score'."""
        return VERDICT_WEIGHTS[self]


VERDICT_LABELS = {
    Verdict.NATIVE: "Runs natively",
    Verdict.WORKS: "Works",
    Verdict.NOT_NEEDED: "Not needed on Linux",
    Verdict.TWEAKS: "Works with tweaks",
    Verdict.ALTERNATIVE: "Use an alternative",
    Verdict.BLOCKED: "Won't work",
    Verdict.UNKNOWN: "Unknown",
}

VERDICT_ICONS = {
    Verdict.NATIVE: "✅",
    Verdict.WORKS: "✅",
    Verdict.NOT_NEEDED: "💤",
    Verdict.TWEAKS: "🔧",
    Verdict.ALTERNATIVE: "🔁",
    Verdict.BLOCKED: "❌",
    Verdict.UNKNOWN: "❔",
}

VERDICT_WEIGHTS: dict[Verdict, float | None] = {
    Verdict.NATIVE: 1.0,
    Verdict.WORKS: 1.0,
    Verdict.NOT_NEEDED: 1.0,
    Verdict.TWEAKS: 0.7,
    Verdict.ALTERNATIVE: 0.5,
    Verdict.BLOCKED: 0.0,
    Verdict.UNKNOWN: None,
}


@dataclass(frozen=True)
class Item:
    """Something the user has installed or wants to check."""

    name: str
    kind: Kind | None  # None = not known yet; the checker works it out
    source: str  # "windows", "steam", "list"
    steam_appid: int | None = None
    publisher: str | None = None


@dataclass(frozen=True)
class Link:
    title: str
    url: str


@dataclass
class Result:
    item: Item
    verdict: Verdict
    summary: str
    alternatives: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    how_to: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.item.name,
            "kind": self.item.kind.value if self.item.kind else None,
            "source": self.item.source,
            "steam_appid": self.item.steam_appid,
            "verdict": self.verdict.value,
            "verdict_label": self.verdict.label,
            "summary": self.summary,
            "alternatives": self.alternatives,
            "how_to": self.how_to,
            "links": [{"title": link.title, "url": link.url} for link in self.links],
        }
