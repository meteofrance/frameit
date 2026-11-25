"""Shared layout for artifacts belonging to one simulation run."""

from dataclasses import dataclass
from pathlib import Path

from frameit.utils.diagnostics import tag_error

TRAJECTORY_RECORD = "records/trajectory.nc"


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

    def trajectory_record(self) -> Path:
        path = self.root / TRAJECTORY_RECORD
        if any(entry.is_symlink() for entry in (self.root, path.parent, path)):
            raise tag_error(ValueError(f"Trajectory record path contains a symlink: {path}"),
                            "E1805")
        if path.parent.exists() and not path.parent.is_dir():
            raise tag_error(ValueError(f"Trajectory record requires a directory: {path.parent}"),
                            "E1805")
        return path

    def planned_products(self, descriptors):
        """Resolve the common plan without sanitizing or inventing file names."""
        paths, seen = [], set()
        for item in descriptors:
            relative = Path(item["path"])
            if (relative.is_absolute() or ".." in relative.parts
                    or len(relative.parts) != 2 or relative.parts[0] != "products"
                    or "\\" in str(relative)
                    or any(ord(char) < 32 or ord(char) == 127 for char in str(relative))):
                raise tag_error(ValueError(f"Unsafe planned product path: {relative}"), "E1805")
            path = self.root / relative
            if any(part.is_symlink() for part in (path, *path.parents)
                   if part == self.root or part.is_relative_to(self.root)):
                raise tag_error(ValueError(f"Product path contains a symlink: {relative}"), "E1805")
            destination = path.resolve()
            if not destination.is_relative_to(self.products.resolve()):
                raise tag_error(ValueError(f"Product path escapes products directory: {relative}"),
                                "E1805")
            if destination in seen:
                raise tag_error(ValueError(f"Product paths collide: {relative}"), "E1805")
            seen.add(destination)
            paths.append(path)
        return paths
