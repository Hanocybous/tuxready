from pathlib import Path

from tuxready.inventory import listfile, steam, windows
from tuxready.models import Kind

LIBRARY_VDF = """
"libraryfolders"
{
    // a comment
    "0"
    {
        "path"      "%s"
        "apps" { "1245620" "123" }
    }
    "1"
    {
        "path"      "/does/not/exist"
    }
}
"""

MANIFEST = """
"AppState"
{
    "appid"     "%d"
    "name"      "%s"
    "StateFlags" "4"
}
"""


def test_parse_vdf_nested_and_escaped():
    data = steam.parse_vdf('"a" { "b" "say \\"hi\\"" "c" { "d" "1" } }')
    assert data == {"a": {"b": 'say "hi"', "c": {"d": "1"}}}


def make_steam(tmp_path: Path, games: dict[int, str]) -> Path:
    root = tmp_path / "Steam"
    apps = root / "steamapps"
    apps.mkdir(parents=True)
    (apps / "libraryfolders.vdf").write_text(LIBRARY_VDF % root)
    for appid, name in games.items():
        (apps / f"appmanifest_{appid}.acf").write_text(MANIFEST % (appid, name))
    return root


def test_steam_scan_finds_games_and_skips_tools(tmp_path):
    root = make_steam(
        tmp_path,
        {
            1245620: "ELDEN RING",
            1493710: "Proton Experimental",
            228980: "Steamworks Common Redistributables",
            570: "Dota 2",
        },
    )
    games = steam.scan([root], use_defaults=False)
    assert [(g.name, g.steam_appid) for g in games] == [("Dota 2", 570), ("ELDEN RING", 1245620)]
    assert all(g.kind is Kind.GAME for g in games)


def test_steam_scan_dedupes_same_library(tmp_path):
    root = make_steam(tmp_path, {570: "Dota 2"})
    assert len(steam.scan([root, root], use_defaults=False)) == 1


def test_windows_filter_hides_noise():
    keep = {"DisplayName": "Discord", "KeyName": "Discord"}
    assert windows.is_user_facing(keep)
    for noise in (
        {"DisplayName": "Microsoft Visual C++ 2015-2022 Redistributable (x64)"},
        {"DisplayName": "NVIDIA Graphics Driver 560.94"},
        {"DisplayName": "Realtek High Definition Audio Driver"},
        {"DisplayName": "Python 3.12.1 Core Interpreter (64-bit)"},
        {"DisplayName": "Some Helper", "SystemComponent": 1},
        {"DisplayName": "KB5005463", "ReleaseType": "Update"},
        {"DisplayName": "Elden Ring", "KeyName": "Steam App 1245620"},
        {"DisplayName": ""},
        {"DisplayName": "Riot Vanguard"},
        {"DisplayName": "THX Spatial Audio USB 1532-0579!057A"},
        {"DisplayName": "Samsung_MonSetup"},
    ):
        assert not windows.is_user_facing(noise), noise


def test_windows_filter_keeps_real_apps_with_similar_names():
    assert windows.is_user_facing({"DisplayName": "Python 3.12.1 (64-bit)"})
    assert windows.is_user_facing({"DisplayName": "NVIDIA App"})


def test_clean_name():
    assert windows.clean_name("Notepad++ (64-bit x64)") == "Notepad++"
    assert windows.clean_name("7-Zip 24.08 (x64)") == "7-Zip"
    assert windows.clean_name("Cyberpunk 2077") == "Cyberpunk 2077"
    assert windows.clean_name("Geeks3D FurMark 2.10.2 x64") == "Geeks3D FurMark"


def test_listfile():
    items = listfile.parse_lines(
        [
            "# my stuff",
            "",
            "Photoshop",
            "game: Elden Ring",
            "app: Discord",
            "steam: 570",
            "photoshop",
        ]
    )
    assert [(i.name, i.kind, i.steam_appid) for i in items] == [
        ("Photoshop", None, None),
        ("Elden Ring", Kind.GAME, None),
        ("Discord", Kind.APP, None),
        ("Steam app 570", Kind.GAME, 570),
    ]


def test_windows_scan_filters_cleans_and_dedupes(monkeypatch):
    monkeypatch.setattr(
        windows,
        "read_registry",
        lambda: [
            {"DisplayName": "Discord", "KeyName": "Discord", "Publisher": "Discord Inc."},
            {"DisplayName": "7-Zip 24.08 (x64)", "KeyName": "7-Zip"},
            {"DisplayName": "7-Zip 24.08 (x64)", "KeyName": "7-Zip"},  # 32 + 64-bit views
            {"DisplayName": "Microsoft Visual C++ 2022 X64 Minimum Runtime - 14.40"},
            {"DisplayName": "ELDEN RING", "KeyName": "Steam App 1245620"},
        ],
    )
    items = windows.scan()
    assert [(i.name, i.source, i.kind) for i in items] == [
        ("7-Zip", "windows", None),
        ("Discord", "windows", None),
    ]
