"""Interactive terminal UI (built with Textual)."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.markup import escape
from textual.widgets import DataTable, Footer, Header, Input, ProgressBar, Static

from tuxready import report
from tuxready.checker import Checker
from tuxready.models import Item, Result, Verdict

FILTERS: list[tuple[str, set[Verdict] | None]] = [
    ("All", None),
    ("Problems", {Verdict.BLOCKED, Verdict.ALTERNATIVE, Verdict.TWEAKS, Verdict.UNKNOWN}),
    ("Won't work", {Verdict.BLOCKED}),
    ("Needs alternative", {Verdict.ALTERNATIVE}),
    ("Needs tweaks", {Verdict.TWEAKS}),
    ("Works", {Verdict.NATIVE, Verdict.WORKS, Verdict.NOT_NEEDED}),
    ("Unknown", {Verdict.UNKNOWN}),
]

# Plain symbols: emoji widths vary between terminals and break the table columns.
SYMBOL = {
    Verdict.NATIVE: "✔",
    Verdict.WORKS: "✔",
    Verdict.NOT_NEEDED: "–",
    Verdict.TWEAKS: "~",
    Verdict.ALTERNATIVE: "⇄",
    Verdict.BLOCKED: "✘",
    Verdict.UNKNOWN: "?",
}

VERDICT_STYLE = {
    Verdict.NATIVE: "bold green",
    Verdict.WORKS: "green",
    Verdict.NOT_NEEDED: "dim",
    Verdict.TWEAKS: "yellow",
    Verdict.ALTERNATIVE: "dark_orange",
    Verdict.BLOCKED: "bold red",
    Verdict.UNKNOWN: "grey50",
}


class TuxReadyApp(App):
    TITLE = "tuxready"
    SUB_TITLE = "Will your stuff work on Linux?"
    CSS = """
    #score { height: auto; padding: 1 2; background: $boost; }
    #progress { padding: 0 2; height: auto; }
    #search { margin: 0 1; display: none; }
    #search.visible { display: block; }
    #body { height: 1fr; }
    #table { width: 3fr; }
    #details { width: 2fr; padding: 1 2; border-left: tall $primary; }
    """
    BINDINGS = [
        Binding("f", "next_filter", "Filter"),
        Binding("slash", "search", "Search"),
        Binding("e", "export", "Save report"),
        Binding("escape", "clear_search", "Clear search", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        checker: Checker,
        items: list[Item],
        notes: list[str],
        markdown_path: str | None = None,
    ):
        super().__init__()
        self.checker = checker
        self.items = items
        self.notes = notes
        self.markdown_path = markdown_path or "tuxready-report.md"
        self.results: list[Result] = []
        self.filter_index = 0
        self.search_text = ""
        self.shown: list[Result] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._intro(), id="score")
        yield ProgressBar(total=len(self.items), id="progress", show_eta=False)
        search = Input(placeholder="Search by name…  (Esc to clear)", id="search")
        search.can_focus = False  # until "/" opens it, so letter keys reach the shortcuts
        yield search
        with Horizontal(id="body"):
            yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="details"):
                yield Static("Select a row to see details.", id="detail-text")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("", key="icon", width=1)
        table.add_column("Name", key="name")
        table.add_column("Type", key="kind", width=5)
        table.add_column("Verdict", key="verdict")
        table.focus()
        self.run_checks()

    def _intro(self) -> str:
        found = " · ".join(self.notes) if self.notes else f"Checking {len(self.items)} items"
        return f"[b]Checking…[/b]\n{escape(found)}"

    @work(thread=True, exclusive=True)
    def run_checks(self) -> None:
        def progress(done: int, total: int, _result: Result) -> None:
            self.call_from_thread(self.query_one(ProgressBar).update, progress=done)

        results = self.checker.check_all(self.items, progress)
        self.call_from_thread(self._show_results, results)

    def _show_results(self, results: list[Result]) -> None:
        self.results = report.sort_results(results)
        self.query_one(ProgressBar).display = False
        self._render_score()
        self._refresh_table()
        if self.checker.http.failures:
            self.notify(
                f"{self.checker.http.failures} online lookups failed; some results may be missing.",
                severity="warning",
                timeout=8,
            )

    def _render_score(self) -> None:
        s = report.score(self.results)
        if s.percent is None:
            bar = ""
        else:
            filled = round(s.percent / 5)
            color = "green" if s.percent >= 70 else "yellow" if s.percent >= 40 else "red"
            bar = f"[{color}]{'█' * filled}[/][dim]{'░' * (20 - filled)}[/]  "
        counts = "   ".join(
            f"[{VERDICT_STYLE[v]}]{SYMBOL[v]} {v.label}: {s.counts[v]}[/]"
            for v in report.ORDER
            if s.counts[v]
        )
        filt = FILTERS[self.filter_index][0]
        if self.search_text:
            filt += f" · search: {escape(self.search_text)}"
        self.query_one("#score", Static).update(
            f"{bar}[b]{escape(s.headline)}[/b]\n{escape(s.mood)}\n"
            f"{counts}\n"
            f"[dim]Showing: {filt}[/dim]"
        )

    def _refresh_table(self) -> None:
        wanted = FILTERS[self.filter_index][1]
        query = self.search_text.lower()
        self.shown = [
            r
            for r in self.results
            if (wanted is None or r.verdict in wanted)
            and (not query or query in r.item.name.lower())
        ]
        table = self.query_one(DataTable)
        table.clear()
        for index, r in enumerate(self.shown):
            style = VERDICT_STYLE[r.verdict]
            table.add_row(
                Text(SYMBOL[r.verdict], style=style),
                Text(r.item.name),
                r.item.kind.value if r.item.kind else "",
                Text(r.verdict.label, style=style),
                key=str(index),
            )
        if self.shown:
            self._show_details(self.shown[0])
        else:
            self.query_one("#detail-text", Static).update("Nothing matches this filter.")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None and event.row_key.value is not None:
            index = int(event.row_key.value)
            if 0 <= index < len(self.shown):
                self._show_details(self.shown[index])

    def _show_details(self, r: Result) -> None:
        style = VERDICT_STYLE[r.verdict]
        parts = [
            f"[b]{escape(r.item.name)}[/b]",
            f"[{style}]{SYMBOL[r.verdict]} {r.verdict.label}[/]",
            "",
            escape(r.summary),
        ]
        if r.alternatives:
            parts += ["", "[b]Try instead:[/b]"] + [f"  • {escape(a)}" for a in r.alternatives]
        if r.how_to:
            parts += ["", "[b]How:[/b]", f"  [cyan]{escape(r.how_to)}[/]"]
        if r.links:
            parts += ["", "[b]Links:[/b]"]
            parts += [
                f'  • [link="{link.url}"]{escape(link.title)}[/link]  [dim]{escape(link.url)}[/dim]'
                for link in r.links
            ]
        self.query_one("#detail-text", Static).update("\n".join(parts))

    def action_next_filter(self) -> None:
        self.filter_index = (self.filter_index + 1) % len(FILTERS)
        self._render_score()
        self._refresh_table()

    def action_search(self) -> None:
        search = self.query_one("#search", Input)
        search.add_class("visible")
        search.can_focus = True
        search.focus()

    def action_clear_search(self) -> None:
        search = self.query_one("#search", Input)
        search.value = ""
        search.remove_class("visible")
        search.can_focus = False
        self.search_text = ""
        self._render_score()
        self._refresh_table()
        self.query_one(DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.search_text = event.value
        if self.results:
            self._render_score()
            self._refresh_table()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.query_one(DataTable).focus()

    def action_export(self) -> None:
        if not self.results:
            self.notify("Still checking — try again in a moment.")
            return
        path = Path(self.markdown_path)
        path.write_text(report.markdown(self.results), encoding="utf-8")
        self.notify(f"Saved {path.resolve()}", title="Report saved")
