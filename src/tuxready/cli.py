from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tuxready import __version__, hardware, report, setupscript
from tuxready.checker import Checker
from tuxready.inventory import listfile, steam, windows
from tuxready.models import Item, Result
from tuxready.sources.http import Http

EPILOG = """examples:
  tuxready                         scan this PC (installed programs + Steam library)
  tuxready "Elden Ring" Photoshop  check specific apps or games
  tuxready --list my-apps.txt      check a list, one name per line
  tuxready --markdown report.md    save a shareable report
  tuxready --setup-script setup.sh write a script that installs your Linux apps
  tuxready --steam-dir "/run/media/me/Windows/Program Files (x86)/Steam"
                                   scan a Windows Steam library from Linux
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuxready",
        description="Find out how many of your Windows apps and games will work on Linux.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("names", nargs="*", help="apps or games to check (skips the PC scan)")
    parser.add_argument(
        "-l",
        "--list",
        metavar="FILE",
        action="append",
        default=[],
        help="text file with one app or game per line ('-' for stdin)",
    )
    parser.add_argument(
        "--steam-dir",
        metavar="DIR",
        action="append",
        default=[],
        type=Path,
        help="extra Steam folder to scan (can repeat)",
    )
    parser.add_argument(
        "--no-scan", action="store_true", help="don't scan this PC, only check names and lists"
    )
    out = parser.add_mutually_exclusive_group()
    out.add_argument("--plain", action="store_true", help="print a text report instead of the UI")
    out.add_argument("--json", action="store_true", help="print the results as JSON")
    parser.add_argument(
        "--markdown", metavar="FILE", help="also save a Markdown report you can share"
    )
    parser.add_argument(
        "--setup-script",
        metavar="FILE",
        help="also write a bash script that installs the Linux apps (run it after switching)",
    )
    hw = parser.add_mutually_exclusive_group()
    hw.add_argument(
        "--hardware", action="store_true", help="check this PC's hardware even when giving names"
    )
    hw.add_argument("--no-hardware", action="store_true", help="skip the hardware check")
    parser.add_argument("--offline", action="store_true", help="use cached data only")
    parser.add_argument("--refresh", action="store_true", help="ignore cached data and re-download")
    parser.add_argument("--version", action="version", version=f"tuxready {__version__}")
    return parser


def gather(args: argparse.Namespace) -> tuple[list[Item], list[str], list[Result]]:
    items: list[Item] = []
    notes: list[str] = []
    if args.names:
        items += listfile.parse_lines(args.names)
    for path in args.list:
        try:
            items += listfile.read(path)
        except OSError as error:
            raise SystemExit(f"tuxready: can't read {path}: {error.strerror}") from None
    explicit = bool(items)
    if not args.no_scan and (not explicit or args.steam_dir):
        programs = [] if explicit else windows.scan()
        games = steam.scan(args.steam_dir, use_defaults=not explicit)
        if programs:
            notes.append(f"Found {len(programs)} installed programs")
        if games:
            notes.append(f"Found {len(games)} Steam games")
        items += programs + games
    hardware_results: list[Result] = []
    if not args.no_hardware and (args.hardware or (not explicit and not args.no_scan)):
        hardware_results = hardware.check(hardware.detect())
        if hardware_results:
            notes.append(f"Checked {len(hardware_results)} hardware parts")
    return _dedupe(items), notes, hardware_results


def _dedupe(items: list[Item]) -> list[Item]:
    seen: set[str] = set()
    unique = []
    for item in items:
        key = f"steam:{item.steam_appid}" if item.steam_appid else item.name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _utf8_output() -> None:
    # on Windows, redirected output uses an old code page that can't print emoji
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    args = build_parser().parse_args(argv)
    items, notes, hardware_results = gather(args)
    if not items and not hardware_results:
        print(
            "Nothing to check yet.\n\n"
            "tuxready scans installed programs on Windows and Steam libraries on any OS.\n"
            "On this machine it found neither, so tell it what you use instead:\n\n"
            '  tuxready "Elden Ring" Photoshop Discord\n'
            "  tuxready --list my-apps.txt\n\n"
            "Run 'tuxready --help' for more options.",
            file=sys.stderr,
        )
        return 2

    http = Http(offline=args.offline, refresh=args.refresh)
    checker = Checker(http)
    interactive = sys.stdout.isatty() and not (args.plain or args.json)

    if interactive:
        from tuxready.tui import TuxReadyApp

        app = TuxReadyApp(
            checker,
            items,
            notes,
            hardware_results=hardware_results,
            markdown_path=args.markdown,
            setup_path=args.setup_script,
        )
        app.run()
        return 0

    def progress(done: int, total: int, _result) -> None:
        if sys.stderr.isatty():
            print(f"\rChecking {done}/{total}...", end="", file=sys.stderr, flush=True)

    for note in notes:
        print(note, file=sys.stderr)
    results = checker.check_all(items, progress) + hardware_results
    if sys.stderr.isatty():
        print("\r" + " " * 30 + "\r", end="", file=sys.stderr)
    if http.failures:
        print(
            f"Note: {http.failures} online lookups failed; results may be incomplete.",
            file=sys.stderr,
        )

    print(report.to_json(results) if args.json else report.plain(results), end="")
    if args.markdown:
        Path(args.markdown).write_text(report.markdown(results), encoding="utf-8")
        print(f"Saved report to {args.markdown}", file=sys.stderr)
    if args.setup_script:
        path = setupscript.write(results, args.setup_script)
        print(
            f"Saved setup script to {path}. Run it on Linux with: bash {path.name}", file=sys.stderr
        )
    return 0
