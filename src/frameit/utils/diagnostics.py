"""Stable IDs for errors and warnings that FrameIt reports."""

import errno
from argparse import ArgumentParser
from typing import NoReturn

CODE_TOPICS: dict[str, str] = {
    "E0001": "start",
    "E0002": "run",
    "E0999": "start",
    "E1001": "start",
    "E1002": "start",
    "E1003": "start",
    "E1004": "start",
    "E1005": "start",
    "E1006": "start",
    "E1007": "inputs",
    "E1008": "inputs",
    "E1101": "configuration",
    "E1102": "configuration",
    "E1103": "configuration",
    "E1104": "configuration",
    "E1105": "configuration",
    "E1106": "configuration",
    "E1107": "configuration",
    "E1201": "inputs",
    "E1202": "inputs",
    "E1203": "inputs",
    "E1204": "inputs",
    "E1205": "inputs",
    "E1206": "inputs",
    "E1207": "inputs",
    "E1301": "fields",
    "E1302": "fields",
    "E1303": "fields",
    "E1304": "fields",
    "E1305": "fields",
    "E1306": "fields",
    "E1307": "fields",
    "E1308": "fields",
    "E1310": "fields",
    "E1401": "time",
    "E1402": "time",
    "E1403": "time",
    "E1404": "time",
    "E1405": "time",
    "E1406": "time",
    "E1501": "regions",
    "E1502": "regions",
    "E1503": "regions",
    "E1504": "regions",
    "E1601": "polar",
    "E1602": "polar",
    "E1603": "polar",
    "E1604": "polar",
    "E1701": "run",
    "E1702": "run",
    "E1801": "outputs",
    "E1802": "outputs",
    "E1803": "outputs",
    "E1804": "outputs",
    "E1805": "outputs",
    "E1806": "outputs",
    "E1807": "outputs",
    "E1808": "outputs",
    "E1809": "outputs",
    "E1810": "outputs",
    "E1901": "run",
    "E1902": "run",
    "E1903": "run",
    "E2001": "diagnostics",
    "E2002": "diagnostics",
    "E2003": "diagnostics",
    "E2004": "diagnostics",
    "E2005": "diagnostics",
    "W1001": "start",
    "W1201": "inputs",
    "W1202": "inputs",
    "W1203": "inputs",
    "W1301": "fields",
    "W1302": "fields",
    "W1303": "fields",
    "W1304": "fields",
    "W1305": "fields",
    "W1306": "fields",
    "W1307": "fields",
    "W1401": "time",
    "W1402": "time",
    "W1501": "regions",
    "W1502": "regions",
    "W1503": "regions",
    "W1504": "regions",
    "W1505": "regions",
    "W1506": "regions",
    "W1507": "regions",
    "W1601": "polar",
    "W1602": "polar",
    "W1603": "polar",
    "W1801": "outputs",
    "W1901": "run",
    "W2001": "diagnostics",
    "W2002": "diagnostics",
}

UNEXPECTED_ERROR = "E0999"


def diagnostic_path(code: str) -> str:
    return f"troubleshooting/{CODE_TOPICS[code]}.html#{code.lower()}"


def format_message(code: str, message: str) -> str:
    diagnostic_path(code)  # Require an entry for every emitted code.
    return f"[{code}] {message}"


def format_help(code: str, message: str) -> str:
    return f"{format_message(code, message)}\nTroubleshooting: {diagnostic_path(code)}"


class FrameItArgumentParser(ArgumentParser):
    def error(self, message: str) -> NoReturn:
        super().error(format_help("E0001", message))


def tag_error[ExcT: BaseException](exc: ExcT, code: str) -> ExcT:
    """Add a code without changing the exception type, arguments, or cause."""
    note = format_message(code, "FrameIt diagnostic")
    if not code.startswith("E"):
        raise ValueError(f"Expected an error code, not {code}")
    if exception_code(exc) != UNEXPECTED_ERROR or getattr(exc, "frameit_code", None) == code:
        return exc
    prior_note = format_message(UNEXPECTED_ERROR, "FrameIt diagnostic")
    if prior_note in getattr(exc, "__notes__", ()):
        exc.__notes__.remove(prior_note)
    exc.frameit_code = code
    exc.add_note(note)
    return exc


def exception_code(exc: BaseException) -> str:
    """Read owned codes or explicit resource failures, not message text."""
    seen = set()
    cause = exc
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        code = getattr(cause, "frameit_code", None)
        if isinstance(code, str) and code.startswith("E") and code in CODE_TOPICS:
            if code != UNEXPECTED_ERROR:
                return code
        if isinstance(cause, KeyboardInterrupt):
            return "E0002"
        if isinstance(cause, MemoryError):
            return "E1702"
        if isinstance(cause, OSError) and cause.errno in (errno.ENOSPC, errno.EDQUOT):
            return "E1810"
        cause = cause.__cause__
    return UNEXPECTED_ERROR
