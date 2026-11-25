"""Read-only terminal view of the validation report."""

from collections import Counter
from dataclasses import dataclass
from os import environ
from pathlib import Path
from shlex import join, split
from subprocess import run

from textual import on
from textual.app import ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Collapsible, DataTable, Static, TabbedContent, TabPane

from frameit.core.reports import memory_summary
from frameit.report_diff import product_key, product_path, report_changes
from frameit.report_motion import ReportScroll
from frameit.report_tui import DisclosureScroll, EvidenceChoices, ReportApp, _time_label, _yaml

_DETAIL_LABELS = {
    "configuration": "Effective configuration",
    "origins": "Setting origins",
    "plan": "Processing plan",
    "why": "Why? / Evidence",
    "changes": "Changes since previous report",
    "raw": "Raw report",
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


def _overview(report, config, schema_only, overrides, *, has_warnings, saved=False):
    data = report["data"]
    configuration, plan = data["configuration"], data["plan"]
    prepared = plan.get("sources", {})
    confirmed = (report["status"] == "ok" and not schema_only
                 and not any(item["status"] == "blocked"
                             for item in report.get("deferred_checks", ())))
    lines = []
    if report["errors"]:
        error = report["errors"][0]
        lines.extend((f"Fix first · [{error['code']}] {error['path']}", *error["repairs"],
                      "Open Findings (2) for evidence.", ""))
    elif confirmed:
        lines.extend(("Metadata preflight: metadata and required static support.",
                      "Other value/mask checks are deferred to execution.", ""))
    elif schema_only:
        lines.extend(("Schema only: inputs, dependencies and execution were not checked.", ""))

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
    lines.append(f"{'Selection':<11}{selection or 'Not reported'}")
    time_span = time_rows[0] if time_rows else inputs if schema_only else unavailable
    lines.append(f"{'Time':<11}{time_span}")
    lines.extend(f"{'':<11}{row}" for row in time_rows[1:])
    lines.extend((f"{'Region':<11}{region}", f"{'Outputs':<11}{outputs}"))
    if memory := memory_summary(plan.get("memory_estimate")):
        lines.extend(("", *memory))
    if saved:
        lines.extend(("", "Recorded evidence only. Open a live request to check current inputs."))
    elif not report["errors"]:
        if schema_only:
            lines.extend(("", "Next: validate without --schema-only."))
        elif confirmed:
            if has_warnings:
                lines.extend(("", "See warnings in Findings."))
            lines.extend(("", f"Next: {_run_command(config, overrides)}"))
        else:
            lines.extend(("", "Next: review the blocking checks in Findings (2)."))
    return "\n".join(lines)


def _setting_at(configuration, path):
    value = configuration
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return False, None
        value = value[key]
    return True, value


def _bound_field_ids(source, product):
    bound = source.get("field_binding") or {}
    return dict.fromkeys(record["field_id"]
                         for descriptor in bound.get("products", {}).get(product, {}).values()
                         for record in descriptor.get("records", ()))


@dataclass
class _RelatedView:
    tab: str
    view_state: tuple
    finding: tuple | None
    notes_only: bool
    reading_finding: bool
    product: str | None
    disclosures: dict
    evidence: tuple | None


class ValidationApp(ReportApp):
    TITLE = "FrameIt / validate"
    LOG_CONTEXT = "validation"
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
        Binding("e", "edit_config", "Open configuration in editor", show=False),
        Binding("l", "copy_location", "Copy exact YAML location", show=False),
        Binding("g", "related", "Related evidence", show=False),
        Binding("u", "show_changes", "Changes since previous report", show=False),
    ]
    CSS = ReportApp.CSS + """
    #summary { padding-top: 1; }
    #details-scroll Collapsible {
        width: auto;
        min-width: 100%;
        border: none;
        padding: 0 0 1 0;
    }
    #details-scroll Contents, #details-scroll Contents Static { width: auto; }
    #details-scroll Contents Static { text-wrap: nowrap; }
    #details-scroll .readable, #details-scroll .readable > Contents,
    #details-scroll .readable > Contents > Static { width: 100%; }
    #details-scroll .readable > Contents > Static { text-wrap: wrap; }
    #plan-products { height: auto; max-height: 100%; }
    """

    def __init__(self, config: Path, collect, *, schema_only=False, overrides=None,
                 saved_report=None, isolate=False):
        super().__init__(config, collect, saved_report=saved_report, isolate=isolate)
        self.schema_only = schema_only if saved_report is None else any(
            item["status"] == "schema-only" for item in saved_report["deferred_checks"])
        self.overrides = overrides or {}
        self._products = {}
        self._product = None
        self._related_views = []
        self._why_target = None
        self._changes = []

    def compose_view(self) -> ComposeResult:
        with TabbedContent(id="report-tabs", classes="report-body"):
            with TabPane("Overview", id="overview"):
                with ReportScroll(id="overview-scroll"):
                    yield Static(id="summary", markup=False)
            with TabPane("Findings", id="findings"):
                yield from self.compose_findings()
            with TabPane("Details", id="details"):
                with DisclosureScroll(id="details-scroll"):
                    yield Static(id="details-sticky", classes="pinned-heading", markup=False)
                    for key, label in _DETAIL_LABELS.items():
                        with Collapsible(title=label, id=f"detail-{key}",
                                         classes=("readable" if key in {"plan", "why", "changes"}
                                                  else None),
                                         collapsed_symbol="›", expanded_symbol="⌄"):
                            if key == "plan":
                                yield DataTable(id="plan-products", cursor_type="row")
                            yield Static(id=f"detail-{key}-text", markup=False)

    def prepare_view(self, report: dict):
        data = report["data"]
        return {key: _yaml(data[key]) if data[key] else "Unavailable"
                for key in ("configuration", "origins")}

    def show_report(self, report: dict, prepared, previous_report) -> None:
        blocked = any(level == "Blocked" for level, _ in self.findings)
        verdict = (
            "Validation failed" if self.result_code else "Validation incomplete" if blocked
            else "Schema checks passed" if self.schema_only else "Validation passed")
        scope = ("Schema only" if self.schema_only else
                 "Metadata preflight" if report["data"]["configuration"] else "Configuration check")
        self.set_status(verdict, hint=scope, passed=not (self.result_code or blocked))
        self.query_one("#summary", Static).update(
            _overview(report, self.config, self.schema_only, self.overrides,
                      has_warnings=any(level == "Warning" for level, _ in self.findings),
                      saved=self.saved))
        plan_title = _DETAIL_LABELS["plan"]
        if self.result_code or blocked:
            plan_title = "Partial plan"
            if report["data"]["plan"].get("planned_products"):
                plan_title += " · unconfirmed paths"
        self.query_one("#detail-plan", Collapsible).title = plan_title
        self._plan_confirmed = not (self.result_code or blocked)
        for key, text in prepared.items():
            self.query_one(f"#detail-{key}-text", Static).update(text)
        self._show_products(report["data"]["plan"])
        self._show_comparison(previous_report, report)
        self._related_views.clear()
        self._show_why(None)
        if not self.query_one("#detail-raw", Collapsible).collapsed:
            self._show_raw_report()
        self.query_one("#details-scroll", DisclosureScroll).update_heading()
        if not self._has_report:
            self.action_view("overview")

    def _show_products(self, plan):
        from rich.text import Text

        self._products = {product_key(item): item for item in plan.get("products", ())}
        table = self.query_one("#plan-products", DataTable)
        table.display = bool(self._products)
        table.clear(columns=True)
        for label, width in (("Source", 14), ("Product", 12), ("Fields", 6), ("Destination", 24)):
            table.add_column(label, width=width)
        for key, item in self._products.items():
            path = product_path(plan, item)
            cells = (item.get("source") or "—", item["product"].replace("_", " "),
                     str(len(item["fields"])) if "fields" in item else "—",
                     Path(path).name if path else "Not reported")
            table.add_row(*(Text(cell, no_wrap=True, overflow="ellipsis") for cell in cells),
                          key=key)
        if self._products:
            if self._product not in self._products:
                self._product = next(iter(self._products))
            table.move_cursor(row=table.get_row_index(self._product), animate=False)
        else:
            self._product = None
        self._show_product(plan)

    @on(DataTable.RowHighlighted, "#plan-products")
    def _select_product(self):
        self._sync_product()

    def _sync_product(self):
        table = self.query_one("#plan-products", DataTable)
        if not table.is_valid_coordinate(table.cursor_coordinate):
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        if key != self._product:
            self._product = key
            self._show_product(self._report["data"]["plan"])
        return self._products.get(key)

    def _show_product(self, plan):
        if item := self._products.get(self._product):
            scope = "Metadata preflight" if self._plan_confirmed else "Unconfirmed partial evidence"
            fields = ", ".join(item.get("fields", ())) or "None reported"
            path = product_path(plan, item) or "Not reported"
            lines = [f"Scope: {scope} · Planned, not published", "",
                     f"Source: {item.get('source') or '—'}",
                     f"Product: {item['product'].replace('_', ' ')}",
                     f"Fields: {fields}", f"Full destination: {path}"]
            keys = ("representation", "stored_names", "units", "dimensions", "time_association")
            if facts := {key: item[key] for key in keys if key in item}:
                lines.extend(("", "Product evidence", _yaml(facts)))
            if layout := plan.get("layouts", {}).get("products", {}).get(self._product):
                lines.extend(("", "Reported layout", _yaml(layout)))
            lines.extend(("", "g Related evidence"))
        elif paths := plan.get("planned_products"):
            lines = ["Only unconfirmed destinations were reported. Exact paths:", *paths]
        else:
            lines = ["No products reported."]
        self.query_one("#detail-plan-text", Static).update("\n".join(lines))

    @on(Collapsible.Expanded, "#detail-raw")
    def _show_raw_report(self):
        if self._report is not None:
            self.query_one("#detail-raw-text", Static).update(_yaml(self._report))

    def _show_comparison(self, previous, report):
        self._changes = report_changes(previous, report) if previous else []
        section = self.query_one("#detail-changes", Collapsible)
        section.display = bool(self._changes)
        if self._changes:
            text = ["Compared with the last completed check.", "",
                    *(label for label, _ in self._changes)]
            if any(target is not None for _, target in self._changes):
                text.extend(("", "g Open related items"))
            self.query_one("#detail-changes-text", Static).update("\n".join(text))

    def action_show_changes(self):
        if not self.busy and self._changes:
            self.action_view("details")
            section = self.query_one("#detail-changes", Collapsible)
            section.collapsed = False
            section.query_one("CollapsibleTitle").focus()

    def _sidebar_available(self):
        return (not self.busy and super()._sidebar_available()
                 and self.query_one("#report-tabs", TabbedContent).active == "findings")

    def _selected_error(self):
        selected = self._current_finding()
        return selected[1] if selected and selected[0] == "Error" else None

    def finding_actions(self, finding):
        hints = super().finding_actions(finding)
        if finding and finding[0] == "Error":
            if not self.saved:
                hints = "e Open config  " + hints
            if finding[1]["locations"]:
                hints += "  l Copy YAML location"
        if self._finding_links(finding):
            hints += "  g Related"
        return hints

    def check_action(self, action, parameters):
        if not self.busy and not isinstance(self.screen, ModalScreen):
            if action == "show_changes":
                return bool(self._changes)
            if action == "related":
                return any(self.query_one(selector).has_focus_within for selector in (
                    "#findings-layout", "#detail-plan", "#detail-changes", "#detail-why"))
            if action == "back" and self._related_views:
                return True
        if action in {"edit_config", "copy_location"}:
            if (isinstance(self.screen, ModalScreen) or self.busy
                    or not self.query_one("#findings-layout").has_focus_within):
                return False
            if self.saved and action == "edit_config":
                return False
            item = self._selected_error()
            return bool(item and (action == "edit_config" or item["locations"]))
        return super().check_action(action, parameters)

    def _finding_links(self, finding):
        if not finding or self._report is None or finding[0] == "Warning":
            return []
        level, item = finding
        path = item["path"]
        choices = []
        for other_level, other in self.findings:
            if level == "Blocked" and other_level == "Error":
                if other["path"] in item.get("prerequisites", ()):
                    choices.append((f"Cause [{other['code']}] · {other['path']}",
                                    ("finding", (other_level, other))))
            elif level == "Error" and other_level == "Blocked":
                if path in other.get("prerequisites", ()):
                    choices.append((f"Blocked · {other['path']}",
                                    ("finding", (other_level, other))))
        data = self._report["data"]
        if path in data["origins"] or _setting_at(data["configuration"], path)[0]:
            choices.append((f"Setting · {path}", ("setting", path)))
        for key, product in self._products.items():
            if path == f"products.{product['product']}":
                choices.append((f"Product · {key}", ("product", key)))
        sources = data["plan"].get("sources", {})
        contexts = item.get("contexts", ())
        names = {context.get("source") for context in contexts}
        for name, source in sources.items():
            prefix = f"sources.{name}"
            if name in names or path == prefix or path.startswith(prefix + "."):
                choices.append((f"Source · {name}", ("source", name)))
                ids = dict.fromkeys(context.get("field_id") for context in contexts
                                    if context.get("source") == name)
                for identity in ids:
                    if field := source.get("fields", {}).get(identity):
                        choices.append((f"Native field · {field['name']}",
                                        ("field", (name, identity))))
        return choices

    def _product_uses(self, name, identity):
        source = self._report["data"]["plan"]["sources"][name]
        return [(key, item["product"]) for key, item in self._products.items()
                if item.get("source") == name
                and identity in _bound_field_ids(source, item["product"])]

    def _related_choices(self):
        if self._report is None:
            return []
        if self.query_one("#findings-layout").has_focus_within:
            return self._finding_links(self._current_finding())
        if self.query_one("#detail-changes").has_focus_within:
            return [(label, target) for label, target in self._changes if target is not None]
        if self.query_one("#detail-why").has_focus_within:
            if self._why_target is not None and self._why_target[0] == "field":
                return [(f"Product · {key}", ("product", key))
                        for key, _ in self._product_uses(*self._why_target[1])]
            return []
        if not self.query_one("#detail-plan").has_focus_within:
            return []
        choices = [("Blocked · plan", ("finding", (level, item))) for level, item in self.findings
                   if level == "Blocked" and item["path"] == "plan"]
        if not (product := self._sync_product()):
            return choices
        name = product.get("source")
        source = self._report["data"]["plan"].get("sources", {}).get(name)
        if source is None:
            return choices
        choices.append((f"Source · {name}", ("source", name)))
        for identity in _bound_field_ids(source, product["product"]):
            if field := source.get("fields", {}).get(identity):
                label = f"{field['name']} · {field.get('group') or 'group not reported'}"
                choices.append((f"Bound field · {label}", ("field", (name, identity))))
        return choices

    def action_related(self):
        if choices := self._related_choices():
            self._choose_evidence("Related evidence", choices)

    def _choose_evidence(self, title, choices):
        tabs = self.query_one("#report-tabs", TabbedContent)
        snapshot = _RelatedView(
            tabs.active, self._view_state(), self._current_finding(), self._notes_only,
            self.query_one("#findings-layout").has_class("reading-finding"), self._product,
            {key: self.query_one(f"#detail-{key}", Collapsible).collapsed
             for key in ("plan", "why")},
            self._why_target)
        self.push_screen(EvidenceChoices(title, choices),
                         lambda target: self._follow_evidence(target, snapshot))

    def _follow_evidence(self, target, snapshot):
        if target is None:
            return
        self._related_views.append(snapshot)
        kind, value = target
        if kind == "finding":
            self._notes_only = False
            self._list_findings(value)
            self.query_one("#report-tabs", TabbedContent).active = "findings"
            self._focus_finding(True)
            return
        self.action_view("details")
        if kind == "product":
            self._product = value
            self._show_products(self._report["data"]["plan"])
            section = self.query_one("#detail-plan", Collapsible)
        else:
            self._show_why(target)
            section = self.query_one("#detail-why", Collapsible)
        section.collapsed = False
        section.query_one("CollapsibleTitle").focus()

    def action_back(self):
        if not self._related_views:
            super().action_back()
            return
        snapshot = self._related_views.pop()
        self.query_one("#report-tabs", TabbedContent).active = snapshot.tab
        self.query_one("#findings-layout").set_class(snapshot.reading_finding, "reading-finding")
        self._notes_only = snapshot.notes_only
        if snapshot.finding != self._current_finding():
            self._list_findings(snapshot.finding)
        if self._product != snapshot.product:
            self._product = snapshot.product
            self._show_products(self._report["data"]["plan"])
        self._show_why(snapshot.evidence)
        for key, collapsed in snapshot.disclosures.items():
            self.query_one(f"#detail-{key}", Collapsible).collapsed = collapsed
        self.call_after_refresh(self._restore_view, *snapshot.view_state)

    def _show_why(self, target):
        self._why_target = target
        text = (self._why(*target) if target is not None else
                "Use g on a finding or on a planned product to follow reported evidence.")
        self.query_one("#detail-why-text", Static).update(text)

    def _why(self, kind, value):
        data = self._report["data"]
        if kind == "setting":
            reported, setting = _setting_at(data["configuration"], value)
            origin = data["origins"].get(value)
            if isinstance(origin, str):
                origin = {"yaml": "Authored YAML", "cli": "Command-line override",
                          "default": "FrameIt default"}.get(origin, origin)
            elif origin:
                origin = _yaml(origin)
            shown = str(setting) if isinstance(setting, str) else _yaml(setting)
            return "\n".join((f"Setting · {value}", "",
                              "Effective value:", shown if reported else "Not reported",
                              "", "Origin:", origin or "Reason not reported."))
        name, identity = value if kind == "field" else (value, None)
        source = data["plan"]["sources"][name]
        lines = [f"Source · {name}", "Scope: Reported preflight evidence, not execution.", ""]
        if identity is not None:
            field = source["fields"][identity]
            lines.extend((f"Native field: {field['name']}",
                          f"Group: {field.get('group') or 'Not reported'}",
                          f"Units: {field.get('attributes', {}).get('units') or 'Not reported'}",
                          f"Identity: {identity}"))
            grids = ", ".join(field.get("grid_ids", ()))
            lines.append(f"Grids: {grids or 'Not reported'}")
            uses = [product for _, product in self._product_uses(name, identity)]
            lines.append("Product uses: " + (", ".join(uses) if uses else "Not reported"))
            if uses:
                lines.append("g Open a product")
        else:
            lines.extend(f"{label}: {source.get(key) or 'Not reported'}"
                         for label, key in (("Model", "model"), ("Format", "format")))
            for key, label in (("files", "files"), ("selected_times", "times")):
                values = source.get(key)
                lines.append(f"Selected {label}: {len(values) if values is not None
                                                    else 'Not reported'}")
            if source.get("excluded_files"):
                lines.extend(("", "Reported exclusions:", *source["excluded_files"],
                              "Matching exclusion rule: Not reported"))
        return "\n".join(lines)

    def action_copy_location(self):
        if item := self._selected_error():
            text = "\n".join(f"{mark['file']}:{mark['line']}:{mark['column']}"
                             for mark in item["locations"])
            if text:
                self._send_copy(text, "YAML location", "Use the locations in Technical evidence.")

    def action_edit_config(self):
        if self.busy or self.saved or (item := self._selected_error()) is None:
            return
        try:
            args = split(environ.get("VISUAL") or environ.get("EDITOR") or "")
        except ValueError as exc:
            self._notice("Editor unavailable", f"Check VISUAL or EDITOR: {exc}", "warning")
            return
        if not args:
            self._notice("Editor unavailable", "Set VISUAL or EDITOR, or use the path shown.",
                         "warning")
            return
        target = self.config.absolute()
        if not self._stale:
            # Only the active request may be opened; positions are a convenience.
            mark = next((mark for mark in item["locations"]
                         if Path(mark["file"]).absolute() == target), None)
            editor = Path(args[0]).name
            if mark and type(mark["line"]) is int and mark["line"] > 0:
                if editor in {"vi", "vim", "nvim", "emacs"}:
                    args.append(f"+{mark['line']}")
                elif editor == "nano" and type(mark["column"]) is int and mark["column"] > 0:
                    args.append(f"+{mark['line']},{mark['column']}")
        try:
            with self.suspend():
                try:
                    code = run([*args, str(target)], check=False).returncode
                except (OSError, ValueError) as exc:
                    # Let Textual resume before reporting a launch failure.
                    code = exc
                except KeyboardInterrupt:
                    code = 130
        except SuspendNotSupported:
            code = "Terminal suspension not supported."
        if not isinstance(code, int):
            self._notice("Editor unavailable", f"{code} Open the path separately.", "warning")
            return
        self._stale = True
        status = Content("Not revalidated after editor · Previous report\n") + self._settled_status
        self.query_one("#status", Static).update(status)
        if code:
            self._notice("Editor exited", f"Status {code}. Press r to revalidate when ready.",
                         "warning")

    @on(TabbedContent.TabActivated, "#report-tabs")
    def _refresh_sidebar_binding(self):
        self.screen.refresh_bindings()

    def action_view(self, view):
        if not self.busy and self.result_code is not None:
            self.query_one("#report-tabs", TabbedContent).active = view
            target = f"#{view}-scroll"
            if view == "findings":
                self._focus_finding(self._sidebar_closed and self._wide_sidebar())
            else:
                self.query_one(target).focus()
