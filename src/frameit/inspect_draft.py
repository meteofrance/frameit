"""Collect and review selectors already offered by sampled inspection."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from frameit.report_motion import ReportScroll
from frameit.report_tui import _yaml


def _merge_selectors(offers):
    variables = {}
    for offer in offers:
        for category, selection in offer["variables"].items():
            if category in {"2d", "3d"} and isinstance(selection, list):
                names = variables.setdefault(category, [])
                if not isinstance(names, list):
                    raise ValueError("Cannot combine unqualified and group-qualified 3d selectors.")
                names.extend(name for name in selection if name not in names)
            elif category == "3d" and isinstance(selection, dict):
                groups = variables.setdefault(category, {})
                if not isinstance(groups, dict):
                    raise ValueError("Cannot combine unqualified and group-qualified 3d selectors.")
                for group, spec in selection.items():
                    if not isinstance(spec, dict) or not isinstance(spec.get("names"), list):
                        raise ValueError("Cannot combine an unsupported group selector.")
                    target = groups.setdefault(group, {**spec, "names": []})
                    if any(target.get(key) != spec.get(key)
                           for key in (target.keys() | spec.keys()) - {"names"}):
                        raise ValueError(f"Cannot combine different settings for group {group}.")
                    target["names"].extend(name for name in spec["names"]
                                           if name not in target["names"])
            else:
                raise ValueError("Cannot combine a selector with unrecognized structure.")
    return variables


class DraftSelection(ModalScreen):
    BINDINGS = [
        Binding("c", "copy_draft", "Copy draft"),
        Binding("delete", "remove_entry", "Remove selection"),
        Binding("x", "clear_draft", "Clear"),
        Binding("escape", "dismiss", "Back"),
    ]
    DEFAULT_CSS = """
    DraftSelection { align: center middle; background: $background; }
    DraftSelection > Vertical { width: 80; max-width: 100%; height: 94%; padding: 0 1; }
    DraftSelection OptionList { height: 5; max-height: 35%; }
    #draft-yaml { height: auto; }
    #draft-actions { color: $accent; }
    """

    def __init__(self, source, entries, current_offers):
        super().__init__()
        self.source = source
        self.entries = entries
        self.offers = {offer["field_id"]: offer for offer in current_offers if "field_id" in offer}
        self._fragment = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Draft selection — not applied", markup=False)
            yield Static(id="draft-status", markup=False)
            yield OptionList(id="draft-entries", markup=False, compact=True)
            with ReportScroll(id="draft-preview"):
                yield Static(id="draft-yaml", markup=False)
            yield Static("c Copy  Delete Remove  x Clear  Esc Back",
                         id="draft-actions", markup=False)

    def on_mount(self):
        self._update_draft()

    def _update_draft(self):
        listing = self.query_one("#draft-entries", OptionList)
        current = []
        rows = []
        for identity, entry in self.entries.items():
            matches = self.offers.get(identity) == entry
            if matches:
                current.append(entry)
            status = "Added" if matches else "Needs review"
            rows.append(Option(f"{status} · {entry['field']}", id=identity))
        listing.set_options(rows)
        n = len(rows) - len(current)
        scope = self.source or "No source"
        status = f"{scope} · {len(current)} current"
        if n:
            status += f" · {n} need review (excluded)"
        self.query_one("#draft-status", Static).update(status)
        self._fragment = ""
        try:
            if merged := _merge_selectors(current):
                self._fragment = _yaml({"sources": {self.source: {"variables": merged}}})
            preview = self._fragment or "No current selectors to copy."
        except ValueError as exc:
            preview = str(exc)
        self.query_one("#draft-yaml", Static).update(preview)

    def action_remove_entry(self):
        if option := self.query_one("#draft-entries", OptionList).highlighted_option:
            self.entries.pop(option.id, None)
            self._update_draft()

    def action_clear_draft(self):
        self.entries.clear()
        self._update_draft()

    def action_copy_draft(self):
        if self._fragment:
            self.app._send_copy(self._fragment, "Draft selection", "Use the displayed YAML.")
