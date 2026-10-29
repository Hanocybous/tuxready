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
        assert entry.get("install") in (None, "package", "vendor", "none"), entry
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


# Programs installed on GitHub's Windows test machine (a typical developer PC).
DEV_PC = [
    "AWS Command Line Interface v2",
    "AWS SAM Command Line Interface",
    "Azure Cosmos DB Emulator",
    "GitHub CLI",
    "IIS 10.0 Express",
    "ImageMagick 7.1.2-25 Q16-HDRI (64-bit) (2026-06-04)",
    "Inno Setup version 6.4.3",
    "LLVM",
    "Microsoft Azure CLI",
    "Microsoft Azure Service Fabric",
    "Microsoft Azure Service Fabric SDK",
    "Microsoft SQL Server 2025 LocalDB",
    "Microsoft SQL Server Integration Services Projects",
    "Microsoft Web Deploy",
    "Miniconda3 py314_26.9.3-0 (Python 3.14.8 64-bit)",
    "MongoDB 7.0.45 2008R2Plus SSL (64 bit)",
    "MongoDB Shell",
    "MySQL Server",
    "OpenSSL",
    "PostgreSQL 17",
    "PowerShell 7-x64",
    "R for Windows",
    "Rtools 4.5 (6768-6492)",
    "sbt",
    "Session Manager Plugin",
    "Strawberry Perl",
    "Windows Application Driver",
    "WiX Toolset",
]
DEV_PC_NOISE = [
    "Mozilla Maintenance Service",
    "Microsoft System CLR Types for SQL Server 2019",
    "Microsoft SQL Server 2016 Management Objects",
    "Microsoft Visual Studio Installer",
    "Microsoft Visual Studio Tools for Applications 2022",
    "PowerShell Extensions for SQL Server 2016",
    "Microsoft SQL Server Data-Tier Application Framework",
    "Microsoft Web Platform Installer",
    "Microsoft Windows Application Compatibility Fix Database",
]


def test_developer_pc_has_no_unknowns(monkeypatch):
    from tuxready.inventory import windows

    monkeypatch.setattr(
        windows, "read_registry", lambda: [{"DisplayName": n} for n in DEV_PC + DEV_PC_NOISE]
    )
    items = windows.scan()
    assert len(items) == len(DEV_PC)  # all the noise is hidden
    results = make_checker({}).check_all(items)
    unknown = [r.item.name for r in results if r.verdict is Verdict.UNKNOWN]
    assert unknown == []


# A typical Windows 11 laptop: dev tools, games, laptop-maker utilities and bundled helpers.
LAPTOP = [
    "CrystalDiskInfo",
    "Epic Games Launcher",
    "HWiNFO® 64",
    "Microsoft 365 - en-us",
    "WinRAR",
    "Xbox Service",
    "Microsoft OneDrive",
    "AI Playground",
    "Bun",
    "Copilot",
    "doxygen",
    "GitHub Copilot",
    "GlideX Service Installer",
    "Intel® VTune(TM) Profiler",
    "Fortnite",
    "NVIDIA GeForce NOW",
    "RPG MAKER VX Ace RTP",
    "Samsung USB Driver for Mobile Phones",
    "Smart Switch Service",
    "starship",
    "StoryCube Service Installer",
    "zoxide",
    "7-Zip",
    "Brave",
    "CLion",
    "Discord",
    "Eclipse Temurin JDK with Hotspot 21.0.12.1+1 (x64)",
    "Git",
    "GitHub CLI",
    "MEGAsync",
    "Microsoft Edge",
    "Microsoft Visual Studio Code (User)",
    "Node.js",
    "PyCharm",
    "Steam",
    "TeamViewer",
    "WebStorm",
    "Zoom Workplace",
]


def test_typical_laptop_has_no_unknowns(monkeypatch):
    from tuxready.inventory import windows

    entries = [{"DisplayName": n} for n in LAPTOP + ["AntiCheatExpert"]]
    monkeypatch.setattr(windows, "read_registry", lambda: entries)
    items = windows.scan()
    names = {i.name for i in items}
    assert "AntiCheatExpert" not in names
    assert {
        "Microsoft Visual Studio Code",
        "Microsoft 365",
        "Eclipse Temurin JDK with Hotspot",
    } <= names
    checker = make_checker({})
    checker._anticheat = AntiCheatDB(
        ANTICHEAT
        + [
            {
                "name": "Nikke: Goddess of Victory",
                "status": "Running",
                "anticheats": ["Anti-Cheat Expert"],
                "storeIds": {},
            }
        ]
    )
    results = checker.check_all(items)
    assert [r.item.name for r in results if r.verdict is Verdict.UNKNOWN] == []


def test_anticheat_name_matching():
    db = AntiCheatDB(
        [
            {"name": "Nikke: Goddess of Victory", "status": "Running"},
            {"name": "Brown Dust 2", "status": "Running"},
            {"name": "Halo Infinite", "status": "Running"},
            {"name": "Halo: The Master Chief Collection", "status": "Running"},
        ]
    )
    assert db.lookup("NIKKE")["name"] == "Nikke: Goddess of Victory"
    assert db.lookup("BrownDust2")["name"] == "Brown Dust 2"
    assert db.lookup("Halo") is None  # two games start with "Halo": don't guess
    assert db.lookup("Dis") is None  # too short to guess
