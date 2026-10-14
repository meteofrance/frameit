# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import logging
import warnings
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

_DEFAULT_THIRD_PARTY_LEVELS: dict[str, int] = {
    "matplotlib": logging.WARNING,
    "fiona": logging.WARNING,
    "pyproj": logging.WARNING,
    "xesmf": logging.WARNING,
    "xesmf.backend": logging.WARNING,
    "urllib3": logging.WARNING,
    "xarray": logging.WARNING,
    "dask": logging.WARNING,
}


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

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(FrameitFormatter(debug=debug, timestamp=True))

    logger.addHandler(sh)
    logger.addHandler(fh)

    configure_third_party_loggers()
    configure_warnings(level)

    return log_path


@contextmanager
def frameit_logging_scope(output_dir, *, level="INFO", simu_name=None):
    """Own execution handlers and restore the caller's logging state."""
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
