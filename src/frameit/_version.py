# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def source_project() -> tuple[Path, str] | None:
    """Find the source project that owns this imported module."""
    try:
        package = Path(__file__).resolve().parent
        if package.name != "frameit" or package.parent.name != "src":
            return None
        root = package.parent.parent
        with (root / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream).get("project")
    except (OSError, tomllib.TOMLDecodeError, UnicodeError):
        return None

    if isinstance(project, dict) and project.get("name") == "frameit":
        release = project.get("version")
        if isinstance(release, str) and release.strip():
            return root, release
    return None


def get_frameit_version() -> str:
    if project := source_project():
        return project[1]
    try:
        return version("frameit")
    except PackageNotFoundError:
        return "2.0.0rc4"


__version__ = get_frameit_version()
