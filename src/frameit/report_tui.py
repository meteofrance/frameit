"""Shared terminal lifecycle and diagnostic presentation for FrameIt reports."""

from asyncio import CancelledError
from collections import Counter
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from textwrap import indent
from time import monotonic

import yaml
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.content import Content
from textual.message import Message
from textual.theme import Theme
from textual.widgets import Footer, OptionList, Static
from textual.worker import Worker, WorkerState, get_current_worker

from frameit.core.reports import project_report

_CHECK_LABELS = {
    "unfinished-selection": "Field discovery",
    "execution-dependent": "During run",
    "schema-only": "Not checked in schema mode",
}
_TEAL, _AMBER, _RED, _SLATE = "#49C5BC", "#F5B55E", "#DA5656", "#A6B4C4"
_THEME = Theme(
    name="frameit", primary=_TEAL, accent=_TEAL, warning=_AMBER, error=_RED,
    background="#021633", surface="#021633", panel="#021633", foreground="#E6EDF3",
)


def _yaml(value):
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True).rstrip()


def _clock(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"


def _time_label(time):
    if isinstance(time, dict):
        return f"{time['label']} ({time['calendar']})"
    return str(time).removesuffix(".000000000")


def _finding_title(level, item):
    if level == "Warning":
        return f"Warning {item}"
    code = f" [{item['code']}]" if level == "Error" else ""
    title = f"{level}{code} · {item['path']}"
    if level == "Field discovery":
        field, separator, _ = item["message"].partition(":")
        if separator:
            title += f" · {field}"
    return title


def _finding_detail(level, item):
    lines = [_finding_title(level, item)]
    if level != "Warning":
        lines.extend(("", item["message"]))
        if level == "Error":
            sections = (("Repair", "repairs"), ("Expected", "expected"), ("Observed", "observed"),
                        ("Affected", "contexts"))
            lines.extend(f"\n{label}:\n{indent(_yaml(item[key]), '  ')}"
                         for label, key in sections if item[key] is not None and item[key] != [])
            lines.extend(f"\nYAML: {mark['file']}:{mark['line']}:{mark['column']}"
                         for mark in item["locations"])
            lines.append(f"\nTroubleshooting: {item['help']}")
        elif item.get("prerequisites"):
            lines.append("\nPrerequisites: " + ", ".join(item["prerequisites"]))
    return "\n".join(lines)


@dataclass
class _Progress(Message):
    stage: str
    source: str | None
    checked: int | None
    total: int | None
    at: float


class ReportApp(App[int]):
    ENABLE_COMMAND_PALETTE = False
    LOG_CONTEXT = "report"
    STAGES = {
        "configuration": "Reading configuration",
        "metadata": "Checking input metadata",
        "report": "Preparing report",
    }
    BINDINGS = [
        Binding("ctrl+c", "interrupt", show=False, priority=True),
    ]
    CSS = f"""
    Screen, Footer {{ background: $background; color: $foreground; }}
    #identity-bar {{ height: 1; padding: 0 1; }}
    #identity {{ width: auto; text-style: bold; }}
    #context {{
        width: 1fr;
        padding-left: 1;
        text-align: right;
        text-wrap: nowrap;
        text-overflow: ellipsis;
        color: {_SLATE};
    }}
    #status {{ height: auto; margin: 1 1 0 1; text-style: bold; }}
    #status.progress {{ color: $accent; }}
    #status.error {{ color: $error; }}
    #status.warning {{ color: $warning; }}
    #interrupt-hint {{ display: none; dock: bottom; padding: 0 1; }}
    Screen.checking #interrupt-hint {{ display: block; }}
    Screen.checking .report-body, Screen.checking Footer {{ display: none; }}
    TabbedContent, TabPane, VerticalScroll {{ height: 1fr; }}
    TabPane {{ padding: 0 1; }}
    VerticalScroll, OptionList, DataTable {{
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
        scrollbar-color: $accent 55%;
        scrollbar-color-hover: $accent 78%;
        scrollbar-color-active: $accent;
        scrollbar-background: transparent;
        scrollbar-background-hover: transparent;
        scrollbar-background-active: transparent;
        scrollbar-corner-color: $background; /* Textual renders the corner opaque. */
    }}
    /* Set both axes so Textual counts the vertical gutter when sizing the horizontal thumb. */
    DataTable, #details-scroll {{ overflow: scroll; }}
    #sources {{ scrollbar-size: 0 0; }}
    #finding-list {{ height: 2fr; min-height: 3; }}
    #finding-list:focus > .option-list--option-highlighted {{
        background: #102440;
        color: $foreground;
        text-style: bold underline;
    }}
    #finding-scroll {{ height: 3fr; }}
    """

    def __init__(self, config: Path, collect):
        super().__init__()
        self.config = config
        self.collect = collect
        self.result_code = None
        self.findings = []
        self.register_theme(_THEME)
        self.theme = _THEME.name

    def compose(self) -> ComposeResult:
        with Horizontal(id="identity-bar"):
            yield Static(self.TITLE, id="identity", markup=False)
            yield Static(self.config.name, id="context", markup=False)
        yield Static(id="status", markup=False)
        yield from self.compose_view()
        yield Static(Content.assemble(("Ctrl+C", f"bold {_TEAL}"), " Interrupt"),
                     id="interrupt-hint")
        yield Footer(compact=True)

    def compose_view(self) -> ComposeResult:
        raise NotImplementedError

    def compose_findings(self) -> ComposeResult:
        yield OptionList(id="finding-list", markup=False, compact=True)
        with VerticalScroll(id="finding-scroll"):
            yield Static(id="finding", markup=False)

    def on_mount(self):
        self.begin_capture_print(self, stdout=False)
        self._start_check()
        self.set_interval(1, self._tick)

    def _start_check(self):
        self.result_code = None
        self._started = self._scan_started = monotonic()
        self._eta_at = None
        self._runtime_warnings = []
        self._activity = self.STAGES["configuration"]
        self.screen.add_class("checking")
        self.query_one("#status").set_classes("progress")
        self._tick()
        self.run_worker(self._collect, thread=True)

    def _collect(self):
        worker = get_current_worker()

        def progress(stage, source, checked, total):
            if worker.is_cancelled:
                raise CancelledError
            self.post_message(_Progress(stage, source, checked, total, monotonic()))

        result = self.collect(progress=progress)
        progress("report", None, None, None)
        report = project_report(result)
        return report, self.prepare_view(report)

    def prepare_view(self, report: dict):
        return None

    def on_print(self, event: events.Print):
        if self.result_code is None and event.stderr:
            level, _, message = event.text.rstrip().partition(":")
            if level == "WARNING" and message:
                detail = message.partition(":")[2] or message
                self._runtime_warnings.append(f"({self.LOG_CONTEXT} log) {detail}")

    @on(_Progress)
    def _observe(self, event: _Progress):
        activity = self.STAGES[event.stage]
        self._eta_at = None
        if event.source is not None:
            activity += f" · {event.source}"
        if event.checked is not None:
            activity += f" · {event.checked} of {event.total} files checked"
            if event.checked == 0:
                self._scan_started = event.at
            elif 2 <= event.checked < event.total:
                self._eta_at = event.at + ((event.at - self._scan_started) *
                                           (event.total - event.checked) / event.checked)
        self._activity = activity
        self._tick()

    def _tick(self):
        if self.result_code is None:
            now = monotonic()
            activity = self._activity
            if self._eta_at is not None and now < self._eta_at:
                activity += f" · ETA ~{_clock(ceil(self._eta_at - now))} (this source)"
            elapsed = _clock(now - self._started)
            self.query_one("#status", Static).update(f"{activity} · {elapsed} elapsed")

    def on_worker_state_changed(self, event: Worker.StateChanged):
        if event.state != WorkerState.SUCCESS:
            return
        report, prepared = event.worker.result
        self.result_code = int(bool(report["errors"]))
        checks = report["deferred_checks"]
        warnings = dict.fromkeys([*report["warnings"], *self._runtime_warnings])
        self.findings = [
            *(("Error", item) for item in report["errors"]),
            *(("Warning", item) for item in warnings),
            *(("Blocked", item) for item in checks if item["status"] == "blocked"),
            *((_CHECK_LABELS.get(item["status"], "Not checked here"), item)
              for item in checks if item["status"] != "blocked"),
        ]
        listing = self.query_one("#finding-list", OptionList)
        listing.clear_options().add_options(
            Content.styled(f"{index:>2}  {_finding_title(level, item)}", {
                "Error": f"bold {_RED}", "Warning": _AMBER,
            }.get(level, _SLATE))
            for index, (level, item) in enumerate(self.findings, start=1))
        listing.highlighted = 0 if self.findings else None
        first = _finding_detail(*self.findings[0]) if self.findings else "No findings."
        self.query_one("#finding", Static).update(first)
        self.screen.remove_class("checking")
        for scroll in self.query(VerticalScroll):
            scroll.scroll_home(animate=False)
        self.show_report(report, prepared)

    def show_report(self, report: dict, prepared) -> None:
        raise NotImplementedError

    def set_status(self, verdict):
        counts = Counter(level for level, _ in self.findings)
        labels = (("Error", "error"), ("Warning", "warning"), ("Blocked", "blocked"),
                  ("Field discovery", "field discovery note"))
        stats = [f"{count} {label}{'s' if count > 1 and level != 'Blocked' else ''}"
                 for level, label in labels if (count := counts[level])]
        status = self.query_one("#status", Static)
        status.set_classes("error" if self.result_code else "warning" if counts["Warning"] else "")
        status.update(" · ".join([verdict, *stats]))

    @on(OptionList.OptionHighlighted, "#finding-list")
    def _select_finding(self, event: OptionList.OptionHighlighted):
        if self.result_code is not None and event.option_index < len(self.findings):
            self.query_one("#finding", Static).update(
                _finding_detail(*self.findings[event.option_index]))
            self.query_one("#finding-scroll").scroll_home(animate=False)

    def action_refresh(self) -> None:
        if self.result_code is not None:
            self._start_check()

    def action_quit(self):
        if self.result_code is not None:
            self.exit(self.result_code)

    def action_interrupt(self):
        self.exit(130)
