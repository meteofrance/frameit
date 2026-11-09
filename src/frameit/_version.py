# Copyright 2026 Clément Soufflet, Météo-France
# Licensed under the Apache License, Version 2.0
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def get_frameit_version() -> str:
    try:
        return version("frameit")
    except PackageNotFoundError:
        return "2.0.0rc2"


__version__ = get_frameit_version()
