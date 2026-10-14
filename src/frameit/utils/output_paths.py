"""Shared layout for artifacts belonging to one simulation run."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputPaths:
    root: Path

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root))

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def products(self) -> Path:
        return self.root / "products"

    @property
    def logs(self) -> Path:
        return self.root / "logs"
