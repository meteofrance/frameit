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

    def planned_products(self, descriptors):
        """Resolve the common plan without sanitizing or inventing file names."""
        paths, seen = [], set()
        for item in descriptors:
            relative = Path(item["path"])
            if (relative.is_absolute() or ".." in relative.parts
                    or len(relative.parts) != 2 or relative.parts[0] != "products"
                    or "\\" in str(relative)
                    or any(ord(char) < 32 or ord(char) == 127 for char in str(relative))):
                raise ValueError(f"Unsafe planned product path: {relative}")
            path = self.root / relative
            if any(part.is_symlink() for part in (path, *path.parents)
                   if part == self.root or part.is_relative_to(self.root)):
                raise ValueError(f"Product path contains a symlink: {relative}")
            destination = path.resolve()
            if not destination.is_relative_to(self.products.resolve()):
                raise ValueError(f"Product path escapes products directory: {relative}")
            if destination in seen:
                raise ValueError(f"Product paths collide: {relative}")
            seen.add(destination)
            paths.append(path)
        return paths
