"""Stable IDs for errors and warnings that FrameIt reports."""

CODE_TOPICS: dict[str, str] = {
    "E0001": "start",
    "E0999": "start",
    "E1001": "start",
    "E1101": "configuration",
    "E1102": "configuration",
    "E1103": "configuration",
    "E1104": "configuration",
    "E1105": "configuration",
    "E1106": "configuration",
    "E1107": "configuration",
}

UNEXPECTED_ERROR = "E0999"


def diagnostic_path(code: str) -> str:
    return f"troubleshooting/{CODE_TOPICS[code]}.html#{code.lower()}"


def format_message(code: str, message: str) -> str:
    diagnostic_path(code)  # Require an entry for every emitted code.
    return f"[{code}] {message}"


def tag_error[ExcT: BaseException](exc: ExcT, code: str) -> ExcT:
    """Add a code without changing the exception type, arguments, or cause."""
    note = format_message(code, "FrameIt diagnostic")
    if not code.startswith("E"):
        raise ValueError(f"Expected an error code, not {code}")
    if exception_code(exc) != UNEXPECTED_ERROR or getattr(exc, "frameit_code", None) == code:
        return exc
    if getattr(exc, "frameit_code", None) == UNEXPECTED_ERROR:
        exc.__notes__.remove(format_message(UNEXPECTED_ERROR, "FrameIt diagnostic"))
    exc.frameit_code = code
    exc.add_note(note)
    return exc


def exception_code(exc: BaseException) -> str:
    """Read codes from the failure and its explicit causes, not from message text."""
    seen = set()
    cause = exc
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        code = getattr(cause, "frameit_code", None)
        if isinstance(code, str) and code.startswith("E") and code in CODE_TOPICS:
            if code != UNEXPECTED_ERROR:
                return code
        cause = cause.__cause__
    return UNEXPECTED_ERROR
