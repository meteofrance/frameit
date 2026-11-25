"""Shared terminal lifecycle and diagnostic presentation for FrameIt reports."""

from asyncio import CancelledError
from collections import Counter
from dataclasses import dataclass
from math import ceil
from os import environ
from pathlib import Path
from sys import __stdout__
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
from textual.scrollbar import ScrollBarRender
from textual.theme import Theme
from textual.widgets import Footer, OptionList, ProgressBar, Static
from textual.worker import Worker, WorkerState, get_current_worker

from frameit.core.reports import project_report
from frameit.report_motion import BrandActivity, ReportScroll

_CHECK_LABELS = {
    "unfinished-selection": "Field discovery",
    "execution-dependent": "During run",
    "schema-only": "Not checked in schema mode",
}
_TEAL, _AMBER, _RED, _SLATE = "#49C5BC", "#F5B55E", "#DA5656", "#A6B4C4"
_THEME = Theme(
    name="frameit", primary=_TEAL, accent=_TEAL, warning=_AMBER, error=_RED,
    background="#000000", surface="#000000", panel="#000000", foreground="#E6EDF3",
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
    FINDINGS_HINT = "Review the report findings."
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
    #report-feedback, #feedback-copy {{ height: auto; }}
    #feedback-copy {{ width: 1fr; }}
    #brand-activity {{ display: none; width: 20; height: 10; margin-right: 2; }}
    Screen.starting #report-feedback {{ height: 1fr; align: center middle; }}
    Screen.starting #feedback-copy {{
        width: 44; max-width: 100%; height: 10; align: left middle;
    }}
    Screen.starting #status {{ margin: 0 1; }}
    #work-progress, #local-activity {{ display: none; height: 1; margin: 0 1; }}
    #local-activity {{ width: 12; }}
    #work-progress Bar {{ width: 1fr; }}
    #work-progress Bar > .bar--bar, #work-progress Bar > .bar--indeterminate {{
        background: #31506a;
    }}
    #work-progress Bar > .bar--indeterminate {{ color: $accent 60%; }}
    #work-progress Bar > .bar--complete {{ color: $accent; }}
    Toast {{ width: 44; max-width: 100%; padding: 0 1; background: #102440; }}
    Toast.-information {{ border-left: outer $accent; }}
    Toast.-information .toast--title {{ color: $accent; }}
    Toast.-warning {{ border-left: outer $warning; }}
    Toast.-error {{ border-left: outer $error; }}
    Screen.-compact ToastRack, Screen.-low ToastRack, Screen.-tiny ToastRack {{
        dock: top; align: right top; margin: 0; scrollbar-size: 0 0;
    }}
    Screen.-compact Toast, Screen.-low Toast, Screen.-tiny Toast {{
        width: 1fr; height: 1; margin: 0; text-wrap: nowrap; text-overflow: ellipsis;
    }}
    #interrupt-hint {{ display: none; dock: bottom; padding: 0 1; }}
    Screen.checking #interrupt-hint {{ display: block; }}
    Screen.starting .report-body, Screen.empty .report-body, Screen.checking Footer {{
        display: none;
    }}
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
    #findings-layout {{ height: 1fr; }}
    Screen.-wide.-tall #findings-layout {{ layout: horizontal; }}
    Screen.-wide.-tall #findings-layout > Widget {{ height: 1fr; }}
    Screen.-wide.-tall #finding-list {{
        width: 32; margin-right: 1;
    }}
    Screen.-wide.-tall #finding-list.sidebar-closed {{ display: none; }}
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
        self._worker = None
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
            context.tooltip = "p · Copy configuration path"
            yield context
        with Horizontal(id="report-feedback"):
            yield BrandActivity(id="brand-activity")
            with Vertical(id="feedback-copy"):
                yield Static(id="status", markup=False)
                yield ProgressBar(total=1, show_percentage=False, show_eta=False,
                                  id="work-progress")
                yield Static(id="local-activity", markup=False)
        yield from self.compose_view()
        yield Static("Ctrl+C  Cancel check", id="interrupt-hint", markup=False)
        yield Footer(compact=True)

    def compose_view(self) -> ComposeResult:
        raise NotImplementedError

    def compose_findings(self) -> ComposeResult:
        with Vertical(id="findings-layout"):
            yield OptionList(id="finding-list", markup=False, compact=True)
            with ReportScroll(id="finding-scroll"):
                yield Static(id="finding", markup=False)

    def on_mount(self):
        for widget in self.query("VerticalScroll, OptionList, DataTable"):
            if widget.scrollbar_size_vertical:
                widget.vertical_scrollbar.renderer = _ThinThumb
        for widget in self.query("DataTable, #details-scroll"):
            widget.horizontal_scrollbar.renderer = _ThinThumb
        self.begin_capture_print(self, stdout=False)
        self._start_check()

    @property
    def busy(self):
        return self._worker is not None

    def _start_check(self):
        if self._has_report and self.BRANDED_REFRESH and self._hidden_view is None:
            self._hidden_view = self._view_state()
        self._notice_since = time()
        self._clear_notices()
        self._cancel.clear()
        self._started = self._scan_started = monotonic()
        self._eta_at = None
        self._checked, self._total = 0, None
        self._runtime_warnings = []
        self._activity = self.STAGES["configuration"]
        self.screen.add_class("checking")
        self.screen.set_class(not self._has_report or self.BRANDED_REFRESH, "starting")
        self.query_one("#status").set_classes("progress")
        self._worker = self.run_worker(self._collect, thread=True, exit_on_error=False)
        self._elapsed_timer = self.set_interval(1, self._tick)
        self._sync_activity()
        self._tick()

    def _collect(self):
        worker = get_current_worker()
        last_key, last_sent = None, 0.0

        def progress(stage, source, checked, total):
            nonlocal last_key, last_sent
            if self._cancel.is_set() or worker.is_cancelled:
                raise CancelledError
            at, key = monotonic(), (stage, source, total)
            if key != last_key or (checked is not None and checked == total
                                   or at - last_sent >= 0.12):
                self.post_message(_Progress(worker, stage, source, checked, total, at))
                last_key, last_sent = key, at

        result = self.collect(progress=progress)
        progress("report", None, None, None)
        report = project_report(result)
        prepared = self.prepare_view(report)
        if self._cancel.is_set() or worker.is_cancelled:
            raise CancelledError
        return report, prepared

    def prepare_view(self, report: dict):
        return None

    def on_print(self, event: events.Print):
        if self.busy and event.stderr:
            level, _, message = event.text.rstrip().partition(":")
            if level == "WARNING" and message:
                detail = message.partition(":")[2] or message
                self._runtime_warnings.append(f"({self.LOG_CONTEXT} log) {detail}")

    @on(_Progress)
    def _observe(self, event: _Progress):
        if event.worker is not self._worker or self._cancel.is_set() or not self.is_running:
            return
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
        self._checked, self._total = event.checked or 0, event.total
        self._sync_activity()
        self._tick()

    def _tick(self):
        if self.busy and not self._cancel.is_set():
            now = monotonic()
            activity = self._activity
            if self._eta_at is not None and now < self._eta_at:
                activity += f" · ETA ~{_clock(ceil(self._eta_at - now))} (this source)"
            elapsed = _clock(now - self._started)
            if self._has_report and not self.BRANDED_REFRESH:
                status = f"Refreshing (previous report shown)\n{activity} · {elapsed} elapsed"
            else:
                prefix = "Refreshing report\n" if self._has_report else ""
                status = f"{prefix}{activity}\n{elapsed} elapsed"
            self.query_one("#status", Static).update(status)

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
        branded = (active and graphical and self.screen.has_class("starting")
                   and size.width >= 68 and size.height >= 20)
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
        if event.worker is not self._worker or event.state in {
                WorkerState.PENDING, WorkerState.RUNNING}:
            return
        self._worker = None
        self._stop_feedback()
        self.screen.remove_class("checking", "starting")
        hidden_view = self._hidden_view
        if self._cancel.is_set() or event.state == WorkerState.CANCELLED:
            if hidden_view is None:
                self.exit(130)
            else:
                self.result_code = 130
                self._stale = True
                status = self.query_one("#status", Static)
                status.set_classes("warning")
                status.update("Refresh cancelled · previous report shown")
                self.call_after_refresh(self._restore_hidden_view)
            return
        if event.state == WorkerState.ERROR:
            if self.result_code != 130:
                self.result_code = 1
            self._stale = self._has_report
            self.screen.set_class(not self._has_report, "empty")
            status = self.query_one("#status", Static)
            status.set_classes("error")
            problem = " ".join(str(event.worker.error).split())
            verdict = "Refresh failed · previous report is stale" if self._stale else "Check failed"
            status.update(f"{verdict} · {problem}. Press r to retry.")
            self._notice("Refresh failed" if self._stale else "Check failed",
                         "Press r to retry.", "warning" if self._stale else "error")
            if hidden_view is not None:
                self.call_after_refresh(self._restore_hidden_view)
            return
        report, prepared = event.worker.result
        self._stale = False
        self.screen.remove_class("empty")
        focused, offsets = hidden_view or self._view_state()
        listing = self.query_one("#finding-list", OptionList)
        old_index = listing.highlighted
        previous = None if old_index is None else self.findings[old_index]
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
        retained = previous in self.findings
        index = self.findings.index(previous) if retained else 0
        with listing.prevent(OptionList.OptionHighlighted):
            listing.set_options(
                Content.styled(f"{number:>2}  {_finding_title(level, item)}", {
                    "Error": f"bold {_RED}", "Warning": _AMBER,
                }.get(level, _SLATE))
                for number, (level, item) in enumerate(self.findings, start=1))
            listing.highlighted = index if self.findings else None
        detail = _finding_detail(*self.findings[index]) if self.findings else "No findings."
        self.query_one("#finding", Static).update(detail)
        if not retained:
            self.query_one("#finding-scroll").scroll_home(animate=False)
        refreshed = self._has_report
        self.show_report(report, prepared)
        self._has_report = True
        self.screen.refresh_bindings()
        self._notify_result(refreshed)
        offsets = [(widget, offset, anchor) for widget, offset, anchor in offsets
                   if (retained or widget.id != "finding-scroll")
                   and (index == old_index or widget is not listing)]
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

    def show_report(self, report: dict, prepared) -> None:
        raise NotImplementedError

    def set_status(self, verdict, *, hint=None):
        self._verdict = verdict
        counts = Counter(level for level, _ in self.findings)
        labels = (("Error", "error"), ("Warning", "warning"), ("Blocked", "blocked"),
                  ("Field discovery", "field discovery note"))
        stats = [f"{count} {label}{'s' if count > 1 and level != 'Blocked' else ''}"
                 for level, label in labels if (count := counts[level])]
        status = self.query_one("#status", Static)
        status.set_classes(
            "error" if self.result_code else "warning" if counts["Warning"] or counts["Blocked"]
            else "")
        status.update(" · ".join(filter(None, (verdict, hint, *stats))))

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
        if any(self.screen.has_class(mode) for mode in ("-compact", "-low", "-tiny")):
            title, message = "", f"{title} · {message}"
        self.notify(message, title=title, severity=severity,
                    timeout={"information": 2.5, "warning": 4.5, "error": 7}[severity],
                    markup=False)

    def _notify_result(self, refreshed):
        if self.result_code:
            self._notice(self._verdict, self.FINDINGS_HINT, "error")
        elif any(level in {"Warning", "Blocked"} for level, _ in self.findings):
            self._notice(self._verdict, self.FINDINGS_HINT, "warning")
        elif refreshed or self.LOG_CONTEXT == "validation":
            message = ("Inputs and execution were not checked."
                       if getattr(self, "schema_only", False) else
                       "Report reloaded." if refreshed else "No blocking diagnostics.")
            self._notice(self._verdict, message)

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

    def _wide_sidebar(self, size=None):
        size = self.size if size is None else size
        return (size.width >= self.HORIZONTAL_BREAKPOINTS[-1][0]
                and size.height >= self.VERTICAL_BREAKPOINTS[-1][0])

    def _sidebar_available(self):
        return self.SIDEBAR is not None and self._has_report and self._wide_sidebar()

    def check_action(self, action, parameters):
        if action == "toggle_sidebar":
            return self._sidebar_available()
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
            self.query_one("#finding", Static).update(
                _finding_detail(*self.findings[event.option_index]))
            self.query_one("#finding-scroll").scroll_home(animate=False)

    def action_refresh(self) -> None:
        if not self.busy:
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
