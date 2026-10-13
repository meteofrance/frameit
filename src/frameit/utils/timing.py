# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class RunTimer:
    """
    Lightweight wall-clock timer for FrameIt pipeline sections.

    Attributes
    ----------
    sections : dict[str, float]
        Accumulated elapsed wall-clock time per named section, in seconds.
    _t0 : float or None
        Reference timestamp recorded by :meth:`start`.
    """

    sections: dict[str, float] = field(default_factory=dict)
    _t0: float | None = None

    def start(self) -> None:
        """Record the global start time for :meth:`total_seconds`."""
        self._t0 = time.perf_counter()

    @contextmanager
    def section(self, name: str) -> Iterator[None]:
        """
        Context manager that times a named pipeline section.

        Parameters
        ----------
        name : str
            Section label (e.g. "loading_data", "tracking").  Accumulated if
            the same name is used more than once.

        Yields
        ------
        None
        """
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            self.sections[name] = self.sections.get(name, 0.0) + dt

    def total_seconds(self) -> float:
        """
        Return elapsed seconds since :meth:`start` was called.

        Returns
        -------
        float
            Elapsed wall-clock time in seconds, or NaN if :meth:`start` was
            never called.
        """
        if self._t0 is None:
            return float("nan")
        return time.perf_counter() - self._t0

    def log_summary(self, logger: logging.Logger, *, title: str = "Runtime summary") -> None:
        """
        Log a formatted timing breakdown at INFO level.

        Parameters
        ----------
        logger : logging.Logger
            Logger to write the summary to.
        title : str, optional
            Header line for the summary block. Default "Runtime summary".
        """
        total = self.total_seconds()
        if not (total > 0.0):
            logger.debug("%s: total time undefined.", title)
            return

        accounted = sum(self.sections.values())
        other = max(0.0, total - accounted)

        items: list[tuple[str, float]] = list(self.sections.items())
        if other > 1e-6:
            items.append(("other", other))

        logger.info("%s · %.2f s total", title, total)

        labels = {
            "loading_data": "Input loading", "tracking": "Tracking",
            "extraction": "Cartesian extraction", "polar_projection": "Polar / collocation",
            "Netcdf export": "NetCDF export", "other": "Setup / overhead",
        }

        for name, dt_s in items:
            pct = 100.0 * dt_s / total
            logger.info("  %-22s %8.2f s  %5.1f%%", labels.get(name, name), dt_s, pct)
