"""Shared terminal lifecycle and diagnostic presentation for FrameIt reports."""

from asyncio import CancelledError
from collections import Counter
from dataclasses import dataclass
from math import ceil
from os import environ
from pathlib import Path
from sys import __stdout__
from tempfile import NamedTemporaryFile
from textwrap import indent
from threading import Event
from time import monotonic, time

import yaml
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.css.scalar import Scalar
from textual.message import Message
from textual.notifications import Notify
from textual.screen import ModalScreen
from textual.scrollbar import ScrollBarRender
from textual.theme import Theme
from textual.widgets import Collapsible, Footer, Input, OptionList, ProgressBar, Static
from textual.worker import Worker, WorkerState, get_current_worker

from frameit.core.reports import serialize_projection
from frameit.report_check import ReportProcess, collect_projection
from frameit.report_diff import finding_key
from frameit.report_motion import BrandActivity, ReportScroll

_CHECK_LABELS = {
    "unfinished-selection": "Field discovery",
    "execution-dependent": "During run",
    "schema-only": "Not checked in schema mode",
}
_THEME = Theme(
    name="frameit", primary="#4CC7C2", accent="#4CC7C2", warning="#F2AE3D",
    success="#78C6A3", error="#F08080", foreground="#E6EDF3",
    background="#000000", surface="#000000", panel="#000000",
    variables={"text-muted": "#A5B0BD", "report-selection": "#0B2B29", "report-rule": "#33464D"},
)
_FINDING_STYLES = {"Error": "bold $error", "Warning": "$warning", "Blocked": "$text-muted"}


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


def _finding_summary(level, item):
    if level == "Warning":
        return Content.styled("Warning", "bold $warning") + Content(f"\n{item}")
    if level != "Error":
        lines = [_finding_title(level, item), "", item["message"]]
        if item.get("prerequisites"):
            lines.append("\nPrerequisites: " + ", ".join(item["prerequisites"]))
        return Content("\n".join(lines))
    title = _finding_title(level, item)
    message = item["message"].split("\n", 1)[0]
    observed = item["observed"]
    if item["code"] == "E1201" and isinstance(observed, dict) and "files" in observed:
        title = "No input files match\n" + title
        message = "A file pattern or path did not select a required input."
    elif len(message) > 160:
        message = message[:157] + "…"
    summary = Content.styled(title, "bold $error") + Content(f"\n\n{message}")
    if repairs := item["repairs"]:
        summary += Content.styled("\n\nRepair: ", "bold $accent") + Content("\n".join(repairs))
    if marks := item["locations"]:
        mark = marks[0]
        label = f"{Path(mark['file']).name}:{mark['line']}:{mark['column']}"
        more = f" (+{len(marks) - 1} more)" if len(marks) > 1 else ""
        summary += Content.styled(f"\n\nLocation: {label}{more}", "$text-muted")
    return summary


def _finding_evidence(item):
    lines = [f"Setting: {item['path']}", item["message"]]
    sections = (("Expected", "expected"), ("Observed", "observed"), ("Affected", "contexts"))
    lines.extend(f"\n{label}:\n{indent(_yaml(item[key]), '  ')}"
                 for label, key in sections if item[key] is not None and item[key] != [])
    lines.extend(f"\nYAML: {mark['file']}:{mark['line']}:{mark['column']}"
                 for mark in item["locations"])
    lines.append(f"\nTroubleshooting: {item['help']}")
    return "\n".join(lines)


class _ReportHelp(ModalScreen):
    BINDINGS = [
        Binding("escape,question_mark", "dismiss", "Close help", show=False),
    ]
    DEFAULT_CSS = """
    _ReportHelp { align: center middle; background: $background; }
    _ReportHelp ReportScroll { width: 62; max-width: 100%; height: auto; max-height: 90%;
                               background: $background; padding: 1 2; }
    """

    def __init__(self, bindings):
        super().__init__()
        keys = {"escape": "Esc", "slash": "/", "question_mark": "?", "ctrl+c": "Ctrl+C"}
        self._text = "\n".join([
            "FrameIt shortcuts · Esc to close", "", "Tab / Shift+Tab  Move focus",
            "Enter  Open selection or toggle section", "Page Up / Down  Scroll details", "",
            *(f"{keys.get(binding.key, binding.key):<8} {binding.description}"
              for binding in bindings),
        ])

    def compose(self) -> ComposeResult:
        with ReportScroll():
            yield Static(self._text, id="report-help", markup=False)


class EvidenceChoices(ModalScreen):
    """Pick a report reference without leaving the current reading position."""

    BINDINGS = [Binding("escape", "dismiss", "Back", show=False)]
    DEFAULT_CSS = """
    EvidenceChoices { align: center middle; background: $background; }
    EvidenceChoices Vertical { width: 76; max-width: 100%; height: 80%; padding: 1 2; }
    EvidenceChoices OptionList { height: 1fr; }
    """

    def __init__(self, title, choices):
        super().__init__()
        self._title = title
        self._choices = choices

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"{self._title} · Enter open · Esc back", markup=False)
            yield OptionList(*(label for label, _ in self._choices),
                             id="related-options", markup=False, compact=True)

    @on(OptionList.OptionSelected, "#related-options")
    def _open_reference(self, event):
        self.dismiss(self._choices[event.option_index][1])


class _SaveReport(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Cancel", show=False)]
    DEFAULT_CSS = """
    _SaveReport { align: center middle; background: $background; }
    _SaveReport Vertical { width: 66; max-width: 100%; height: auto; padding: 1 2; }
    #export-error { color: $error; }
    """

    def __init__(self, label, save):
        super().__init__()
        self._label = label
        self._save = save

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Save current report · {self._label}", markup=False)
            yield Static("Choose a new JSON path. Enter saves; Esc cancels. No files are replaced.",
                         markup=False)
            yield Input(placeholder="Path for the JSON report", id="export-path")
            yield Static(id="export-error", markup=False)

    @on(Input.Submitted, "#export-path")
    def _save_to_path(self, event):
        error = self.query_one("#export-error", Static)
        if not event.value.strip():
            error.update("Enter a destination path.")
            return
        try:
            path = Path(event.value).expanduser().absolute()
            self._save(path)
        except FileExistsError:
            error.update("Destination already exists. Choose a new path.")
        except (OSError, ValueError, RuntimeError) as exc:
            error.update(f"Cannot save report: {exc}")
        else:
            self.dismiss(path)


class DisclosureScroll(ReportScroll):
    """Keep the currently scrolled disclosure operable inside its own viewport."""

    _pinned: Collapsible | None = None

    def on_mount(self):
        for attribute in ("scroll_y", "virtual_size"):
            self.watch(self, attribute, self.update_heading, init=False)

    @on(Collapsible.Toggled)
    def update_heading(self):
        self.call_after_refresh(self._pin_heading)

    def _pin_heading(self):
        top = self.scroll_offset.y
        self._pinned = next((section for section in self.query(Collapsible)
                             if not section.collapsed
                             and section.virtual_region.y < top < section.virtual_region.bottom),
                            None)
        pinned = self.query_one(".pinned-heading", Static)
        label = self._pinned.title if self._pinned is not None else ""
        if pinned.content != label:
            pinned.update(label, layout=False)
            pinned.set_class(bool(label), "clickable")

    @on(events.Click, ".pinned-heading")
    def _collapse_pinned(self):
        if not self.app.busy and (section := self._pinned) is not None and not section.collapsed:
            section.collapsed = True
            section.query_one("CollapsibleTitle").focus(scroll_visible=False)


@dataclass
class _Progress(Message):
    worker: Worker
    stage: str
    source: str | None
    checked: int | None
    total: int | None
    at: float


class _ThinThumb(ScrollBarRender):
    """Center the painted thumb without shrinking its mouse target."""

    def __rich_console__(self, console, options):
        from rich.segment import Segment
        from rich.style import Style

        paint = Style(bgcolor=console.get_style(self.style).bgcolor, reverse=False)
        glyph = "┃" if self.vertical else "━"
        for bar in super().__rich_console__(console, options):
            for cell in console.render(bar, options):
                # Only the native thumb has a foreground; keep its mouse action metadata.
                if cell.style is not None and cell.style.color is not None:
                    yield Segment(glyph * cell.cell_length, cell.style + paint, cell.control)
                else:
                    yield cell


class ReportApp(App[int]):
    ENABLE_COMMAND_PALETTE = False
    LOG_CONTEXT = "report"
    SIDEBAR = None
    BRANDED_REFRESH = False
    HORIZONTAL_BREAKPOINTS = [(0, "-compact"), (68, "-narrow"), (120, "-wide")]
    VERTICAL_BREAKPOINTS = [(0, "-tiny"), (10, "-low"), (20, "-short"), (30, "-tall")]
    STAGES = {
        "configuration": "Reading configuration",
        "discovery": "Discovering input files",
        "metadata": "Checking input metadata",
        "report": "Preparing report",
    }
    BINDINGS = [
        Binding("ctrl+c", "interrupt", show=False, priority=True),
        Binding("b", "toggle_sidebar", "Sidebar"),
        Binding("p", "copy_config_path", "Copy configuration path", show=False),
        Binding("escape", "back", "Back"),
        Binding("y", "copy_finding", "Copy evidence", show=False),
        Binding("n", "filter_notes", "Field discovery notes", show=False),
        Binding("question_mark", "report_help", "Help", show=False),
        Binding("w", "save_report", "Save current report as JSON", show=False),
    ]
    CSS = """
    Screen, Footer { background: $background; color: $foreground; }
    #identity-bar { height: 1; padding: 0 1; }
    #identity { width: auto; text-style: bold; }
    #help-key { width: auto; margin-left: 2; color: $accent; pointer: pointer; }
    #context {
        width: 1fr;
        padding-left: 1;
        text-align: right;
        text-wrap: nowrap;
        text-overflow: ellipsis;
        color: $text-muted;
    }
    #status { height: auto; margin: 1 1 0 1; }
    #status.progress { color: $accent; text-style: bold; }
    #operation-context { display: none; height: auto; margin: 0 1; color: $text-muted; }
    Screen.checking #operation-context { display: block; }
    #report-feedback, #feedback-copy { height: auto; }
    #feedback-copy { width: 1fr; }
    #brand-activity {
        display: none; width: 20; height: 10; margin-right: 2; text-wrap: nowrap;
    }
    Screen.starting #report-feedback { height: 1fr; align: center middle; }
    Screen.starting #feedback-copy {
        width: 1fr; max-width: 44; height: 10; align: left middle;
    }
    Screen.starting #status { margin: 0 1; }
    #work-progress, #local-activity { display: none; height: 1; margin: 0 1; }
    #local-activity { width: 12; }
    #work-progress Bar { width: 1fr; }
    #work-progress Bar > .bar--bar, #work-progress Bar > .bar--indeterminate {
        background: $report-rule;
    }
    #work-progress Bar > .bar--indeterminate { color: $accent 60%; }
    #work-progress Bar > .bar--complete { color: $accent; }
    Toast { width: 44; max-width: 100%; padding: 0 1; background: $report-selection; }
    Toast.-information { border-left: outer $accent; }
    Toast.-information .toast--title { color: $accent; }
    Toast.-warning { border-left: outer $warning; }
    Toast.-error { border-left: outer $error; }
    ToastRack { scrollbar-size: 0 0; }
    Screen.-compact Toast, Screen.-narrow Toast, Screen.-low Toast, Screen.-tiny Toast {
        width: 1fr; height: 1; margin: 0; text-wrap: nowrap; text-overflow: ellipsis;
    }
    #interrupt-hint { display: none; dock: bottom; padding: 0 1; }
    Screen.checking #interrupt-hint { display: block; }
    Screen.starting .report-body, Screen.empty .report-body, Screen.checking Footer {
        display: none;
    }
    TabbedContent, TabPane, VerticalScroll { height: 1fr; }
    TabPane { padding: 0 1; }
    VerticalScroll, OptionList, DataTable {
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
        scrollbar-color: $accent 55%;
        scrollbar-color-hover: $accent 78%;
        scrollbar-color-active: $accent;
        scrollbar-background: transparent;
        scrollbar-background-hover: transparent;
        scrollbar-background-active: transparent;
        scrollbar-corner-color: $background; /* Textual renders the corner opaque. */
    }
    /* Set both axes so Textual counts the vertical gutter when sizing the horizontal thumb. */
    DataTable, #details-scroll { overflow: scroll; }
    #sources { scrollbar-size: 0 0; }
    OptionList, DataTable { background: $background; background-tint: transparent;
                            border-left: outer $background; }
    OptionList:focus, DataTable:focus { border-left: outer $accent; }
    OptionList > .option-list--option-highlighted, DataTable > .datatable--cursor {
        background: $report-selection; color: $foreground; text-style: bold;
    }
    DataTable > .datatable--header { background-tint: transparent; color: $text-muted; }
    Collapsible:focus-within { background-tint: transparent; }
    CollapsibleTitle:focus { background: $report-selection; color: $accent; text-style: reverse; }
    .pinned-heading {
        dock: top; height: 1; padding: 0 1; color: $accent; text-style: bold;
        text-wrap: nowrap; text-overflow: ellipsis; background: $background;
    }
    .pinned-heading.clickable { pointer: pointer; }
    #findings-layout { height: 1fr; }
    #finding-filter { height: auto; color: $text-muted; }
    #finding-list, #finding-scroll { height: 1fr; }
    #finding-scroll { display: none; border-left: outer $background; padding-left: 1; }
    #finding-scroll:focus { border-left: outer $accent; }
    #findings-layout.reading-finding #finding-scroll { display: block; }
    #findings-layout.reading-finding #finding-list { display: none; }
    Screen.-wide.-tall #findings-layout { layout: horizontal; }
    Screen.-wide.-tall #findings-layout #finding-scroll { display: block; }
    Screen.-wide.-tall #finding-list {
        display: block; width: 32; margin-right: 1;
    }
    Screen.-wide.-tall #findings-layout.reading-finding #finding-list { display: block; }
    Screen.-wide.-tall #finding-list.sidebar-closed { display: none; }
    Screen.-wide.-tall #findings-layout.reading-finding #finding-list.sidebar-closed {
        display: none;
    }
    #finding-evidence { border: none; padding: 0; margin-top: 1; }
    #finding-actions { height: auto; color: $accent; margin-top: 1; }
    """

    def __init__(self, config: Path, collect, *, saved_report=None, isolate=False):
        super().__init__()
        self.config = config
        self.collect = collect
        self._reader = ReportProcess(collect) if isolate else None
        self._saved_projection = saved_report
        self.saved = saved_report is not None
        self.result_code = None
        self.findings = []
        self._findings_visible = []
        self._notes_only = False
        self._report = None
        self._worker = None
        self._runtime_warnings = []
        self._elapsed_timer = None
        self._notice_since = 0.0
        self._has_report = self._stale = False
        self._hidden_view = None
        self._cancel = Event()
        self._sidebar_closed = False
        self._sidebar_epoch = 0
        self._sidebar_focus = None
        self._sidebar_width = None
        self.register_theme(_THEME)
        self.theme = _THEME.name

    def compose(self) -> ComposeResult:
        with Horizontal(id="identity-bar"):
            yield Static(self.TITLE, id="identity", markup=False)
            context = Static(self.config.name, id="context", markup=False)
            if not self.saved:
                context.tooltip = "p · Copy configuration path"
            yield context
            yield Static("? Help", id="help-key", markup=False)
        with Horizontal(id="report-feedback"):
            yield BrandActivity(id="brand-activity")
            with Vertical(id="feedback-copy"):
                yield Static(id="status", markup=False)
                yield Static(id="operation-context", markup=False)
                yield ProgressBar(total=1, show_percentage=False, show_eta=False,
                                  id="work-progress")
                yield Static(id="local-activity", markup=False)
        yield from self.compose_view()
        yield Static("Ctrl+C  Cancel check", id="interrupt-hint", markup=False)
        yield Footer(compact=True)

    def compose_view(self) -> ComposeResult:
        raise NotImplementedError

    @on(events.Click, "#help-key")
    def action_report_help(self):
        if not self.busy:
            bindings = [*ReportApp.BINDINGS, *type(self).BINDINGS]
            if self.saved:
                live = {"refresh", "edit_config", "copy_config_path", "toggle_draft_field",
                        "view_draft", "copy_selector", "show_changes"}
                bindings = [binding for binding in bindings if binding.action not in live]
            self.push_screen(_ReportHelp(bindings))

    def compose_findings(self) -> ComposeResult:
        yield Static(id="finding-filter", markup=False)
        with Vertical(id="findings-layout"):
            yield OptionList(id="finding-list", markup=False, compact=True)
            with DisclosureScroll(id="finding-scroll"):
                yield Static(id="finding-sticky", classes="pinned-heading", markup=False)
                yield Static(id="finding", markup=False)
                yield Static(id="finding-actions", markup=False)
                yield Collapsible(Static(id="finding-evidence-text", markup=False),
                                  title="Technical evidence", id="finding-evidence")

    def run(self, *args, **kwargs):
        if self._reader is None:
            return super().run(*args, **kwargs)
        try:
            # The first spawn needs a real stderr FD, before Textual captures it.
            self._reader.start()
            return super().run(*args, **kwargs)
        finally:
            self._reader.close()

    def on_mount(self):
        for widget in self.query("VerticalScroll, OptionList, DataTable"):
            if widget.scrollbar_size_vertical:
                widget.vertical_scrollbar.renderer = _ThinThumb
        for widget in self.query("DataTable, #details-scroll"):
            widget.horizontal_scrollbar.renderer = _ThinThumb
        if self.saved:
            try:
                report = self._saved_projection
                self._accept_report(report, self.prepare_view(report))
            except (KeyError, TypeError, ValueError, AttributeError, IndexError, RecursionError):
                self.result_code = 1
                self._report = None
                self.screen.add_class("empty")
                self.query_one("#status", Static).update(Content.styled(
                    "Saved report could not be displayed: incomplete or invalid metadata. "
                    "Use a JSON reader to inspect the file. q Quit.", "$error"))
        else:
            self.begin_capture_print(self, stdout=False)
            self._start_check()

    def on_unmount(self):
        if self._reader is not None:
            self._reader.close()

    @property
    def busy(self):
        return self._worker is not None

    def _start_check(self):
        if self._has_report and self.BRANDED_REFRESH and self._hidden_view is None:
            self._hidden_view = self._view_state()
        if self.BRANDED_REFRESH:
            # Hiding is deferred until layout; buffered input must stop immediately.
            self.query_one(".report-body").disabled = True
            self.screen.set_focus(None, scroll_visible=False)
        self._notice_since = time()
        self._clear_notices()
        self._cancel.clear()
        self._started = self._scan_started = monotonic()
        self._eta_at = None
        self._checked, self._total = 0, None
        self._runtime_warnings = []
        self._activity = self.STAGES["configuration"]
        self._progress_context = ""
        self.screen.add_class("checking")
        self.screen.set_class(not self._has_report or self.BRANDED_REFRESH, "starting")
        self.query_one("#status").set_classes("progress")
        self._worker = self.run_worker(self._collect, thread=True, exit_on_error=False)
        self._elapsed_timer = self.set_interval(1, self._tick)
        self._sync_activity()
        self._tick()

    def _collect(self):
        worker = get_current_worker()

        def cancelled():
            return self._cancel.is_set() or worker.is_cancelled

        def notify(*args):
            self.post_message(_Progress(worker, *args))

        if self._reader is None:
            report = collect_projection(self.collect, notify, cancelled)
        else:
            report = self._reader.read(notify, cancelled, self._remember_warning)
        if cancelled():
            raise CancelledError
        prepared = self.prepare_view(report)
        if cancelled():
            raise CancelledError
        return report, prepared

    def _remember_warning(self, detail):
        self._runtime_warnings.append(f"({self.LOG_CONTEXT} log) {detail}")

    def prepare_view(self, report: dict):
        return None

    def on_print(self, event: events.Print):
        if self.busy and event.stderr:
            level, _, message = event.text.rstrip().partition(":")
            if level == "WARNING" and message:
                self._remember_warning(message.partition(":")[2] or message)

    @on(_Progress)
    def _observe(self, event: _Progress):
        if event.worker is not self._worker or self._cancel.is_set() or not self.is_running:
            return
        context = []
        self._eta_at = None
        if event.source is not None:
            context.append(str(event.source))
        if event.checked is not None:
            context.append(f"{event.checked} of {event.total} files checked")
            if event.checked == 0:
                self._scan_started = event.at
            elif 2 <= event.checked < event.total:
                self._eta_at = event.at + ((event.at - self._scan_started) *
                                           (event.total - event.checked) / event.checked)
        self._activity = self.STAGES[event.stage]
        self._progress_context = " · ".join(context)
        self._checked, self._total = event.checked or 0, event.total
        self._sync_activity()
        self._tick()

    def _tick(self):
        if self.busy and not self._cancel.is_set():
            now = monotonic()
            context = [self._progress_context]
            if self._eta_at is not None and now < self._eta_at:
                context.append(f"ETA ~{_clock(ceil(self._eta_at - now))} (this source)")
            context.append(f"{_clock(now - self._started)} elapsed")
            if self._has_report and not self.BRANDED_REFRESH:
                prefix = "Refreshing (previous report shown)\n"
            else:
                prefix = "Refreshing report\n" if self._has_report else ""
            self.query_one("#status", Static).update(prefix + self._activity)
            self.query_one("#operation-context", Static).update(" · ".join(filter(None, context)))

    async def on_resize(self, event: events.Resize):
        if self.busy:
            self._sync_activity(event.size)
        if self.SIDEBAR and self._has_report:
            sidebar = self.query_one(self.SIDEBAR[0])
            self._sidebar_epoch += 1
            await self.animator.stop_animation(sidebar.styles, "width", complete=False)
            self._settle_sidebar(sidebar, self._wide_sidebar(event.size))
            self.screen.refresh_bindings()

    def _sync_activity(self, size=None):
        active = self.busy and not self._cancel.is_set()
        size = self.size if size is None else size
        encoding = getattr(__stdout__, "encoding", None) or ""
        graphical = (not self.no_color and encoding.lower().replace("-", "") == "utf8"
                     and environ.get("TERM") not in {"ansi", "linux", "vt100"})
        motion = active and graphical and self.animation_level == "full"
        compact_refresh = self.BRANDED_REFRESH and self._has_report
        branded = (active and graphical and self.screen.has_class("starting")
                   and size.width >= (44 if compact_refresh else 68)
                   and size.height >= (14 if compact_refresh else 20))
        self.query_one(BrandActivity).set_active(branded)
        known = active and graphical and bool(self._total)
        bar = self.query_one("#work-progress", ProgressBar)
        bar.display = known or (motion and branded)
        if bar.display:
            bar.update(total=self._total if known else None, progress=self._checked)
        else:
            bar.update(total=1, progress=0)  # Stop the native indeterminate bar's timer.
        local = self.query_one("#local-activity", Static)
        local.display = local.loading = motion and not branded and not known

    def _stop_feedback(self):
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        self._sync_activity()

    def on_worker_state_changed(self, event: Worker.StateChanged):
        if not self.is_running or event.worker is not self._worker or event.state in {
                WorkerState.PENDING, WorkerState.RUNNING}:
            return
        self._worker = None
        self._stop_feedback()
        self.screen.remove_class("checking", "starting")
        if self.BRANDED_REFRESH:
            self.query_one(".report-body").disabled = False
        hidden_view = self._hidden_view
        if self._cancel.is_set() or event.state == WorkerState.CANCELLED:
            if hidden_view is None and not self.BRANDED_REFRESH:
                self.exit(130)
            else:
                self.result_code = 130
                self._stale = self._has_report
                self.screen.set_class(not self._has_report, "empty")
                status = self.query_one("#status", Static)
                status.set_classes("")
                if hidden_view is not None:
                    status.update(Content("Refresh cancelled · Previous report shown\n")
                                  + self._settled_status)
                    self.call_after_refresh(self._restore_hidden_view)
                else:
                    status.update("Check cancelled · no report yet. Press r to retry or q to quit.")
            return
        if event.state == WorkerState.ERROR:
            if self.result_code != 130:
                self.result_code = 1
            self._stale = self._has_report
            self.screen.set_class(not self._has_report, "empty")
            status = self.query_one("#status", Static)
            problem = " ".join(str(event.worker.error).split())
            verdict = "Refresh failed · previous report is stale" if self._stale else "Check failed"
            content = Content.styled(f"{verdict} · {problem}. Press r to retry.", "$error")
            if self._stale:
                content += Content("\n") + self._settled_status
            status.set_classes("")
            status.update(content)
            if hidden_view is not None:
                self.call_after_refresh(self._restore_hidden_view)
            return
        self._accept_report(*event.worker.result, hidden_view=hidden_view)

    def _accept_report(self, report, prepared, *, hidden_view=None):
        self._stale = False
        self.screen.remove_class("empty")
        focused, offsets = hidden_view or self._view_state()
        listing = self.query_one("#finding-list", OptionList)
        old_index = listing.highlighted
        previous = self._current_finding()
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
        previous_report, self._report = self._report, report
        retained = self._list_findings(previous)
        self.show_report(report, prepared, previous_report)
        self._has_report = True
        self.screen.refresh_bindings()
        offsets = [(widget, offset, anchor) for widget, offset, anchor in offsets
                   if (retained or widget.id != "finding-scroll")
                   and (listing.highlighted == old_index or widget is not listing)]
        if hidden_view is not None:
            self._hidden_view = focused, offsets
            self.call_after_refresh(self._restore_hidden_view)
        elif offsets and self.focused is focused:
            self.call_after_refresh(self._restore_view, None, offsets)

    def _view_state(self):
        offsets = [(widget, widget.scroll_offset, self._scroll_anchor(widget))
                   for widget in self.query("VerticalScroll, DataTable, OptionList")
                   if self._has_report and widget.is_on_screen]
        return self.focused, offsets

    def _scroll_anchor(self, widget):
        return None

    def _restore_hidden_view(self):
        # A quick retry can start before the report has redrawn.
        if not self.busy and self._hidden_view is not None:
            view, self._hidden_view = self._hidden_view, None
            self._restore_view(*view)

    def _restore_view(self, focused, offsets):
        if focused is not None and focused.is_on_screen:
            self.screen.set_focus(focused, scroll_visible=False)
        for widget, (x, y), anchor in offsets:
            if widget.is_on_screen and anchor == self._scroll_anchor(widget):
                widget.scroll_to(x=x, y=y, animate=False, immediate=self.BRANDED_REFRESH)

    def show_report(self, report: dict, prepared, previous_report) -> None:
        raise NotImplementedError

    def set_status(self, verdict, *, hint=None, passed=False):
        counts = Counter(level for level, _ in self.findings)
        labels = (("Error", "error"), ("Warning", "warning"), ("Blocked", "blocked"),
                  ("Field discovery", "field discovery note"))
        parts = [Content.styled("Saved report", "bold $text-muted")] if self.saved else []
        parts.append(Content.styled(verdict, "bold " + (
            "$error" if self.result_code else "$success" if passed else "$foreground")))
        if hint:
            parts.append(Content.styled(hint, "$text-muted"))
        for level, label in labels:
            if count := counts[level]:
                suffix = "s" if count > 1 and level != "Blocked" else ""
                parts.append(Content.styled(f"{count} {label}{suffix}",
                                            _FINDING_STYLES.get(level, "$text-muted")))
        status = self.query_one("#status", Static)
        status.set_classes("")
        self._settled_status = Content(" · ").join(parts)
        status.update(self._settled_status)

    def _clear_notices(self):
        self.clear_notifications()
        # Textual 8.2 leaves an empty holder in the rack when clearing a toast.
        self.screen.query("ToastRack > ToastHolder").remove()

    @on(Notify)
    def _replace_notification(self, event: Notify):
        if event.notification.raised_at < self._notice_since:
            event.prevent_default()
        else:
            self._clear_notices()

    def _notice(self, title, message, severity="information"):
        if any(self.screen.has_class(mode) for mode in ("-compact", "-narrow", "-low", "-tiny")):
            title, message = "", f"{title} · {message}"
        self.notify(message, title=title, severity=severity,
                    timeout={"information": 2.5, "warning": 4.5, "error": 7}[severity],
                    markup=False)

    def _send_copy(self, text, title, fallback):
        try:
            self.copy_to_clipboard(text)
        except (OSError, UnicodeError):
            self._notice("Clipboard unavailable", fallback, "warning")
            return False
        self._notice(title, "Sent to terminal. Try paste.")
        return True

    def action_copy_config_path(self):
        self._send_copy(str(self.config.absolute()), "Configuration path",
                         "Use the path passed to FrameIt.")

    def _save_report(self, path):
        if path.resolve() == self.config.resolve():
            raise ValueError("Choose a path other than the active configuration or saved report.")
        contents = serialize_projection(self._report)
        # Publish a complete new file atomically, without replacing any existing entry.
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix=".frameit-report-", delete_on_close=False) as stream:
            stream.write(contents + "\n")
            stream.close()
            path.hardlink_to(stream.name)

    def action_save_report(self):
        if self.busy or self._report is None:
            return
        label = "Saved report" if self.saved else (
            "Previous report" if self._stale else "Latest report")

        def saved(path):
            if path is not None:
                self._notice("Report saved", str(path))

        self.push_screen(_SaveReport(label, self._save_report), saved)

    def _wide_sidebar(self, size=None):
        size = self.size if size is None else size
        return (size.width >= self.HORIZONTAL_BREAKPOINTS[-1][0]
                and size.height >= self.VERTICAL_BREAKPOINTS[-1][0])

    def _sidebar_available(self):
        return self.SIDEBAR is not None and self._has_report and self._wide_sidebar()

    def check_action(self, action, parameters):
        if isinstance(self.screen, ModalScreen):
            return False
        if self.saved and action in {"refresh", "copy_config_path"}:
            return False
        if action == "save_report":
            return self._report is not None and not self.busy
        if action == "toggle_sidebar":
            return self._sidebar_available()
        if action in {"back", "copy_finding"}:
            within_finding = not self.busy and self.query_one("#finding-scroll").has_focus_within
            return within_finding and (action == "back" or self._current_finding() is not None)
        if action == "filter_notes":
            return (not self.busy and self.query_one("#findings-layout").has_focus_within
                    and self.query_one("#finding-filter").display)
        return super().check_action(action, parameters)

    def _settle_sidebar(self, sidebar, wide):
        disabled = wide and self._sidebar_closed
        if disabled and self.focused and sidebar in self.focused.ancestors_with_self:
            self._sidebar_focus = self.focused
            self._focus_sidebar_main()
        sidebar.styles.width = None
        sidebar.set_class(self._sidebar_closed, "sidebar-closed")
        sidebar.disabled = disabled
        if not self._sidebar_closed:
            previous, self._sidebar_focus = self._sidebar_focus, None
            if wide and previous is not None and self.focused is self.query_one(self.SIDEBAR[1]):
                previous.focus()

    def _focus_sidebar_main(self):
        if self.SIDEBAR[1] == "#finding-scroll":
            self._focus_finding(True)
        else:
            self.query_one(self.SIDEBAR[1]).focus()

    def action_toggle_sidebar(self):
        if not self._sidebar_available():
            return
        sidebar = self.query_one(self.SIDEBAR[0])
        current = sidebar.region.width if sidebar.display else 0
        if self._sidebar_width is None:
            self._sidebar_width = sidebar.styles.width
        self._sidebar_closed = not self._sidebar_closed
        self._sidebar_epoch += 1
        epoch = self._sidebar_epoch
        if self._sidebar_closed and self.focused and sidebar in self.focused.ancestors_with_self:
            self._sidebar_focus = self.focused
            self._focus_sidebar_main()
        sidebar.disabled = self._sidebar_closed
        sidebar.remove_class("sidebar-closed")

        def finish():
            if epoch == self._sidebar_epoch:
                self._settle_sidebar(sidebar, self._wide_sidebar())

        if self.animation_level == "full":
            sidebar.styles.width = current
            target = Scalar.parse("0") if self._sidebar_closed else self._sidebar_width
            sidebar.styles.animate("width", target, duration=.18, easing="out_cubic",
                                   on_complete=finish)
        else:
            finish()

    @on(OptionList.OptionHighlighted, "#finding-list")
    def _select_finding(self, event: OptionList.OptionHighlighted):
        if (self.result_code is not None and event.option is event.option_list.highlighted_option):
            self._present_finding(self._current_finding(), reset=True)

    @on(OptionList.OptionSelected, "#finding-list")
    def _open_finding(self):
        if not self.busy:
            self._focus_finding(True)

    def _focus_finding(self, reading):
        layout = self.query_one("#findings-layout")
        layout.set_class(reading, "reading-finding")
        target = self.query_one("#finding-scroll" if reading else "#finding-list")
        # A terminal can deliver the tab shortcut and Enter in the same read.
        self.screen.set_focus(target, scroll_visible=False)

    def action_back(self):
        if self._wide_sidebar() and self.SIDEBAR and self.SIDEBAR[0] == "#finding-list":
            if self._sidebar_closed:
                self.action_toggle_sidebar()
        self._focus_finding(False)

    def _current_finding(self):
        index = self.query_one("#finding-list", OptionList).highlighted
        return self._findings_visible[index] if index is not None else None

    def _list_findings(self, previous):
        listing = self.query_one("#finding-list", OptionList)
        notes = sum(level == "Field discovery" for level, _ in self.findings)
        self._notes_only = bool(notes and self._notes_only)
        visible = [(level, item) for level, item in self.findings
                   if not self._notes_only or level == "Field discovery"]
        self._findings_visible = visible
        index = visible.index(previous) if previous in visible else None
        if index is None and previous is not None:
            key = finding_key(*previous)
            matches = [i for i, finding in enumerate(visible) if finding_key(*finding) == key]
            if len(matches) == 1:
                index = matches[0]
        with listing.prevent(OptionList.OptionHighlighted):
            listing.set_options(
                Content.styled(f"{number:>2}  {_finding_title(level, item)}",
                               _FINDING_STYLES.get(level, "$text-muted"))
                for number, (level, item) in enumerate(visible, start=1))
            listing.highlighted = (index or 0) if visible else None
        filter_label = self.query_one("#finding-filter", Static)
        filter_label.display = bool(notes)
        shown = "Field discovery only" if self._notes_only else "All findings"
        filter_label.update(f"{shown} · {notes} discovery · n Filter")
        self._present_finding(self._current_finding(), reset=index is None)
        return index is not None

    def action_filter_notes(self):
        previous = self._current_finding()
        self._notes_only = not self._notes_only
        self._list_findings(previous)

    def _present_finding(self, finding, *, reset):
        summary = self.query_one("#finding", Static)
        actions = self.query_one("#finding-actions", Static)
        disclosure = self.query_one("#finding-evidence", Collapsible)
        hints = self.finding_actions(finding)
        actions.display = bool(hints)
        actions.update(hints)
        if finding is not None:
            level, item = finding
            summary.update(_finding_summary(level, item))
            disclosure.display = level == "Error"
            if disclosure.display:
                self.query_one("#finding-evidence-text", Static).update(_finding_evidence(item))
        else:
            summary.update("No findings.")
            disclosure.display = False
        if reset:
            disclosure.collapsed = True
            self.query_one("#finding-scroll").scroll_home(animate=False)
        self.screen.refresh_bindings()

    def finding_actions(self, finding):
        return "y Copy evidence" if finding is not None else ""

    def action_copy_finding(self):
        if finding := self._current_finding():
            level, item = finding
            text = str(_finding_summary(level, item))
            if level == "Error":
                text += "\n\n" + _finding_evidence(item)
            self._send_copy(text, "Finding evidence", "Use the visible evidence instead.")

    def action_refresh(self) -> None:
        if not self.busy and not self.saved:
            self._start_check()

    def action_quit(self):
        if not self.busy and self.result_code is not None:
            self.exit(self.result_code)

    def action_interrupt(self):
        if not self.busy:
            self.exit(130)
        else:
            self._cancel.set()
            self._stop_feedback()
            status = "Cancellation requested · waiting for the current operation"
            if self._has_report and not self.BRANDED_REFRESH:
                status = f"Previous report shown\n{status}"
            self.query_one("#status", Static).update(status)
            self.query_one("#operation-context", Static).update("")
