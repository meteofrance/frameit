"""Read-only terminal explorer for one metadata sample per configured source."""

from pathlib import Path
from textwrap import indent

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import DataTable, Input, OptionList, Static, TabbedContent, TabPane
from textual.widgets.option_list import Option

from frameit.report_tui import ReportApp, _time_label, _yaml

_UNKNOWN = "Not reported"
_REQUEST = {"requested": "Requested", "not_requested": "Not requested", "unresolved": "Unresolved"}
_SORTS = {"Name": 0, "Units": 1, "Group": 3}
_TABS = {
    "overview": "Overview", "coordinates": "Coordinates", "time": "Time", "grids": "Grids",
    "files": "Files", "origins": "Origins", "diagnostics": "Diagnostics",
}
_PANES = {
    "sources-pane": "#sources", "variables-pane": "#fields", "field-scroll": "#field-scroll",
    "source-tabs": "#source-tabs ContentTabs",
}


def _scope(source):
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
    lines = ["Observed in sample"]
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
    overview = [f"Source: {name}", f"Sample: {sample_path or _UNKNOWN}", _scope(source),
                f"Model: {source.get('model') or _UNKNOWN}",
                f"Format: {source.get('format') or _UNKNOWN}",
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
                    "not_inspected": "Not inspected"}
    files = []
    for entry in source.get("file_inventory", ()):
        files.append(f"{dispositions[entry['status']]} · {entry['path']}")
        files.extend(f"  Alias · {alias}" for alias in entry.get("aliases", ()))
    files.extend(f"Excluded · {path}" for path in source.get("excluded_files", ()))
    declarations = source.get("declaration", {}).get("field_metadata")
    setting_origins = {key: value for key, value in origins.items()
                       if key.startswith(f"sources.{name}.")}
    return {
        "overview": "\n".join(overview),
        "coordinates": "\n\n".join(coordinates) or _UNKNOWN,
        "time": _time_details(source),
        "grids": "\n\n".join(grids) or _UNKNOWN,
        "files": "\n".join(files) or _UNKNOWN,
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
    dimensions = field.get("dimensions")
    return (name, str(attrs.get("units") or _UNKNOWN),
            _UNKNOWN if dimensions is None else ", ".join(dimensions) or "scalar",
            field.get("group") or _UNKNOWN,
            _REQUEST.get(source.get("request_status", {}).get(identity), _UNKNOWN))


class InspectionApp(ReportApp):
    TITLE = "FrameIt / inspect"
    LOG_CONTEXT = "inspection"
    STAGES = {**ReportApp.STAGES, "metadata": "Reading sample metadata",
              "report": "Preparing sample report"}
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (120, "-wide")]
    VERTICAL_BREAKPOINTS = [(0, "-short"), (30, "-tall")]
    BINDINGS = [
        Binding("1", "pane('sources-pane')", "Sources"),
        Binding("2", "pane('variables-pane')", "Fields"),
        Binding("3", "pane('field-scroll')", "Detail"),
        Binding("4", "pane('source-tabs')", "Tabs"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
        Binding("slash", "search", show=False),
        Binding("escape", "leave_search", show=False),
        Binding("s", "sort_fields", show=False),
        Binding("f", "filter_fields", show=False),
        Binding("c", "copy_selector", show=False),
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
    Screen.-wide.-tall #inspect-upper { height: 3fr; display: block; }
    Screen.-wide.-tall #source-tabs { height: 2fr; display: block; }
    Screen.-wide.-tall #inspect-upper > Widget { display: block; }
    Screen.-wide.-tall #sources-pane { width: 23; border-right: solid $accent 30%; }
    Screen.-wide.-tall #field-scroll { width: 38; border-left: solid $accent 30%; }
    .pane-title { height: 1; text-style: bold; }
    #sources, #fields { height: 1fr; }
    #sources:focus > .option-list--option-highlighted {
        background: #102440;
        color: $foreground;
        text-style: bold underline;
    }
    #fields > .datatable--cursor {
        background: #102440;
        color: $foreground;
        text-style: bold;
    }
    #fields:focus > .datatable--cursor { text-style: bold underline; }
    #field-search { height: 1; border: none; padding: 0 1; }
    #field-search:focus { border: none; background: #102440; }
    #field-controls, #copy-hint { height: auto; color: $text-muted; }
    #field-message { height: auto; color: $text-muted; }
    """

    def __init__(self, config: Path, collect):
        super().__init__(config, collect)
        self._sources = {}
        self._source_details = {}
        self._source = None
        self._field = None
        self._visible = []
        self._pane = "variables-pane"
        self._sort = "Name"
        self._filter = None
        self._selector = ""

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
                with VerticalScroll(id="field-scroll"):
                    yield Static("Field", classes="pane-title")
                    yield Static(id="copy-hint", markup=False)
                    yield Static(id="field-details", markup=False)
            with TabbedContent(id="source-tabs"):
                for key, tab in _TABS.items():
                    with TabPane(tab, id=key):
                        if key == "diagnostics":
                            yield from self.compose_findings()
                        else:
                            with VerticalScroll(id=f"source-{key}-scroll"):
                                yield Static(id=f"source-{key}", markup=False)

    def prepare_view(self, report: dict):
        data = report["data"]
        sampled = data["plan"].get("sources", {})
        sources = {name: sampled.get(name, {"declaration": declaration}) for name, declaration
                   in (data["configuration"] or {}).get("sources", {}).items()}
        return sources, {name: _source_details(source, name, data["origins"])
                         for name, source in sources.items()}

    def show_report(self, report: dict, prepared) -> None:
        self._sources, self._source_details = prepared
        verdict = "Inspection has errors" if self.result_code else "Sample inspected"
        self.set_status(verdict)
        listing = self.query_one("#sources", OptionList)
        listing.clear_options().add_options(
            Option(Content(f"{name}\n{_scope(source)}"), id=name)
            for name, source in self._sources.items())
        readable = [name for name, source in self._sources.items()
                    if source.get("sample", {}).get("inspected")]
        selected = self._source if self._source in self._sources else (
            next(iter(readable or self._sources), None))
        if selected is not None:
            listing.highlighted = listing.get_option_index(selected)
        self._select_source(selected)
        if readable:
            self.action_pane(self._pane)
        else:
            self.query_one("#source-tabs", TabbedContent).active = "diagnostics"
            self._show_pane("source-tabs")
            self.query_one("#finding-list", OptionList).focus()

    def _select_source(self, name):
        previous = self._field if name == self._source else None
        self._source = name
        source = self._sources.get(name, {})
        path = source.get("sample", {}).get("path")
        scope = f"{name} · {_scope(source)}" if name is not None else "No source metadata"
        if path:
            scope += f" · {Path(path).name}"
        self.query_one("#source-scope", Static).update(scope)
        details = self._source_details.get(name, {})
        for key in _TABS.keys() - {"diagnostics"}:
            self.query_one(f"#source-{key}", Static).update(details.get(key, _UNKNOWN))
            self.query_one(f"#source-{key}-scroll", VerticalScroll).scroll_home(animate=False)
        self._populate_fields(previous)

    @on(OptionList.OptionHighlighted, "#sources")
    def _source_highlighted(self, event: OptionList.OptionHighlighted):
        if (self.result_code is not None and event.option is event.option_list.highlighted_option
                and event.option.id != self._source):
            self._select_source(event.option.id)

    def _populate_fields(self, previous):
        # Load Rich only after Textual so a missing UI stack falls back to the text report.
        from rich.text import Text

        source = self._sources.get(self._source, {})
        search = self.query_one("#field-search", Input).value.strip().casefold()
        status = self._filter
        rows = []
        for identity, field in source.get("fields", {}).items():
            cells = _field_cells(source, identity, field)
            if status and cells[-1] != _REQUEST[status]:
                continue
            if search and not any(search in text.casefold() for text in cells[:4]):
                continue
            rows.append((identity, cells))
        rows.sort(key=lambda row: (row[1][_SORTS[self._sort]].casefold(), row[1][0].casefold()))
        table = self.query_one("#fields", DataTable)
        table.clear(columns=True).add_columns("Name", "Units", "Dims", "Group", "Request")
        self._visible = [identity for identity, _ in rows]
        for identity, cells in rows:
            table.add_row(*map(Text, cells), key=identity)
        self.query_one("#field-controls", Static).update(
            f"/ Search   s Sort: {self._sort}   f Filter: {_REQUEST.get(status, 'All')}")
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
                and row < len(self._visible) and self._visible[row] == event.row_key.value):
            self._show_field(event.row_key.value)

    def _show_field(self, identity):
        self._field = identity
        self._selector = ""
        source = self._sources.get(self._source, {})
        field = source.get("fields", {}).get(identity)
        lines = ["No field selected."]
        if field:
            name, units, dims, group, status = _field_cells(source, identity, field)
            lines = [name, f"Units: {units}", f"Request: {status}", ""]
            selector = next((s for s in source.get("available_selectors", ())
                             if s.get("field_id") == identity), None)
            if selector is not None:
                self._selector = _yaml(selector["variables"])
                lines.extend((f"YAML selector · {selector['field']}",
                              f"Under sources.{self._source}.variables:",
                              indent(self._selector, "  ")))
            else:
                lines.append("No YAML selector for this field in the sample.")
            grids = ", ".join(field.get("grid_ids", ()))
            coords = ", ".join(field.get("coordinate_names", ()))
            native = (field.get("native_descriptor") or {}).get("native", {})
            shape = native.get("shape")
            grid = source["native_grids"].get(field.get("grid_id"), {})
            sizes = grid.get("dimensions", {})
            if shape is None and field["dimensions"] is not None:
                if sizes.keys() >= set(field["dimensions"]):
                    shape = [sizes[dim] for dim in field["dimensions"]]
            lines.extend(("", f"Dimensions: {dims}", f"Native group: {group}",
                          f"Shape: {shape if shape is not None else _UNKNOWN}",
                          f"Coordinates: {coords or _UNKNOWN}", f"Grids: {grids or _UNKNOWN}",
                          f"Dtype: {field.get('dtype') or _UNKNOWN}",
                          f"Role: {field.get('role') or _UNKNOWN}", f"Identity: {identity}"))
            if "levels" in field:
                lines.append(f"Native level labels: {field['levels']}")
            if attrs := field.get("attributes"):
                lines.extend(("", "Observed attributes:", _yaml(attrs)))
        self.query_one("#copy-hint", Static).update("c Copy YAML" if self._selector else "")
        self.query_one("#field-details", Static).update("\n".join(lines))
        self.query_one("#field-scroll", VerticalScroll).scroll_home(animate=False)

    def _show_pane(self, pane):
        self._pane = pane
        self.query_one("#inspect-upper").set_class(pane != "source-tabs", "active-pane")
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
        if action == "leave_search":
            return in_search
        if in_search and action != "interrupt":
            return False
        return super().check_action(action, parameters)

    def action_pane(self, pane):
        if self.result_code is not None:
            self._show_pane(pane)
            self.query_one(_PANES[pane]).focus()

    def action_search(self):
        if self.result_code is not None:
            self._show_pane("variables-pane")
            self.query_one("#field-search", Input).focus()

    def action_leave_search(self):
        self.action_pane("variables-pane")

    @on(Input.Changed, "#field-search")
    def _search_changed(self):
        if self.result_code is not None:
            self._populate_fields(self._field)

    @on(Input.Submitted, "#field-search")
    def _search_submitted(self):
        self.action_leave_search()

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
        if self.result_code is None:
            return
        source = self.query_one("#sources", OptionList).highlighted_option
        row = self.query_one("#fields", DataTable).cursor_row
        if source is None or source.id != self._source or not 0 <= row < len(self._visible):
            return
        # The table cursor can move before its queued RowHighlighted message is handled.
        if self._visible[row] != self._field:
            self._show_field(self._visible[row])
        if self._selector:
            self.copy_to_clipboard(self._selector)
            self.query_one("#copy-hint", Static).update("Copy request sent to terminal")
