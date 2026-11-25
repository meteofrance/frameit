"""Read-only terminal explorer for one metadata sample per configured source."""

from collections import Counter
from pathlib import Path
from textwrap import indent

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import (
    Collapsible,
    DataTable,
    Input,
    OptionList,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.option_list import Option

from frameit.inspect_draft import DraftSelection
from frameit.report_diff import source_identity
from frameit.report_motion import ReportScroll
from frameit.report_tui import DisclosureScroll, ReportApp, _time_label, _yaml

_UNKNOWN = "Not reported"
_REQUEST = {"requested": "Requested", "not_requested": "Not requested", "unresolved": "Unresolved"}
_SORTS = {"Name": 0, "Units": 2, "Group": 1}
_GROUP_WIDTH = 8
_FIELD_COLUMNS = (("Name", 11), ("Group", _GROUP_WIDTH), ("Units", 8), ("Request", 13))
_TABS = {
    "overview": "Overview", "coordinates": "Coordinates", "time": "Time", "grids": "Grids",
    "files": "Files", "origins": "Origins", "diagnostics": "Diagnostics",
}
_PANES = {
    "sources-pane": "#sources", "variables-pane": "#fields", "field-scroll": "#field-scroll",
    "source-tabs": "#source-tabs ContentTabs",
}


def _scope(source):
    if "sample" not in source and (files := source.get("files")) is not None:
        return f"{len(files)} files reported · sampling scope not reported"
    sample = source.get("sample", {})
    checked, discovered = sample.get("inspected", 0), sample.get("discovered")
    return f"{checked} of {discovered} files inspected" if discovered is not None else (
        "No file inspected")


def _time_details(source):
    clocks = {}
    for record in source.get("sample_clock", source.get("record_inventory", ())):
        calendar = record.get("calendar") or _UNKNOWN
        key = (record.get("clock") or _UNKNOWN, calendar,
               record.get("reference_calendar") or calendar)
        times, cycles, intervals = clocks.setdefault(key, (set(), set(), set()))
        times.add(_time_label(record["time"]))
        if record.get("cycle") is not None:
            cycles.add(_time_label(record["cycle"]))
        if record.get("time_bounds"):
            intervals.add(" → ".join(map(_time_label, record["time_bounds"])))
    lines = ["Observed in sample" if "sample" in source else "Reported time metadata"]
    for (clock, calendar, reference), (times, cycles, intervals) in clocks.items():
        lines.extend(("", f"Clock: {clock} · Calendar: {calendar}"))
        for title, labels in ((f"Timestamps ({len(times)})", times),
                              (f"Cycles ({reference})", cycles), ("Reported intervals", intervals)):
            lines.extend((f"{title}:", indent("\n".join(sorted(labels)) or _UNKNOWN, "  ")))
    if not clocks:
        lines.append(_UNKNOWN)
    selected = source.get("declaration", {}).get("time")
    lines.extend(("", "Requested time (YAML)", _yaml(selected) if selected else "Not set"))
    for note in source.get("time_notes", ()):
        status = "Not seen in sample" if note["status"] == "not_seen" else _UNKNOWN
        lines.append(f"{note['subject']}: {status}")
    return "\n".join(lines)


def _source_details(source, name, origins):
    sample_path = source.get("sample", {}).get("path")
    fields = source.get("fields", {})
    overview = [f"Sample file: {Path(sample_path).name if sample_path else _UNKNOWN}",
                f"Physical type: {source.get('physical_type') or _UNKNOWN}"]
    if source.get("sample", {}).get("inspected"):
        overview.append(f"Native field entries: {len(fields)}")
    for title, key in (("Not seen in sample", "missing_references"),
                       ("Unresolved request", "unresolved_references")):
        if references := source.get(key):
            overview.extend(("", f"{title}: {', '.join(references)}"))
    for selector in source.get("available_selectors", ()):
        if selector.get("field_id") not in fields:
            overview.extend(("", f"Selector for {selector['field']} · sources.{name}.variables",
                             indent(_yaml(selector["variables"]), "  ")))

    coordinates, grids = {}, []
    for identity, grid in (source.get("native_grids") or {}).items():
        name_list = ", ".join(grid.get("coordinates", {}))
        geometry = {key: value for key, value in grid.items()
                    if key not in {"coordinates", "coordinate_providers"} and value is not None}
        grids.append(f"{identity}\nCoordinates: {name_list or _UNKNOWN}\n{_yaml(geometry)}")
        for coordinate, evidence in grid.get("coordinates", {}).items():
            coordinates.setdefault(f"{coordinate}\n{indent(_yaml(evidence), '  ')}", None)

    dispositions = {"inspected": "Inspected sample", "sample_failed": "Sample failed",
                    "not_inspected": "Not inspected", "selected": "Selected",
                    "time_excluded": "Outside selected time", "metadata_only": "Metadata only",
                    "irrelevant": "Not selected", "dependency_pending": "Dependency pending"}
    files = []
    for entry in source.get("file_inventory", ()):
        state = entry["status"]
        label = dispositions.get(state, f"Recorded status: {state}")
        files.append((label, entry["path"], entry.get("reason")))
        files.extend(("Alias", path, None) for path in entry.get("aliases", ()))
    files.extend(("Excluded", path, None) for path in source.get("excluded_files", ()))
    declarations = source.get("declaration", {}).get("field_metadata")
    setting_origins = {key: value for key, value in origins.items()
                       if key.startswith(f"sources.{name}.")}
    return {
        "overview": "\n".join(overview),
        "coordinates": "\n\n".join(coordinates) or _UNKNOWN,
        "time": _time_details(source),
        "grids": "\n\n".join(grids) or _UNKNOWN,
        "files": "\n".join(f"{label} · {Path(path).name}" for label, path, _ in files) or _UNKNOWN,
        "file_paths": "\n".join(" · ".join(filter(None, (label, path, reason)))
                                for label, path, reason in files) or _UNKNOWN,
        "origins": "\n\n".join((
            f"Observed origins\n{_yaml(source['metadata_origins'])}"
            if source.get("metadata_origins") else f"Observed origins\n{_UNKNOWN}",
            f"YAML field metadata\n{_yaml(declarations) if declarations else 'Not set'}",
            f"Setting origins\n{_yaml(setting_origins) if setting_origins else _UNKNOWN}",
        )),
    }


def _field_cells(source, identity, field):
    attrs = field.get("attributes", {})
    name = field.get("name") or f"Unmapped ({attrs.get('GRIB_paramId') or 'unknown'})"
    request = _REQUEST.get(source.get("request_status", {}).get(identity), _UNKNOWN)
    return name, field.get("group") or "Unknown", str(attrs.get("units") or _UNKNOWN), request


def _row_groups(rows):
    """Keep short labels distinct for repeated names, independent of order and filters."""
    keys = {identity: (cells[0], cells[1] if len(cells[1]) <= _GROUP_WIDTH
                          else cells[1][:_GROUP_WIDTH - 1] + "…")
            for identity, cells in rows}
    counts = Counter(keys.values())
    seen = Counter()
    groups = {}
    for identity, key in sorted(keys.items()):
        group = key[1]
        if counts[key] > 1:
            seen[key] += 1
            suffix = f"·{seen[key]}"
            group = group[:_GROUP_WIDTH - len(suffix)] + suffix
        groups[identity] = group
    return groups


class InspectionApp(ReportApp):
    TITLE = "FrameIt / inspect"
    LOG_CONTEXT = "inspection"
    STAGES = {**ReportApp.STAGES, "metadata": "Reading sample metadata",
              "report": "Preparing sample report"}
    FINDINGS_HINT = "Press d for Diagnostics."
    SIDEBAR = ("#sources-pane", "#fields")
    BINDINGS = [
        Binding("1", "pane('sources-pane')", "Sources"),
        Binding("2", "pane('variables-pane')", "Fields"),
        Binding("3", "pane('field-scroll')", "Field detail", show=False),
        Binding("4", "pane('source-tabs')", "Tabs"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
        Binding("d", "diagnostics", "Diagnostics", show=False),
        Binding("slash", "search", "Search fields", show=False),
        Binding("s", "sort_fields", "Sort fields", show=False),
        Binding("f", "filter_fields", "Filter by request state", show=False),
        Binding("c", "copy_selector", "Copy offered YAML selector", show=False),
        Binding("a", "toggle_draft_field", "Add or remove field in draft", show=False),
        Binding("v", "view_draft", "Review draft selection", show=False),
    ]
    CSS = ReportApp.CSS + """
    #explorer { height: 1fr; }
    #status { margin-top: 0; }
    #source-scope {
        height: 1;
        margin: 0 1;
        color: $text-muted;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    #inspect-upper, #source-tabs { height: 1fr; display: none; }
    #inspect-upper.active-pane, #source-tabs.active-pane { display: block; }
    #inspect-upper > Widget { display: none; width: 1fr; height: 1fr; padding: 0 1; }
    #inspect-upper > .active-pane { display: block; }
    Screen.-wide.-tall #inspect-upper.browsing-fields > #variables-pane,
    Screen.-wide.-tall #inspect-upper.browsing-fields > #field-scroll,
    Screen.three-pane #inspect-upper > Widget { display: block; }
    Screen.three-pane #inspect-upper > .sidebar-closed { display: none; }
    Screen.three-pane #sources-pane { width: 23; border-right: solid $report-rule; }
    Screen.-wide.-tall #field-scroll { width: 45%; max-width: 65; border-left: solid $report-rule; }
    .pane-title { height: 1; text-style: bold; }
    Screen.-compact #inspect-upper > #variables-pane { padding: 0; }
    Screen.-tiny #variables-pane > .pane-title { display: none; }
    #sources, #fields { height: 1fr; }
    #field-search { height: 1; border: none; padding: 0 1; }
    #field-search:focus { border: none; background: $report-selection; }
    #field-controls, #copy-hint { height: auto; color: $text-muted; }
    #field-message { height: auto; color: $text-muted; }
    #field-evidence, #source-file-evidence { border: none; padding: 0; margin-top: 1; }
    """

    def __init__(self, config: Path, collect, *, saved_report=None, isolate=False):
        super().__init__(config, collect, saved_report=saved_report, isolate=isolate)
        self._sources = {}
        self._source_details = {}
        self._source = None
        self._field = None
        self._visible = []
        self._pane = "variables-pane"
        self._sort = "Name"
        self._filter = None
        self._selector = ""
        self._offer = None
        self._draft = {}
        self._draft_source = None

    def compose_view(self) -> ComposeResult:
        with Vertical(id="explorer", classes="report-body"):
            yield Static(id="source-scope", markup=False)
            with Horizontal(id="inspect-upper"):
                with Vertical(id="sources-pane"):
                    yield Static("Sources", classes="pane-title")
                    yield OptionList(id="sources", markup=False, compact=True)
                with Vertical(id="variables-pane"):
                    yield Static("Variables", classes="pane-title")
                    yield Static(id="field-controls", markup=False)
                    yield Input(placeholder="Search name, units or group", id="field-search")
                    yield Static(id="field-message", markup=False)
                    yield DataTable(id="fields", cursor_type="row")
                with DisclosureScroll(id="field-scroll"):
                    yield Static(classes="pinned-heading", markup=False)
                    yield Static("Field", classes="pane-title")
                    yield Static(id="copy-hint", markup=False)
                    yield Static(id="field-details", markup=False)
                    yield Collapsible(Static(id="field-evidence-text", markup=False),
                                      title="Technical field metadata", id="field-evidence")
            with TabbedContent(id="source-tabs"):
                for key, tab in _TABS.items():
                    with TabPane(tab, id=key):
                        if key == "diagnostics":
                            yield from self.compose_findings()
                        elif key == "files":
                            with DisclosureScroll(id="source-files-scroll"):
                                yield Static(classes="pinned-heading", markup=False)
                                yield Static(id="source-files", markup=False)
                                yield Collapsible(Static(id="source-file-paths", markup=False),
                                                  title="Exact file locations",
                                                  id="source-file-evidence")
                        else:
                            with ReportScroll(id=f"source-{key}-scroll"):
                                yield Static(id=f"source-{key}", markup=False)

    def prepare_view(self, report: dict):
        data = report["data"]
        sampled = data["plan"].get("sources", {})
        sources = {name: sampled.get(name, {"declaration": declaration}) for name, declaration
                   in (data["configuration"] or {}).get("sources", {}).items()}
        return sources, {name: _source_details(source, name, data["origins"])
                         for name, source in sources.items()}

    def _scroll_anchor(self, widget):
        if widget.id == "fields":
            return self._source, self._field, self._visible
        if widget.id == "sources":
            return self._source, tuple(self._sources)
        if widget.id == "field-scroll":
            return (self._source, self._field, self.query_one("#field-details", Static).content,
                    self.query_one("#field-evidence-text", Static).content)
        if widget.id and widget.id.startswith("source-"):
            return self._source, self._source_details.get(self._source, {})
        return super()._scroll_anchor(widget)

    def show_report(self, report: dict, prepared, _previous_report) -> None:
        self._sources, self._source_details = prepared
        verdict = "Inspection has errors" if self.result_code else "Sample inspected"
        if self.saved and not self.result_code:
            verdict = "Inspection recorded"
        self.set_status(verdict, hint="d Diagnostics" if self.result_code else None)
        listing = self.query_one("#sources", OptionList)
        listing.clear_options().add_options(
            Option(Content(f"{name}\n{_scope(source)}"), id=name)
            for name, source in self._sources.items())
        readable = [name for name, source in self._sources.items()
                    if source.get("sample", {}).get("inspected") or source.get("fields")]
        selected = self._source if self._source in self._sources else (
            next(iter(readable or self._sources), None))
        if selected is not None:
            listing.highlighted = listing.get_option_index(selected)
        self._select_source(selected)
        if readable and not self._has_report:
            self.action_pane(self._pane)
        elif not readable:
            self.action_diagnostics()

    def _select_source(self, name):
        same = name == self._source
        previous = self._field if same else None
        self._source = name
        source = self._sources.get(name, {})
        path = source.get("sample", {}).get("path")
        model = source.get("model") or source.get("declaration", {}).get("model")
        format_ = source.get("format")
        kind = " / ".join(item.upper() for item in (model, format_) if item)
        scope = " · ".join(filter(None, (name, kind, _scope(source))))
        if name is None:
            scope = "No source metadata"
        if path:
            scope += f" · {Path(path).name}"
        self.query_one("#source-scope", Static).update(scope)
        details = self._source_details.get(name, {})
        for key in _TABS.keys() - {"diagnostics"}:
            self.query_one(f"#source-{key}", Static).update(details.get(key, _UNKNOWN))
            self.query_one(f"#source-{key}-scroll", VerticalScroll).scroll_home(animate=False)
        self.query_one("#source-file-paths", Static).update(details.get("file_paths", _UNKNOWN))
        if not same:
            self.query_one("#source-file-evidence", Collapsible).collapsed = True
        self._populate_fields(previous)

    @on(OptionList.OptionHighlighted, "#sources")
    def _source_highlighted(self, event: OptionList.OptionHighlighted):
        if (self.result_code is not None and event.option is event.option_list.highlighted_option
                and event.option.id != self._source):
            self._select_source(event.option.id)

    def _populate_fields(self, previous, *, search_only=False):
        # Load Rich only after Textual so a missing UI stack falls back to the text report.
        from rich.text import Text

        source = self._sources.get(self._source, {})
        search = self.query_one("#field-search", Input).value.strip().casefold()
        status = self._filter
        fields = [(identity, _field_cells(source, identity, field))
                  for identity, field in source.get("fields", {}).items()]
        rows = [(identity, cells) for identity, cells in fields
                if (not status or cells[3] == _REQUEST[status])
                and (not search or any(search in text.casefold() for text in cells[:3]))]
        rows.sort(key=lambda row: (row[1][_SORTS[self._sort]].casefold(), row[1][0].casefold()))
        visible = [identity for identity, _ in rows]
        if search_only and visible == self._visible:
            return
        self._visible = visible
        self._groups = _row_groups(fields)
        table = self.query_one("#fields", DataTable)
        table.clear(columns=True)
        for label, width in _FIELD_COLUMNS:
            table.add_column(label, width=width)
        for identity, (name, _, units, request) in rows:
            table.add_row(*(Text(cell, no_wrap=True, overflow="ellipsis") for cell in (
                name, self._groups[identity], "—" if units == _UNKNOWN else units, request)),
                key=identity)
        result = f"{len(rows)} of {len(fields)} fields"
        self.query_one("#field-controls", Static).update(
            f"{result}  / Search  s {self._sort}  f {_REQUEST.get(status, 'All')}")
        message = self.query_one("#field-message", Static)
        message.display = not rows
        if not rows:
            message.update("No matching fields" if source.get("fields") else "No fields reported")
        if self._visible:
            position = self._visible.index(previous) if previous in self._visible else 0
            table.move_cursor(row=position, column=0, animate=False)
        else:
            position = None
        self._show_field(self._visible[position] if position is not None else None)

    @on(DataTable.RowHighlighted, "#fields")
    def _field_highlighted(self, event: DataTable.RowHighlighted):
        row = event.cursor_row
        if (self.result_code is not None and row == event.data_table.cursor_row
                and row < len(self._visible) and self._visible[row] == event.row_key.value
                and event.row_key.value != self._field):
            self._show_field(event.row_key.value)

    @on(DataTable.RowSelected, "#fields")
    def _open_field(self):
        self.action_pane("field-scroll")

    def _show_field(self, identity):
        evidence = self.query_one("#field-evidence", Collapsible)
        if identity != self._field:
            evidence.collapsed = True
        self._field = identity
        self._selector = ""
        self._offer = None
        source = self._sources.get(self._source, {})
        field = source.get("fields", {}).get(identity)
        lines = ["No field selected."]
        technical = []
        evidence.display = bool(field)
        if field:
            name, group, units, status = _field_cells(source, identity, field)
            label = self._groups[identity]
            dims = field.get("dimensions")
            native = (field.get("native_descriptor") or {}).get("native", {})
            shape = native.get("shape")
            grid = source.get("native_grids", {}).get(field.get("grid_id"), {})
            sizes = grid.get("dimensions", {})
            if shape is None and dims is not None and sizes.keys() >= set(dims):
                shape = [sizes[dim] for dim in dims]
            lines = [name, f"Native group: {group}" + (f" (row {label})" if label != group else ""),
                     f"Request: {status} · Units: {units}",
                     f"Dimensions: {', '.join(dims) or 'scalar' if dims is not None else _UNKNOWN}",
                     f"Shape: {shape if shape is not None else _UNKNOWN}", ""]
            selector = next((s for s in source.get("available_selectors", ())
                             if s.get("field_id") == identity), None)
            if selector is not None:
                self._offer = selector
                self._selector = _yaml(selector["variables"])
                lines.extend((f"YAML selector · {selector['field']}",
                              f"Under sources.{self._source}.variables:",
                              indent(self._selector, "  ")))
            else:
                lines.append("No YAML selector reported for this field." if self.saved
                             else "No YAML selector for this field in the sample.")
                conflicts = source.get("provider_conflicts", ())
                lines.append("Competing providers were reported for this entry." if any(
                    item["field_id"] == identity for item in conflicts) else "Reason not reported.")
            lines.extend(("", f"Scope: {_scope(source)}"))
            grids = ", ".join(field.get("grid_ids", ()))
            coords = ", ".join(field.get("coordinate_names", ()))
            technical.extend((f"Coordinates: {coords or _UNKNOWN}", f"Grids: {grids or _UNKNOWN}",
                              f"Dtype: {field.get('dtype') or _UNKNOWN}",
                              f"Role: {field.get('role') or _UNKNOWN}", f"Identity: {identity}"))
            if "levels" in field:
                technical.append(f"Native level labels: {field['levels']}")
            if attrs := field.get("attributes"):
                technical.extend(("", "Observed attributes:", _yaml(attrs)))
        self._show_field_actions()
        self.query_one("#field-details", Static).update("\n".join(lines))
        self.query_one("#field-evidence-text", Static).update("\n".join(technical))
        self.query_one("#field-scroll", VerticalScroll).scroll_home(animate=False)

    def _wide_sidebar(self, size=None):
        size = self.size if size is None else size
        return size.width >= 140 and size.height >= 35

    @on(events.Resize)
    def _fit_inspection(self, event):
        self.screen.set_class(self._wide_sidebar(event.size), "three-pane")

    def _show_pane(self, pane):
        self._pane = pane
        upper = self.query_one("#inspect-upper")
        upper.set_class(pane != "source-tabs", "active-pane")
        upper.set_class(pane in {"variables-pane", "field-scroll"}, "browsing-fields")
        for key in _PANES:
            self.query_one(f"#{key}").set_class(key == pane, "active-pane")

    @on(events.DescendantFocus)
    def _remember_pane(self, event: events.DescendantFocus):
        if self.result_code is not None:
            for element in event.widget.ancestors_with_self:
                if element.id in _PANES:
                    self._show_pane(element.id)
                    break

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        in_search = isinstance(self.focused, Input)
        if action == "back" and in_search:
            return True
        if action == "back" and self.query_one("#field-scroll").has_focus_within:
            return True
        if in_search and action != "interrupt":
            return False
        if action in {"toggle_draft_field", "view_draft"}:
            return self._has_report and not self.busy and not self._stale and not self.saved
        if self.saved and action == "copy_selector":
            return False
        return super().check_action(action, parameters)

    def _focus_sidebar_main(self):
        self._show_pane("variables-pane")
        super()._focus_sidebar_main()

    def action_pane(self, pane):
        if self.result_code is not None:
            if (pane == "sources-pane" and self._sidebar_closed
                    and self._sidebar_available()):
                self.action_toggle_sidebar()
            self._show_pane(pane)
            self.query_one(_PANES[pane]).focus()

    def action_search(self):
        if self.result_code is not None:
            self._show_pane("variables-pane")
            self.query_one("#field-search", Input).focus()

    def action_diagnostics(self):
        if self.result_code is not None:
            self.query_one("#source-tabs", TabbedContent).active = "diagnostics"
            self._show_pane("source-tabs")
            self._focus_finding(False)

    def action_back(self):
        if isinstance(self.focused, Input) or self.query_one("#field-scroll").has_focus_within:
            self.action_pane("variables-pane")
        else:
            super().action_back()

    @on(Input.Changed, "#field-search")
    def _search_changed(self, event: Input.Changed):
        if self.result_code is not None and event.value == event.input.value:
            self._populate_fields(self._field, search_only=True)

    @on(Input.Submitted, "#field-search")
    def _search_submitted(self):
        self.action_pane("variables-pane")

    def action_sort_fields(self):
        if self.result_code is not None:
            items = list(_SORTS)
            self._sort = items[(items.index(self._sort) + 1) % len(items)]
            self._populate_fields(self._field)
            self.action_pane("variables-pane")

    def action_filter_fields(self):
        if self.result_code is not None:
            items = [None, *_REQUEST]
            self._filter = items[(items.index(self._filter) + 1) % len(items)]
            self._populate_fields(self._field)
            self.action_pane("variables-pane")

    def action_copy_selector(self):
        if self.saved:
            return
        if self.busy or self._stale:
            self._notice("Selector not copied", "Use a fresh sample before copying.", "warning")
            return
        if self._sync_selected_field() and self._selector:
            if self._send_copy(self._selector, "YAML selector", "Copy the visible YAML instead."):
                self.query_one("#copy-hint", Static).update("Copy request sent to terminal")

    def _sync_selected_field(self):
        source = self.query_one("#sources", OptionList).highlighted_option
        row = self.query_one("#fields", DataTable).cursor_row
        if source is None or source.id != self._source or not 0 <= row < len(self._visible):
            return False
        # The table cursor can move before its queued RowHighlighted message is handled.
        if self._visible[row] != self._field:
            self._show_field(self._visible[row])
        return True

    def _show_field_actions(self):
        if self.saved:
            return
        actions = []
        if self._selector:
            actions.append("c Copy YAML")
        staged = self._source == self._draft_source and self._field in self._draft
        if staged:
            mark = ("added, not applied" if self._draft[self._field] == self._draft_entry()
                    else "needs review")
            actions.extend((f"Draft: {mark}", "a Remove"))
        elif self._selector:
            actions.append("a Add to draft")
        if self._draft:
            actions.append("v Review draft")
        self.query_one("#copy-hint", Static).update(" · ".join(actions))

    def _draft_entry(self):
        return source_identity(self._sources.get(self._source, {})), self._offer

    def action_toggle_draft_field(self):
        if self.busy or self._stale or self.saved or not self._sync_selected_field():
            return
        if self._draft and self._draft_source != self._source:
            self._notice("Draft belongs to " + self._draft_source,
                         "Review or clear it with v before adding from this source.", "warning")
        elif identity := self._field:
            if identity in self._draft:
                del self._draft[identity]
            elif self._offer is not None:
                self._draft_source = self._source
                self._draft[identity] = self._draft_entry()
            else:
                self._notice("No selector offered", "See field details for the available evidence.",
                             "warning")
            self._show_field_actions()

    def action_view_draft(self):
        if not self.busy and not self._stale and not self.saved:
            source = self._draft_source if self._draft else self._source
            self.push_screen(DraftSelection(source, self._draft, self._sources.get(source, {})),
                             lambda _: self._show_field_actions())
