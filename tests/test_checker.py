"""Checker logic, with every online source replaced by canned answers."""

import pytest

from tuxready import knowledge, report
from tuxready.checker import Checker
from tuxready.models import Item, Kind, Verdict
from tuxready.sources.anticheat import AntiCheatDB
from tuxready.text import normalize


class FakeHttp:
    """Answers the URLs tuxready asks for, from a dict. Anything else is 'not found'."""

    failures = 0

    def __init__(self, responses: dict):
        self.responses = responses
        self.calls: list[str] = []

    def get_json(self, url, ttl=0):
        self.calls.append(url)
        for fragment, data in self.responses.items():
            if fragment in url:
                return data
        return None

    def post_json(self, url, body, ttl=0):
        return self.get_json(f"{url}?q={body['query']}")


ANTICHEAT = [
    {
        "name": "Fortnite",
        "status": "Denied",
        "anticheats": ["Easy Anti-Cheat"],
        "storeIds": {"epic": {"slug": "fortnite"}},
        "slug": "fortnite",
    },
    {
        "name": "Elden Ring",
        "status": "Supported",
        "anticheats": ["Easy Anti-Cheat"],
        "storeIds": {"steam": "1245620"},
        "slug": "elden-ring",
    },
    {
        "name": "Helldivers 2",
        "status": "Running",
        "anticheats": ["nProtect GameGuard"],
        "storeIds": {"steam": "553850"},
        "slug": "helldivers-2",
    },
]


def make_checker(responses: dict) -> Checker:
    checker = Checker(FakeHttp(responses))
    checker._anticheat = AntiCheatDB(ANTICHEAT)
    return checker


def test_normalize():
    assert normalize("HELLDIVERS™ 2") == "helldivers 2"
    assert normalize("Baldur's Gate 3") == "baldurs gate 3"
    assert normalize("Pokémon: Café Mix") == "pokemon cafe mix"


def test_knowledge_prefers_longest_alias():
    assert knowledge.match("Adobe Photoshop 2025")["verdict"] == "alternative"
    assert knowledge.match("Epic Games Launcher")["names"][0] == "epic games launcher"
    assert knowledge.match("Mega Man 11") is None
    assert knowledge.match("Rust") is None


def test_knowledge_file_is_valid():
    valid = {v.value for v in Verdict}
    for entry in knowledge.entries():
        assert entry["names"] and entry["summary"], entry
        assert entry["verdict"] in valid, entry
        assert entry.get("kind") in (None, "app", "game"), entry
        for alt in entry.get("alternatives", []):
            assert alt["name"], entry


def test_known_app_uses_knowledge_base():
    result = make_checker({}).check(Item("Notepad++", None, "windows"))
    assert result.verdict is Verdict.ALTERNATIVE
    assert "Kate" in result.alternatives


def test_anticheat_denied_blocks_game():
    result = make_checker({}).check(Item("Fortnite", None, "list"))
    assert result.verdict is Verdict.BLOCKED
    assert "Easy Anti-Cheat" in result.summary


def test_proton_gold_works_and_uses_anticheat_steam_id():
    checker = make_checker(
        {
            "protondb.com/api/v1/reports/summaries/553850": {"tier": "gold", "total": 900},
            "appdetails?appids=553850": {
                "553850": {
                    "success": True,
                    "data": {
                        "name": "HELLDIVERS™ 2",
                        "platforms": {"windows": True, "linux": False},
                    },
                }
            },
        }
    )
    result = checker.check(Item("Helldivers 2", None, "list"))
    assert result.verdict is Verdict.WORKS
    assert result.item.steam_appid == 553850
    assert "supports Linux" in result.summary


def test_native_linux_steam_game():
    checker = make_checker(
        {
            "appdetails?appids=570": {
                "570": {"success": True, "data": {"name": "Dota 2", "platforms": {"linux": True}}}
            },
        }
    )
    result = checker.check(Item("Steam app 570", Kind.GAME, "list", steam_appid=570))
    assert result.verdict is Verdict.NATIVE
    assert result.item.name == "Dota 2"


@pytest.mark.parametrize(
    "tier, verdict",
    [
        ("platinum", Verdict.WORKS),
        ("silver", Verdict.TWEAKS),
        ("borked", Verdict.BLOCKED),
    ],
)
def test_proton_tiers(tier, verdict):
    checker = make_checker({"summaries/42": {"tier": tier, "total": 50}})
    result = checker.check(Item("Some Game", Kind.GAME, "steam", steam_appid=42))
    assert result.verdict is verdict


def test_unknown_thing_falls_back_to_flathub_then_steam_search():
    checker = make_checker(
        {
            "flathub.org/api/v2/search?q=Bottles": {
                "hits": [
                    {
                        "name": "Bottles",
                        "app_id": "com.usebottles.bottles",
                        "summary": "Run Windows software",
                    }
                ]
            },
        }
    )
    result = checker.check(Item("Bottles", None, "list"))
    assert result.verdict is Verdict.NATIVE
    assert result.how_to == "flatpak install flathub com.usebottles.bottles"

    nothing = make_checker({}).check(Item("Totally Unknown Thing", None, "list"))
    assert nothing.verdict is Verdict.UNKNOWN


def test_one_failing_item_does_not_stop_the_scan(monkeypatch):
    checker = make_checker({})
    monkeypatch.setattr(checker, "check", lambda item: 1 / 0)
    [result] = checker.check_all([Item("Boom", None, "list")])
    assert result.verdict is Verdict.UNKNOWN


def test_score_ignores_unknowns():
    checker = make_checker({})
    results = checker.check_all(
        [
            Item("Discord", None, "list"),  # native, 1.0
            Item("Notepad++", None, "list"),  # alternative, 0.5
            Item("Fortnite", None, "list"),  # blocked, 0
            Item("Who Knows", None, "list"),  # unknown, not scored
        ]
    )
    s = report.score(results)
    assert s.percent == 50
    assert s.rated == 3 and s.total == 4
    assert "50%" in report.markdown(results)
