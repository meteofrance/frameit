"""Branded activity artwork for the shared terminal report."""

from functools import cache
from math import exp

from textual import constants
from textual.actions import SkipAction
from textual.containers import VerticalScroll
from textual.widgets import Static

# Braille and colour roles sampled offline from the supplied logo prototype.
_LOGO = (
    ("⢀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⠀⣀⣀⣀⣀⣀⡀⠀", "FFFFFFFFFFFFFFFFFFFF"),
    ("⢸⣿⡿⠿⠿⠿⠿⠿⠿⠿⠿⠟⠀⠻⠿⠿⠿⣿⣿⠀", "FFFFFFFFFFFFFFFFFFFF"),
    ("⢸⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀", "FFFFFFFFFFFFFFFFFFFF"),
    ("⢸⣿⣷⣶⣶⣶⣶⣶⣶⣦⠀⠀⠀⠀⠀⠀⠀⠛⠛⠀", "FFFFFFFFFFFFFFFFFFFF"),
    ("⢸⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣷⡄", "FFFFFFFFFFFFFFFFFTTT"),
    ("⢸⣿⡇⠀⠀⠀⠀⠀⠀⠀⣴⣶⣤⠶⠶⠶⠶⠟⠁⠀", "FFFFFFFFFFEEETTTTTTF"),
    ("⠘⠟⢃⡀⣠⣴⠿⠛⠿⠶⠛⠿⠋⠀⠀⠀⠀⣠⣄⠀", "FFFTTTTTTTEEEFFFFFFF"),
    ("⢸⣿⡎⠻⣿⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀", "FFFTTTFFFFFFFFFFFFFF"),
    ("⢸⣿⣷⣶⣶⣶⡆⠀⠀⠀⠀⠀⢀⣶⣶⣶⣶⣿⣿⠀", "FFFFFFFFFFFFFFFFFFFF"),
    ("⠈⠉⠉⠉⠉⠉⠁⠀⠀⠀⠀⠀⠀⠉⠉⠉⠉⠉⠁⠀", "FFFFFFFFFFFFFFFFFFFF"),
)
_COLORS = {"F": "#00978f", "T": "#f79335", "E": "#ec7600"}
_PHASES = 24
_FPS = 12


@cache
def _logo_frame(phase):
    from rich.text import Text

    frame = Text(no_wrap=True, overflow="crop")
    center = None if phase is None else -4 + 28 * phase / (_PHASES - 1)
    for index, (glyphs, roles) in enumerate(_LOGO):
        if index:
            frame.append("\n")
        for x, (glyph, role) in enumerate(zip(glyphs, roles, strict=True)):
            color = _COLORS[role]
            if role == "T" and center is not None:
                glow = exp(-0.5 * ((x - center) / 2.2) ** 2)
                rgb = tuple(round(a + (b - a) * glow)
                            for a, b in zip((160, 83, 34), (255, 199, 116), strict=True))
                color = "#{:02x}{:02x}{:02x}".format(*rgb)
            frame.append(glyph, style=color)
    return frame


class BrandActivity(Static):
    """A cached trajectory pulse; nothing ticks while the mark is hidden."""

    timer = None

    def set_active(self, visible):
        if self.display == visible:
            return
        self.display = visible
        if not visible:
            self._stop()
        elif self.app.animation_level == "full":
            self._frames = tuple(_logo_frame(phase) for phase in range(_PHASES))
            self._phase = 0
            self.update(self._frames[0], layout=False)
            self.timer = self.set_interval(1 / _FPS, self._advance)
        else:
            self.update(_logo_frame(None), layout=False)

    def _advance(self):
        self._phase = (self._phase + 1) % _PHASES
        self.update(self._frames[self._phase], layout=False)

    def _stop(self):
        if self.timer is not None:
            self.timer.stop()
            self.timer = None

    def on_hide(self):
        self._stop()

    def on_unmount(self):
        self._stop()


class ReportScroll(VerticalScroll):
    """Use short native page moves without replacing row or pointer navigation."""

    def action_page_down(self):
        self._page(self.scroll_page_down)

    def action_page_up(self):
        self._page(self.scroll_page_up)

    def _page(self, move):
        if not self.allow_vertical_scroll:
            raise SkipAction()
        move(animate=constants.SMOOTH_SCROLL and self.app.animation_level != "none",
             duration=.12, easing="out_cubic")
