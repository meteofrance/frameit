"""Read-only terminal view of the validation report."""

from asyncio import CancelledError
from collections import Counter
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from shlex import join
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
from textual.widgets import Collapsible, Footer, OptionList, Static, TabbedContent, TabPane
from textual.worker import Worker, WorkerState, get_current_worker

from frameit.core.reports import project_report

_STAGES = {
    "configuration": "Reading configuration",
    "metadata": "Checking input metadata",
    "binding": "Checking selected fields and methods",
    "plan": "Checking planned outputs and resources",
    "report": "Preparing validation report",
}
_CHECK_LABELS = {
    "unfinished-selection": "Field discovery",
    "execution-dependent": "During run",
    "schema-only": "Not checked in schema mode",
}
_DETAIL_LABELS = {
    "configuration": "Effective configuration",
    "origins": "Setting origins",
    "plan": "Processing plan",
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


def _count(count, label):
    return f"{count} {label}{'s' if count != 1 else ''}"


def _region_label(region, sources, *, model_grid):
    if sources and all("region.center" in source.get("region", {}).get("unused_settings", ())
                       for source in sources.values()):
        return "Full domain; configured centre unused"
    if tracker := region.get("tracker"):
        mode = f"Tracker: {tracker['method']}"
    elif "track" in region:
        mode = "Prescribed track"
    elif "center" in region:
        mode = "Fixed centre"
    else:
        return "Full domain"
    width = region.get("width_km") if model_grid else None
    return f"{mode} · {width['x']:g} × {width['y']:g} km crop requested" if width else mode


def _overview(report, config, schema_only, overrides, *, has_warnings):
    data = report["data"]
    configuration, plan = data["configuration"], data["plan"]
    prepared = plan.get("sources", {})
    confirmed = report["status"] == "ok" and not schema_only
    lines = []
    if report["errors"]:
        error = report["errors"][0]
        lines.extend((f"Fix first · [{error['code']}] {error['path']}", *error["repairs"], ""))

    unavailable = "Not confirmed" if configuration else "Unavailable"
    inputs = "Not checked (schema only)" if schema_only else unavailable
    selection, region, outputs = unavailable, unavailable, "Unavailable"
    time_rows = []
    if confirmed:
        source_labels = []
        for name, declared in configuration["sources"].items():
            source = prepared.get(name, {})
            model = source.get("model") or declared.get("model")
            source_labels.append(f"{name} ({model})" if model else name)
            if times := source.get("selected_times"):
                first, last = _time_label(times[0]), _time_label(times[-1])
                span = first if len(times) == 1 else f"{first} → {last}"
                prefix = f"{name}: " if len(configuration["sources"]) > 1 else ""
                time_rows.append(f"{prefix}{_count(len(times), 'source time')} selected · {span}")
                if associations := source.get("region", {}).get("associations"):
                    matched = len({_time_label(entry["source_time"]) for entry in associations})
                    if matched < len(times):
                        time_rows.append(
                            f"{prefix}{_count(matched, 'source time')} matched to centres")
        if data["inputs"]:
            inputs = " · ".join([f"{_count(len(data['inputs']), 'file')} scanned", *source_labels])
        fields = Counter()
        for product in plan.get("products", ()):
            if product["product"] != "track":
                fields[product["product"].replace("_", "-")] += len(product["fields"])
        selection = " · ".join(_count(n, f"{kind} output field") for kind, n in fields.items() if n)
        region = _region_label(configuration["region"], prepared,
                               model_grid=bool(fields["model-grid"]))
        if paths := plan.get("planned_products"):
            kinds = dict.fromkeys(product["product"].replace("_", " ")
                                  for product in plan.get("products", ()))
            outputs = f"{len(paths)} planned" + (f" · {', '.join(kinds)}" if kinds else "")
    elif plan.get("planned_products"):
        outputs = "Unconfirmed output paths in Details"

    lines.append(f"{'Inputs':<11}{inputs}")
    selection_rows = [row for row in [selection, *time_rows] if row] or ["Unavailable"]
    lines.append(f"{'Selection':<11}{selection_rows[0]}")
    lines.extend(f"{'':<11}{row}" for row in selection_rows[1:])
    lines.extend((f"{'Region':<11}{region}", f"{'Outputs':<11}{outputs}"))
    if not report["errors"]:
        if schema_only:
            lines.extend(("", "Next: validate without --schema-only."))
        else:
            if has_warnings:
                lines.extend(("", "See warnings in Findings."))
            lines.extend(("", f"Next: {_run_command(config, overrides)}"))
    return "\n".join(lines)


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


class ValidationApp(App[int]):
    TITLE = "FrameIt / validate"
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
    #status {{ height: auto; margin: 1 1 0 1; padding: 0 1; text-style: bold;
        border-left: tall $accent; }}
    #status.progress {{ color: $accent; }}
    #status.error {{ color: $error; border-left: tall $error; }}
    #status.warning {{ color: $warning; border-left: tall $warning; }}
    #interrupt-hint {{ display: none; dock: bottom; padding: 0 1; }}
    Screen.checking #interrupt-hint {{ display: block; }}
    Screen.checking #report-tabs, Screen.checking Footer {{ display: none; }}
    TabbedContent, TabPane, VerticalScroll {{ height: 1fr; }}
    TabPane {{ padding: 0 1; }}
    #summary, #details-scroll {{ padding-top: 1; }}
    VerticalScroll:focus {{ scrollbar-color: $accent; }}
    #finding-list {{ height: 2fr; min-height: 3; }}
    #finding-list:focus > .option-list--option-highlighted,
    #details-scroll CollapsibleTitle:focus {{
        background: #102440;
        color: $foreground;
        text-style: bold underline;
    }}
    #finding-scroll {{ height: 3fr; }}
    #details-scroll {{ overflow-x: auto; }}
    #details-scroll Collapsible {{
        width: auto;
        min-width: 100%;
        border: none;
        padding: 0 0 1 0;
    }}
    #details-scroll Contents, #details-scroll Contents Static {{ width: auto; }}
    #details-scroll Contents Static {{ text-wrap: nowrap; }}
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
        with Horizontal(id="identity-bar"):
            yield Static(self.TITLE, id="identity", markup=False)
            yield Static(self.config.name, id="context", markup=False)
        yield Static(id="status", markup=False)
        with TabbedContent(id="report-tabs"):
            with TabPane("Overview", id="overview"):
                with VerticalScroll(id="overview-scroll"):
                    yield Static(id="summary", markup=False)
            with TabPane("Findings", id="findings"):
                yield OptionList(id="finding-list", markup=False, compact=True)
                with VerticalScroll(id="finding-scroll"):
                    yield Static(id="finding", markup=False)
            with TabPane("Details", id="details"):
                with VerticalScroll(id="details-scroll"):
                    for key, label in _DETAIL_LABELS.items():
                        yield Collapsible(
                            Static(id=f"detail-{key}-text", markup=False),
                            title=label, id=f"detail-{key}",
                            collapsed_symbol="›", expanded_symbol="⌄",
                        )
        yield Static(Content.assemble(("Ctrl+C", f"bold {_TEAL}"), " Interrupt"),
                     id="interrupt-hint")
        yield Footer(compact=True)

    def on_mount(self):
        self.begin_capture_print(self, stdout=False)
        self._start_check()
        self.set_interval(1, self._tick)

    def _start_check(self):
        self.result_code = None
        self._started = self._scan_started = monotonic()
        self._eta_at = None
        self._runtime_warnings = []
        self._activity = _STAGES["configuration"]
        self.screen.add_class("checking")
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
        details = {key: _yaml(data[key]) if data[key] else "Unavailable" for key in _DETAIL_LABELS}
        return report, details

    def on_print(self, event: events.Print):
        if self.result_code is None and event.stderr:
            level, _, message = event.text.rstrip().partition(":")
            if level == "WARNING" and message:
                detail = message.partition(":")[2] or message
                self._runtime_warnings.append(f"(validation log) {detail}")

    @on(_Progress)
    def _observe(self, event: _Progress):
        activity = _STAGES[event.stage]
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
        report, details = event.worker.result
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
        counts = Counter(level for level, _ in self.findings)
        verdict = ("Validation failed" if self.result_code else
                   "Schema checks passed" if self.schema_only else "Validation passed")
        labels = (("Error", "error"), ("Warning", "warning"), ("Blocked", "blocked"),
                  ("Field discovery", "field discovery note"))
        stats = [f"{count} {label}{'s' if count > 1 and level != 'Blocked' else ''}"
                 for level, label in labels if (count := counts[level])]
        status = self.query_one("#status", Static)
        status.set_classes("error" if self.result_code else "warning" if counts["Warning"] else "")
        status.update(" · ".join([verdict, *stats]))

        self.query_one("#summary", Static).update(
            _overview(report, self.config, self.schema_only, self.overrides,
                      has_warnings=bool(warnings)))
        plan_title = _DETAIL_LABELS["plan"]
        if self.result_code:
            plan_title = "Partial plan"
            if report["data"]["plan"].get("planned_products"):
                plan_title += " · unconfirmed paths"
        for key, text in details.items():
            section = self.query_one(f"#detail-{key}", Collapsible)
            section.title = plan_title if key == "plan" else _DETAIL_LABELS[key]
            section.collapsed = True
            self.query_one(f"#detail-{key}-text", Static).update(text)
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
