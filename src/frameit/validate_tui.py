"""Read-only terminal view of the validation report."""

from collections import Counter
from pathlib import Path
from shlex import join

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Collapsible, Static, TabbedContent, TabPane

from frameit.report_motion import ReportScroll
from frameit.report_tui import ReportApp, _time_label, _yaml

_DETAIL_LABELS = {
    "configuration": "Effective configuration",
    "origins": "Setting origins",
    "plan": "Processing plan",
}


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
    confirmed = (report["status"] == "ok" and not schema_only
                 and not any(item["status"] == "blocked"
                             for item in report.get("deferred_checks", ())))
    lines = []
    if report["errors"]:
        error = report["errors"][0]
        lines.extend((f"Fix first · [{error['code']}] {error['path']}", *error["repairs"], ""))
    elif confirmed:
        lines.extend(("Preflight only: metadata and required static support.",
                      "Other value/mask checks are deferred to execution.", ""))

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
        elif confirmed:
            if has_warnings:
                lines.extend(("", "See warnings in Findings."))
            lines.extend(("", f"Next: {_run_command(config, overrides)}"))
        else:
            lines.extend(("", "Next: review the blocking checks in Findings (2)."))
    return "\n".join(lines)


class ValidationApp(ReportApp):
    TITLE = "FrameIt / validate"
    LOG_CONTEXT = "validation"
    FINDINGS_HINT = "Findings (2) lists repairs and warnings."
    SIDEBAR = ("#finding-list", "#finding-scroll")
    BRANDED_REFRESH = True
    STAGES = {
        **ReportApp.STAGES,
        "binding": "Checking selected fields and methods",
        "plan": "Checking planned outputs and resources",
        "report": "Preparing validation report",
    }
    BINDINGS = [
        Binding("1", "view('overview')", "Overview"),
        Binding("2", "view('findings')", "Findings"),
        Binding("3", "view('details')", "Details"),
        Binding("r", "refresh", "Revalidate"),
        Binding("q", "quit", "Quit"),
    ]
    CSS = ReportApp.CSS + """
    #summary { padding-top: 1; }
    #details-sticky {
        dock: top;
        height: 1;
        padding: 0 1;
        color: $accent;
        text-style: bold;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    #details-scroll CollapsibleTitle:focus {
        background: #102440;
        color: $foreground;
        text-style: bold underline;
    }
    #details-scroll Collapsible {
        width: auto;
        min-width: 100%;
        border: none;
        padding: 0 0 1 0;
    }
    #details-scroll Contents, #details-scroll Contents Static { width: auto; }
    #details-scroll Contents Static { text-wrap: nowrap; }
    """

    def __init__(self, config: Path, collect, *, schema_only=False, overrides=None):
        super().__init__(config, collect)
        self.schema_only = schema_only
        self.overrides = overrides or {}

    def compose_view(self) -> ComposeResult:
        with TabbedContent(id="report-tabs", classes="report-body"):
            with TabPane("Overview", id="overview"):
                with ReportScroll(id="overview-scroll"):
                    yield Static(id="summary", markup=False)
            with TabPane("Findings", id="findings"):
                yield from self.compose_findings()
            with TabPane("Details", id="details"):
                with ReportScroll(id="details-scroll"):
                    yield Static(id="details-sticky", markup=False)
                    for key, label in _DETAIL_LABELS.items():
                        yield Collapsible(
                            Static(id=f"detail-{key}-text", markup=False),
                            title=label, id=f"detail-{key}",
                            collapsed_symbol="›", expanded_symbol="⌄",
                        )

    @on(events.Mount)
    def _watch_details_scroll(self):
        details = self.query_one("#details-scroll", ReportScroll)
        self.watch(details, "scroll_y", self._schedule_details_title, init=False)
        self.watch(details, "virtual_size", self._schedule_details_title, init=False)

    @on(Collapsible.Toggled)
    def _schedule_details_title(self):
        self.call_after_refresh(self._update_details_title)

    def _update_details_title(self):
        details = self.query_one("#details-scroll", ReportScroll)
        top = details.scroll_offset.y
        label = ""
        for section in details.query(Collapsible):
            region = section.virtual_region
            if not section.collapsed and region.y < top < region.bottom:
                label = section.title
                break
        pinned = self.query_one("#details-sticky", Static)
        if pinned.content != label:
            pinned.update(label, layout=False)

    def prepare_view(self, report: dict):
        data = report["data"]
        plan = data["plan"]
        first = {key: plan[key] for key in ("planned_products", "products") if key in plan}
        data = dict(data, plan=first | plan)
        return {key: _yaml(data[key]) if data[key] else "Unavailable" for key in _DETAIL_LABELS}

    def show_report(self, report: dict, prepared) -> None:
        blocked = any(level == "Blocked" for level, _ in self.findings)
        verdict = (
            "Validation failed" if self.result_code else "Validation incomplete" if blocked
            else "Schema checks passed" if self.schema_only else "Validation passed")
        self.set_status(verdict)
        self.query_one("#summary", Static).update(
            _overview(report, self.config, self.schema_only, self.overrides,
                      has_warnings=any(level == "Warning" for level, _ in self.findings)))
        plan_title = _DETAIL_LABELS["plan"]
        if self.result_code or blocked:
            plan_title = "Partial plan"
            if report["data"]["plan"].get("planned_products"):
                plan_title += " · unconfirmed paths"
        for key, text in prepared.items():
            section = self.query_one(f"#detail-{key}", Collapsible)
            section.title = plan_title if key == "plan" else _DETAIL_LABELS[key]
            self.query_one(f"#detail-{key}-text", Static).update(text)
        self._schedule_details_title()
        if not self._has_report:
            self.action_view("overview")

    def _sidebar_available(self):
        return (not self.busy and super()._sidebar_available()
                and self.query_one("#report-tabs", TabbedContent).active == "findings")

    @on(TabbedContent.TabActivated, "#report-tabs")
    def _refresh_sidebar_binding(self):
        self.screen.refresh_bindings()

    def action_view(self, view):
        if not self.busy and self.result_code is not None:
            self.query_one("#report-tabs", TabbedContent).active = view
            target = f"#{view}-scroll"
            if view == "findings":
                target = ("#finding-scroll" if self._sidebar_closed and self._wide_sidebar()
                          else "#finding-list")
            self.query_one(target).focus()
