"""Explicit pip refresh of the active editable installation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
from importlib.metadata import distributions
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

from frameit._version import source_project


def _editable_checkout(site_packages: set[Path]) -> Path:
    installations = list(distributions(name="frameit", path=list(site_packages)))
    if not installations:
        raise ValueError("There is no FrameIt install in this interpreter's site-packages.")
    if len(installations) != 1:
        raise ValueError("There are multiple FrameIt installs in this interpreter's site-packages.")

    install = installations[0]
    try:
        direct_url = json.loads(install.read_text("direct_url.json") or "{}")
        installer = (install.read_text("INSTALLER") or "").strip()
        if installer != "pip" or direct_url["dir_info"]["editable"] is not True:
            raise ValueError
        location = urlsplit(direct_url["url"])
        if (location.scheme != "file" or location.netloc not in {"", "localhost"}
                or location.query or location.fragment):
            raise ValueError
        checkout = Path(url2pathname(location.path))
        if not checkout.is_absolute():
            raise ValueError
        return checkout.resolve()
    except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError) as exc:
        raise ValueError("FrameIt needs a pip editable install with a local checkout recorded "
                         "in direct_url.json.") from exc


def refresh_editable_install() -> str:
    """Refresh installed metadata and return the version reported by a fresh pip."""
    site_packages = {
        Path(sysconfig.get_path(key)).resolve() for key in ("purelib", "platlib")
    }
    try:
        project = source_project()
        if project is None:
            raise ValueError("The imported FrameIt is outside an identifiable source checkout "
                             "(for example, a wheel install).")
        checkout, release = project
        installed_checkout = _editable_checkout(site_packages)
        if installed_checkout != checkout:
            raise ValueError(f"The editable installation points to a different checkout: "
                             f"{installed_checkout}. The imported code is from {checkout}.")
    except ValueError as exc:
        raise ValueError(f"{exc} Activate the matching editable environment and check "
                         "`python -m pip show frameit`.") from exc

    # Import and pip overrides could shadow metadata or redirect the installation.
    env = {key: value for key, value in os.environ.items()
           if key != "PYTHONPATH"
           and (not key.startswith("PIP_") or key == "PIP_REQUIRE_VIRTUALENV")}
    env.update(PYTHONNOUSERSITE="1", PYTHONSAFEPATH="1", PIP_CONFIG_FILE=os.devnull,
               PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    pip = [sys.executable, "-m", "pip"]
    try:
        subprocess.run(
            [*pip, "install", "--no-deps", "--no-build-isolation", "-e", str(checkout)],
            cwd=checkout, env=env, check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(
            f"pip install failed: {exc}. Check pip's output and the build tools "
            "in the active environment, then retry `frameit refresh-install`."
        ) from exc

    try:
        shown = subprocess.run([*pip, "show", "frameit"], cwd=checkout, env=env, check=True,
                               capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (getattr(exc, "stderr", None) or str(exc)).strip()
        raise ValueError(f"pip show could not verify the refreshed install: {detail}. "
                         "Check `python -m pip show frameit` in the active environment.") from exc
    fields = dict(line.split(": ", 1) for line in shown.stdout.splitlines() if ": " in line)
    installed_release = fields.get("Version", "unavailable")
    if installed_release != release:
        raise ValueError(f"pip show reports FrameIt {installed_release}; expected {release}. "
                         "Check for conflicting installs in the active environment.")
    if location := fields.get("Location"):
        if Path(location).resolve() not in site_packages:
            raise ValueError(f"pip show reports FrameIt outside this interpreter's site-packages: "
                             f"{location}. Check for conflicting installs.")
    return release
