# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
import time
import warnings
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread

_DEFAULT_THIRD_PARTY_LEVELS: dict[str, int] = {
    "pyproj": logging.WARNING,
    "xesmf": logging.WARNING,
    "xesmf.backend": logging.WARNING,
    "urllib3": logging.WARNING,
    "xarray": logging.WARNING,
    "dask": logging.WARNING,
}


class _QuietProgress:
    """Own one passive reporter; only real boundaries update its scalar state."""

    def __init__(self, logger, *, interval=30., clock=time.monotonic):
        if interval <= 0:
            raise ValueError("Progress interval must be positive")
        self.logger, self.interval, self.clock = logger, interval, clock
        self._lock, self._stop = Lock(), Event()
        self._thread = None
        self._started = self._activity = clock()
        self._reported = None
        self._operation = "preparing metadata/selected source plans"
        self._source = None
        self._prepared = self._tracking = self._published = 0

    def update(self, operation, *, source=None, prepared_sources=0,
               tracking_operations=0, published_products=0):
        with self._lock:
            self._operation, self._source = operation, source
            self._prepared += prepared_sources
            self._tracking += tracking_operations
            self._published += published_products
            self._activity = self.clock()

    def reconcile_published(self, count):
        """Use retained parent facts without replaying publication activity."""
        with self._lock:
            self._published = count

    def _report(self, *, force=False, level=logging.INFO):
        with self._lock:
            now = self.clock()
            if not force and self._reported is not None and now - self._reported < self.interval:
                return
            self._reported = now
            try:
                self.logger.log(
                    level, "Progress | %s | source=%s | prepared sources=%d | "
                    "completed tracking operations=%d | published products=%d | "
                    "elapsed=%.1fs | last activity=%.1fs ago",
                    self._operation, self._source or "not known", self._prepared,
                    self._tracking, self._published, now - self._started, now - self._activity)
            except Exception:
                # A broken progress handler must not replace a processing/cleanup error.
                pass

    def _watch(self):
        while True:
            with self._lock:
                delay = max(0., self.interval - (self.clock() - self._reported))
            if self._stop.wait(delay):
                return
            self._report()

    def start(self):
        if self._thread is not None or not self.logger.isEnabledFor(logging.INFO):
            return
        if self._reported is None:
            self._report()
        self._stop.clear()
        self._thread = Thread(target=self._watch, name="frameit-progress", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            if self._thread.ident is not None:
                self._thread.join()
            self._thread = None

    def finish(self, state):
        self.stop()
        self.update(f"Run {state}")
        level = (logging.INFO if state == "complete" else
                 logging.WARNING if state == "incomplete" else logging.ERROR)
        self._report(force=True, level=level)


class FrameitFormatter(logging.Formatter):
    """Compact ordinary records, with source locations available in DEBUG."""

    def __init__(self, *, debug: bool = False, timestamp: bool = False):
        prefix = "%(asctime)s | " if timestamp else ""
        source = "%(name)s:%(lineno)d | " if debug else ""
        super().__init__(prefix + "%(levelname)-7s | " + source + "%(message)s",
                         datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        # Legacy multiline/tabbed messages become aligned, readable continuations.
        rendered = super().format(record).expandtabs(2)
        return rendered.replace("\n", "\n          ")


def configure_warnings(level: str = "INFO") -> None:
    """
    Configure Python warning filters for the active log level.

    DEBUG retains dependency diagnostics. Otherwise suppress only known
    non-actionable performance hints and xarray default-change notices.

    Parameters
    ----------
    level : str, optional
        Active log level string (e.g. "INFO", "DEBUG"). Default "INFO".
    """
    # In DEBUG mode, keep warnings visible
    if str(level).upper() == "DEBUG":
        return

    warnings.filterwarnings(
        "ignore",
        message=r"Input array is not (C|F)_CONTIGUOUS\. Will affect performance\.",
        category=UserWarning,
        module=r"xesmf\..*",
    )
    # xarray uses stacklevel to attribute these warnings to application code,
    # so match the specific message rather than the emitting module.
    warnings.filterwarnings(
        "ignore",
        message=r"The default value of (?:join|compat|coords|data_vars) will change from .*",
        category=FutureWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=(r"In a future version of xarray the default value for "
                 r"(?:join|compat|coords|data_vars) will change from .*"),
        category=FutureWarning,
    )


def configure_third_party_loggers(levels: dict[str, int] | None = None) -> None:
    """
    Set log levels for noisy third-party libraries.

    Only the named loggers are affected; FrameIt loggers are left unchanged.

    Parameters
    ----------
    levels : dict[str, int] or None, optional
        Mapping of logger name to :mod:`logging` level constant.  When None,
        :data:`_DEFAULT_THIRD_PARTY_LEVELS` is used.
    """
    levels = dict(_DEFAULT_THIRD_PARTY_LEVELS) if levels is None else levels
    for name, lvl in levels.items():
        logging.getLogger(name).setLevel(lvl)


def _sanitize_filename_token(token: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    token = str(token).strip()
    return "".join(ch if ch in allowed else "_" for ch in token)


def setup_frameit_logging(
    output_dir: str | Path,
    *,
    level: str = "INFO",
    simu_name: str | None = None,
    date_fmt: str = "%m%dT%H%M",
) -> Path:
    """
    Configure the "frameit" root logger with a console handler and a log file.

    Removes any existing handlers before attaching new ones, so this function
    is safe to call multiple times (e.g. after overriding the log level).
    Also calls :func:`configure_third_party_loggers` and
    :func:`configure_warnings`.

    Parameters
    ----------
    output_dir : str or Path
        Run root; the log file is created in its ``logs`` subdirectory.
    level : str, optional
        Log level string for both handlers (e.g. "INFO", "DEBUG"). Default "INFO".
    simu_name : str or None, optional
        Prefix for the log file name.  Sanitized to ASCII-safe characters.
        Defaults to "frameit" when None.
    date_fmt : str, optional
        :func:`datetime.strftime` format for the timestamp in the file name.
        Default "%m%dT%H%M".

    Returns
    -------
    Path
        Absolute path of the log file that was created.
    """
    from frameit.utils.output_paths import OutputPaths

    output_dir = OutputPaths(Path(output_dir)).logs
    output_dir.mkdir(parents=True, exist_ok=True)

    date_tag = datetime.now().strftime(date_fmt)
    name_tag = _sanitize_filename_token(simu_name) if simu_name else "frameit"
    log_path = output_dir / f"{name_tag}_{date_tag}.log"

    logger = logging.getLogger("frameit")
    logger.setLevel(level)
    logger.propagate = False

    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()

    debug = str(level).upper() == "DEBUG"

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(FrameitFormatter(debug=debug))

    attempt = 0
    while True:
        try:
            fh = logging.FileHandler(log_path, mode="x", encoding="utf-8")
            break
        except FileExistsError:
            # Never append through an occupied path, including an input-file alias.
            attempt += 1
            log_path = output_dir / f"{name_tag}_{date_tag}.{attempt}.log"
    fh.setLevel(level)
    fh.setFormatter(FrameitFormatter(debug=debug, timestamp=True))

    logger.addHandler(sh)
    logger.addHandler(fh)

    configure_third_party_loggers()
    configure_warnings(level)

    return log_path


@contextmanager
def frameit_logging_scope(output_dir, *, level="INFO", simu_name=None):
    """Own handlers; ``None`` provides early stderr without creating run paths."""
    logger = logging.getLogger("frameit")
    previous = list(logger.handlers)
    previous_level, previous_propagate = logger.level, logger.propagate
    third_party_levels = {
        name: logging.getLogger(name).level for name in _DEFAULT_THIRD_PARTY_LEVELS
    }
    for handler in previous:
        logger.removeHandler(handler)
    try:
        with warnings.catch_warnings():
            if output_dir is None:
                logger.setLevel(level)
                logger.propagate = False
                handler = logging.StreamHandler()
                handler.setLevel(level)
                handler.setFormatter(FrameitFormatter(debug=str(level).upper() == "DEBUG"))
                logger.addHandler(handler)
                log_path = None
            else:
                log_path = setup_frameit_logging(output_dir, level=level, simu_name=simu_name)
            def showwarning(message, category, filename, lineno, file=None, line=None):
                if file is not None:
                    file.write(warnings.formatwarning(message, category, filename, lineno, line))
                    return
                logging.getLogger("frameit.warnings").warning(
                    "%s: %s", category.__name__, message,
                )

            warnings.showwarning = showwarning
            yield log_path
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        for handler in previous:
            logger.addHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        for name, saved_level in third_party_levels.items():
            logging.getLogger(name).setLevel(saved_level)
