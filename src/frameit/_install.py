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


def _read_python(arguments, *, cwd, env, purpose):
    try:
        return subprocess.run([sys.executable, *arguments], cwd=cwd, env=env, check=True,
                              capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (getattr(exc, "stderr", None) or str(exc)).strip()
        raise ValueError(f"{purpose} could not verify the install: {detail}. "
                         "Activate the matching editable environment.") from exc


def _pip_version(checkout, site_packages, env):
    shown = _read_python(["-m", "pip", "show", "frameit"], cwd=checkout,
                         env=env, purpose="pip show")
    fields = dict(line.split(": ", 1) for line in shown.splitlines() if ": " in line)
    location = Path(fields.get("Location", ""))
    editable = Path(fields.get("Editable project location", ""))
    if not location.is_absolute() or location.resolve() not in site_packages:
        raise ValueError(f"pip show selected FrameIt outside this interpreter's site-packages "
                         f"({fields.get('Location', 'unknown')}). Activate the matching "
                         "editable environment and remove any conflicting path override.")
    if not editable.is_absolute() or editable.resolve() != checkout:
        raise ValueError("pip show did not select the verified editable checkout. "
                         "Activate the matching editable environment.")
    return fields.get("Version", "unavailable")


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
           if not key.startswith("PYTHON") and key != "__PYVENV_LAUNCHER__"
           and (not key.startswith("PIP_") or key == "PIP_REQUIRE_VIRTUALENV")}
    env.update(PYTHONNOUSERSITE="1", PYTHONSAFEPATH="1", PYTHONDONTWRITEBYTECODE="1",
               PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    probe = _read_python(
        ["-c", "import json, sysconfig; print(json.dumps(["
               "sysconfig.get_path('purelib'), sysconfig.get_path('platlib')]))"],
        cwd=checkout, env=env, purpose="Python install paths",
    )
    try:
        paths = json.loads(probe)
        if not isinstance(paths, list) or not all(Path(path).is_absolute() for path in paths):
            raise ValueError
        child_site_packages = {Path(path).resolve() for path in paths}
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("Cannot verify the child interpreter's site-packages. "
                         "Activate the matching editable environment.") from exc
    if child_site_packages != site_packages:
        raise ValueError("The child interpreter would install to different site-packages. "
                         "Activate the matching editable environment.")
    _pip_version(checkout, site_packages, env)

    # A trailing separator prevents pip treating a bracketed directory as an extra.
    editable_path = str(checkout) + os.sep if checkout.name.endswith("]") else str(checkout)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation",
             "-e", editable_path],
            cwd=checkout, env=env, check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(
            f"pip install failed: {exc}. Check pip's output and the build tools "
            "in the active environment, then retry `frameit refresh-install`."
        ) from exc

    installed_release = _pip_version(checkout, site_packages, env)
    if installed_release != release:
        raise ValueError(f"pip show reports FrameIt {installed_release}; expected {release}. "
                         "Check for conflicting installs in the active environment.")
    return release
