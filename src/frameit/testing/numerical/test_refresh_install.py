"""Exercise refresh-install with on-disk install evidence and a fake pip boundary."""

import json
import subprocess
import sys
import sysconfig

import pytest

from frameit import _version, cli


@pytest.fixture
def installation(tmp_path, monkeypatch):
    checkout = tmp_path / "FrameIt checkout"
    module = checkout / "src/frameit/_version.py"
    module.parent.mkdir(parents=True)
    module.touch()
    (checkout / "pyproject.toml").write_text('[project]\nname = "frameit"\nversion = "2.0.0rc4"\n')
    monkeypatch.setattr(_version, "__file__", str(module))
    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()
    get_path = sysconfig.get_path

    def scheme_path(name, *args, **kwargs):
        if name in {"purelib", "platlib"}:
            return str(site_packages)
        return get_path(name, *args, **kwargs)

    monkeypatch.setattr(sysconfig, "get_path", scheme_path)
    monkeypatch.chdir(tmp_path)
    return checkout, site_packages


def _install_metadata(site_packages, release, checkout):
    metadata = site_packages / f"frameit-{release}.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(f"Name: frameit\nVersion: {release}\n")
    (metadata / "INSTALLER").write_text("pip\n")
    if checkout is not None:
        (metadata / "direct_url.json").write_text(json.dumps({
            "url": checkout.as_uri(), "dir_info": {"editable": True},
        }))


def _refresh(capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main(["refresh-install"])
    return caught.value.code, capsys.readouterr()


def test_refresh_confirms_pip_version_in_separate_process(installation, monkeypatch, capsys):
    checkout, site_packages = installation
    alias = checkout.with_name("checkout-alias")
    alias.symlink_to(checkout, target_is_directory=True)
    _install_metadata(site_packages, "2.0.0rc2", alias)
    monkeypatch.setenv("PYTHONPATH", str(checkout / "src"))
    monkeypatch.setenv("PIP_TARGET", str(checkout / "other-target"))
    calls = []

    def pip(args, **kwargs):
        calls.append(args)
        assert not kwargs.get("shell")
        assert "PYTHONPATH" not in kwargs["env"]
        assert "PIP_TARGET" not in kwargs["env"]
        return subprocess.CompletedProcess(args, 0, stdout="Name: frameit\nVersion: 2.0.0rc4\n")

    monkeypatch.setattr(subprocess, "run", pip)
    code, output = _refresh(capsys)
    assert code == 0 and "2.0.0rc4" in output.out and not output.err
    assert calls == [
        [sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation",
         "-e", str(checkout.resolve())],
        [sys.executable, "-m", "pip", "show", "frameit"],
    ]


@pytest.mark.parametrize(("kind", "message"), [
    ("wheel", "editable"),
    ("other-checkout", "different checkout"),
    ("source-egg-info", "site-packages"),
    ("duplicate", "multiple"),
    ("ambiguous-source", "source checkout"),
    ("broken-url", "direct_url.json"),
])
def test_unverified_install_is_refused(installation, monkeypatch, capsys, kind, message):
    checkout, site_packages = installation
    if kind == "wheel":
        _install_metadata(site_packages, "2.0.0rc2", None)
    elif kind == "other-checkout":
        _install_metadata(site_packages, "2.0.0rc2", checkout.with_name("other"))
    elif kind == "source-egg-info":
        stale = checkout / "src/frameit.egg-info"
        stale.mkdir()
        (stale / "PKG-INFO").write_text("Name: frameit\nVersion: 2.0.0rc2\n")
        monkeypatch.syspath_prepend(str(checkout / "src"))
    elif kind == "duplicate":
        _install_metadata(site_packages, "2.0.0rc2", checkout)
        _install_metadata(site_packages, "2.0.0rc1", None)
    elif kind == "ambiguous-source":
        _install_metadata(site_packages, "2.0.0rc2", checkout)
        (checkout / "pyproject.toml").write_text('[project]\nname = "other"\nversion = "9"\n')
    else:
        _install_metadata(site_packages, "2.0.0rc2", checkout)
        (site_packages / "frameit-2.0.0rc2.dist-info/direct_url.json").write_text("{")

    def forbidden(*args, **kwargs):
        pytest.fail("pip ran on an unverified installation")

    monkeypatch.setattr(subprocess, "run", forbidden)
    code, output = _refresh(capsys)
    assert code == 1 and message in output.err.lower()
    assert "activate" in output.err.lower()


@pytest.mark.parametrize("failure", ["install", "show", "stale-version"])
def test_refresh_does_not_report_success_on_pip_failure(
        installation, monkeypatch, capsys, failure):
    checkout, site_packages = installation
    _install_metadata(site_packages, "2.0.0rc2", checkout)
    steps = []

    def pip(args, **kwargs):
        step = args[3]
        steps.append(step)
        if step == failure:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0, stdout="Name: frameit\nVersion: 2.0.0rc2\n")

    monkeypatch.setattr(subprocess, "run", pip)
    code, output = _refresh(capsys)
    assert code == 1 and not output.out
    assert ("pip install" if failure == "install" else "pip show") in output.err
    assert steps == (["install"] if failure == "install" else ["install", "show"])
    if failure == "stale-version":
        assert "2.0.0rc2" in output.err and "2.0.0rc4" in output.err
