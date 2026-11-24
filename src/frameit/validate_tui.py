"""Optional, read-only terminal view of the existing validation report."""

from asyncio import CancelledError
from collections import Counter
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from shlex import join
from textwrap import indent
from time import monotonic

import yaml
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.content import Content
from textual.message import Message
from textual.theme import Theme
from textual.widgets import Footer, Header, OptionList, Static, TabbedContent, TabPane
from textual.worker import Worker, WorkerState, get_current_worker

from frameit.core.reports import project_report

_STAGES = {
    "configuration": "Reading configuration",
    "metadata": "Checking input metadata",
    "binding": "Checking selected fields and methods",
    "plan": "Checking planned outputs and resources",
    "report": "Preparing validation report",
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
    return f"{time['label']} ({time['calendar']})" if isinstance(time, dict) else str(time)


def _run_command(config, overrides):
    args = ["frameit", "run"]
    for key, value in overrides.items():
        if key == "overwrite":
            args.append("--overwrite" if value else "--no-overwrite")
        else:
            args.append(f"--{key.replace('_', '-')}={value}")
    if str(config).startswith("-"):
        args.append("--")
    return join([*args, str(config)])


def _overview(report, config, schema_only, overrides):
    configuration, plan = (report["data"][key] for key in ("configuration", "plan"))
    confirmed = report["status"] == "ok" and not schema_only
    lines = [f"Configuration: {config}", ""]
    if configuration is None:
        lines.append("Configured request: unavailable")
    else:
        lines.append("Resolved request" if confirmed else "Configured request (not fully checked)")
        for name, declared in configuration["sources"].items():
            source = plan.get("sources", {}).get(name, {})
            model = source.get("model") or declared.get("model") or "model not established"
            lines.append(f"  {name} ({model})")
            fields = dict.fromkeys(
                field for product in plan.get("products", ()) if product["source"] == name
                for field in product["fields"])
            if fields:
                label = "Selected output fields" if confirmed else "Requested output fields"
                lines.append(f"    {label}: {', '.join(fields)}")
            elif declared.get("variables"):
                lines.append("    Configured field selectors:")
                lines.append(indent(_yaml(declared["variables"]), "      "))
            if times := source.get("selected_times"):
                first, last = _time_label(times[0]), _time_label(times[-1])
                span = first if len(times) == 1 else f"{first} to {last}"
                lines.append(f"    {len(times)} selected times: {span}")
            else:
                lines.append("    Selected times: unavailable")
        region = {key: value for key, value in configuration["region"].items()
                  if key != "sources_coupling_time_association"}
        lines.append("  Region / tracking:\n" + indent(_yaml(region), "    ")
                     if region else "  Region: full domain")

    if paths := plan.get("planned_products"):
        label = "Planned outputs (not written)" if confirmed else "Unconfirmed output paths"
        lines.extend(("", label))
        lines.extend(f"  {path}" for path in paths)
    else:
        lines.extend(("", "Planned outputs: unavailable"))

    if report["errors"]:
        error = report["errors"][0]
        lines.extend(("", f"First repair · [{error['code']}] {error['path']}",
                      *error["repairs"]))
    elif schema_only:
        lines.extend(("", "Next: input-aware validation. Inputs were not checked."))
    else:
        if report["warnings"]:
            lines.extend(("", "Review warnings in Findings before running."))
        lines.extend(("", f"Next: {_run_command(config, overrides)}"))
    lines.extend(("", "Execution and scientific validity were not checked."))
    return "\n".join(lines)


def _finding_title(level, item):
    if level == "Warning":
        return f"Warning {item}"
    code = f" [{item['code']}]" if level == "Error" else ""
    return f"{level}{code} · {item['path']}"


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


class ValidationApp(App[int]):
    TITLE = "FrameIt · Validate (experimental)"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("1", "view('overview')", "Overview"),
        Binding("2", "view('findings')", "Findings"),
        Binding("3", "view('details')", "Details"),
        Binding("r", "revalidate", "Revalidate"),
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "interrupt", show=False, priority=True),
    ]
    CSS = f"""
    Screen, Header, Footer {{ background: $background; color: $foreground; }}
    #context, #status {{ height: auto; padding: 0 1; }}
    #context {{ color: {_SLATE}; text-wrap: nowrap; text-overflow: ellipsis; }}
    #status {{ text-style: bold; }}
    #status.progress {{ color: $accent; }}
    #status.error {{ color: $error; }}
    #status.warning {{ color: $warning; }}
    TabbedContent, TabPane, VerticalScroll {{ height: 1fr; }}
    TabPane {{ padding: 0 1; }}
    VerticalScroll:focus {{ scrollbar-color: $accent; }}
    #finding-list {{ height: 2fr; min-height: 3; }}
    #finding-scroll {{ height: 3fr; }}
    """

    def __init__(self, config: Path, collect, *, schema_only=False, overrides=None):
        super().__init__()
        self.config = config
        self.collect = collect
        self.schema_only = schema_only
        self.overrides = overrides or {}
        self.result_code = None
        self.findings = []
        self.register_theme(_THEME)
        self.theme = _THEME.name

    def compose(self) -> ComposeResult:
        mode = "Schema only" if self.schema_only else "Input-aware"
        yield Header()
        yield Static(f"{self.config.name} · {mode}", id="context", markup=False)
        yield Static(id="status", markup=False)
        with TabbedContent(id="report-tabs"):
            with TabPane("Overview", id="overview"):
                with VerticalScroll(id="overview-scroll"):
                    yield Static(id="summary", markup=False)
            with TabPane("Findings", id="findings"):
                yield OptionList(id="finding-list", markup=False)
                with VerticalScroll(id="finding-scroll"):
                    yield Static(id="finding", markup=False)
            with TabPane("Details", id="details"):
                with VerticalScroll(id="details-scroll"):
                    yield Static(id="report-details", markup=False)
        yield Footer()

    def on_mount(self):
        self._start_check()
        self.set_interval(1, self._tick)

    def _start_check(self):
        self.result_code = None
        self._started = self._scan_started = monotonic()
        self._activity = _STAGES["configuration"]
        self.query_one("#report-tabs").display = False
        self.query_one("#status").set_classes("progress")
        self._tick()
        self.run_worker(self._validate, thread=True)

    def _validate(self):
        worker = get_current_worker()

        def progress(stage, source, checked, total):
            if worker.is_cancelled:
                raise CancelledError
            self.post_message(_Progress(stage, source, checked, total, monotonic()))

        result = self.collect(progress=progress)
        progress("report", None, None, None)
        report = project_report(result)
        data = report["data"]
        details = "\n\n".join(
            f"{label}\n{_yaml(data[key]) if data[key] else 'Unavailable'}"
            for label, key in (("Effective configuration", "configuration"),
                               ("Setting origins", "origins"), ("Processing plan", "plan"))
        )
        return report, details

    @on(_Progress)
    def _observe(self, event: _Progress):
        activity = _STAGES[event.stage]
        if event.source is not None:
            activity += f" · {event.source}"
        if event.checked is not None:
            activity += f" · {event.checked} of {event.total} files checked"
            if event.checked == 0:
                self._scan_started = event.at
            elif 2 <= event.checked < event.total:
                remaining = ceil((event.at - self._scan_started) *
                                 (event.total - event.checked) / event.checked)
                activity += f" · ETA ~{_clock(remaining)} (this source)"
        self._activity = activity
        self._tick()

    def _tick(self):
        if self.result_code is None:
            elapsed = _clock(monotonic() - self._started)
            self.query_one("#status", Static).update(f"{self._activity} · {elapsed} elapsed")

    def on_worker_state_changed(self, event: Worker.StateChanged):
        if event.state != WorkerState.SUCCESS:
            return
        report, details = event.worker.result
        self.result_code = int(bool(report["errors"]))
        checks = report["deferred_checks"]
        self.findings = [
            *(("Error", item) for item in report["errors"]),
            *(("Warning", item) for item in report["warnings"]),
            *(("Blocked", item) for item in checks if item["status"] == "blocked"),
            *(("Deferred", item) for item in checks if item["status"] != "blocked"),
        ]
        counts = Counter(level for level, _ in self.findings)
        verdict = ("Validation failed" if self.result_code else
                   "Schema checks passed" if self.schema_only else "Input-aware checks passed")
        stats = [f"{counts[level]} {level.lower()}{suffix}" for level, suffix in
                 (("Error", "s"), ("Warning", "s"), ("Blocked", ""), ("Deferred", ""))
                 if counts[level]]
        status = self.query_one("#status", Static)
        status.set_classes("error" if self.result_code else "warning" if counts["Warning"] else "")
        status.update(" · ".join([verdict, *stats]))

        self.query_one("#summary", Static).update(
            _overview(report, self.config, self.schema_only, self.overrides))
        self.query_one("#report-details", Static).update(details)
        listing = self.query_one("#finding-list", OptionList)
        listing.clear_options().add_options(
            Content.styled(_finding_title(level, item), {
                "Error": f"bold {_RED}", "Warning": _AMBER, "Blocked": _SLATE, "Deferred": _SLATE,
            }[level])
            for level, item in self.findings)
        listing.highlighted = 0 if self.findings else None
        first = _finding_detail(*self.findings[0]) if self.findings else "No findings."
        self.query_one("#finding", Static).update(first)
        self.query_one("#report-tabs").display = True
        for scroll in self.query(VerticalScroll):
            scroll.scroll_home(animate=False)
        self.action_view("overview")

    @on(OptionList.OptionHighlighted)
    def _select_finding(self, event: OptionList.OptionHighlighted):
        if self.result_code is not None and event.option_index < len(self.findings):
            self.query_one("#finding", Static).update(
                _finding_detail(*self.findings[event.option_index]))
            self.query_one("#finding-scroll").scroll_home(animate=False)

    def action_view(self, view):
        if self.result_code is not None:
            self.query_one("#report-tabs", TabbedContent).active = view
            target = "#finding-list" if view == "findings" else f"#{view}-scroll"
            self.query_one(target).focus()

    def action_revalidate(self):
        if self.result_code is not None:
            self._start_check()

    def action_quit(self):
        if self.result_code is not None:
            self.exit(self.result_code)

    def action_interrupt(self):
        self.exit(130)
