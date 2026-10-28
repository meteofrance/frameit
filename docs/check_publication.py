"""Reject accidental FA development-history publication using only the standard library."""

from __future__ import annotations

import re
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = re.compile(
    r"fa_epygram_c\d+|fa_(?:p\d+|c\d+|environment)\.ya?ml"
    r"|(?:docs/)?development/fa|fa_\w+_history(?:\.|/)"
    r"|Frozen\s+developer\s+evidence|\bFA\s+P\d+\b|\bEPyGrAM\s+C\d+\b"
    r"|\b(?:stage|increment)\s+[PC]\d+\b",
    re.IGNORECASE,
)
TEXT_SUFFIXES = {".html", ".js", ".txt", ".rst", ".yaml", ".yml", ".json"}


def check_text(path: Path, text: str) -> list[str]:
    match = FORBIDDEN.search(text)
    if match is None:
        return []
    line = text.count("\n", 0, match.start()) + 1
    return [f"{path}:{line}: development-history reference {match.group()!r}"]


def check_artifact(artifact: Path) -> list[str]:
    errors = []
    for name in ("index.html", "searchindex.js", "objects.inv", "_sources/index.rst.txt"):
        if not (artifact / name).is_file():
            errors.append(f"{artifact / name}: missing expected Sphinx product")
    for path in sorted(artifact.rglob("*")):
        if FORBIDDEN.search(path.relative_to(artifact).as_posix()):
            errors.append(f"{path}: development record/catalogue copied into artifact")
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            errors.extend(check_text(path, path.read_text(encoding="utf-8")))
    inventory = artifact / "objects.inv"
    if inventory.is_file():
        try:
            header = inventory.read_bytes().split(b"\n", 4)
            if header[0] != b"# Sphinx inventory version 2":
                raise ValueError("expected Sphinx inventory version 2")
            text = zlib.decompress(header[4]).decode("utf-8")
        except (IndexError, ValueError, zlib.error) as exc:
            errors.append(f"{inventory}: invalid inventory: {exc}")
        else:
            errors.extend(check_text(inventory, text))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python docs/check_publication.py <fresh-sphinx-html-directory>")
        return 2
    artifact = Path(sys.argv[1])
    if not artifact.is_dir():
        print(f"Not a documentation artifact directory: {artifact}")
        return 2
    errors = []
    for source in sorted((ROOT / "docs/source").rglob("*.rst")):
        errors.extend(check_text(source, source.read_text(encoding="utf-8")))
    errors.extend(check_artifact(artifact))
    if errors:
        print("\n".join(errors))
        return 1
    print("Public documentation boundary passed (sources, artifact, search, downloads, inventory).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
