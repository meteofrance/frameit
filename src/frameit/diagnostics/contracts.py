"""Facts carried between diagnostic admission, reading and publication."""

from dataclasses import dataclass
from pathlib import Path

from frameit.core.reports import Diagnostic, PreflightError


def diagnostic_error(code, path, message, *, expected=None, observed=None, repair=None):
    return PreflightError(
        [
            Diagnostic(
                path,
                message,
                expected,
                observed,
                [repair] if repair else [],
                code=code,
            )
        ]
    )


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
    files: tuple = ()
    reference: object | None = None
    zarr_evidence: dict | None = None
    decode_coords: str = "all"


@dataclass(frozen=True)
class Metric:
    value: float | None = None
    observed: float | None = None
    bound: float | None = None
    bound_kind: str = "none"
    support: str = "not_evaluated"
    comparability: str = "unavailable"
    reasons: tuple[str, ...] = ()
    location: tuple[float, float] | None = None
    offset_m: float | None = None
    ties: int = 0
    valid_samples: int = 0
    candidates: tuple[tuple[float, float], ...] = ()

    @property
    def qualified_value(self):
        return self.value if self.comparability == "qualified" else None


@dataclass(frozen=True)
class DiagnosticResult:
    centre: Centre
    maximum_wind: Metric
    central_pressure: Metric
    gust: Metric
    rmw: Metric
    wind_radii: tuple[Metric, ...]
