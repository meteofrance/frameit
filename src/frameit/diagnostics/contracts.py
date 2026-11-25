"""Facts carried between diagnostic admission, reading and publication."""

from dataclasses import dataclass
from pathlib import Path

from frameit.core.reports import Diagnostic, PreflightError


def diagnostic_error(code, path, message, *, expected=None, observed=None, repair=None):
    return PreflightError([Diagnostic(
        path, message, expected, observed, [repair] if repair else [], code=code,
    )])


@dataclass(frozen=True)
class Centre:
    time: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class ParentSnapshot:
    root: Path
    attempt_id: str
    identity_scheme: str
    centres: tuple[Centre, ...]
    calendar: str
    centre_origin: str
    effective: dict
    sources: dict
    products: tuple[dict, ...]
    fingerprints: tuple[tuple[Path, str], ...]


@dataclass(frozen=True)
class DiagnosticPlan:
    """Backend-specific selectors are held as frozen sample descriptors, not open views."""

    parent: ParentSnapshot
    request: dict
    facts: dict
    samples: tuple = ()
