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
}


def configure_warnings(level: str = "INFO") -> None:
    """
    Configure Python warning filters for the active log level.

    In DEBUG mode all warnings remain visible; otherwise noisy xESMF
    array-contiguity warnings are suppressed.

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
        Directory where the log file will be created.  Created if absent.
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
    output_dir = Path(output_dir)
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

    fmt = logging.Formatter(
        "%(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    )

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(fmt)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)

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
