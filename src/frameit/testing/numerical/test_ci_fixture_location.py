"""External reduced fixtures stay separate from installed software."""

from importlib import resources

import pytest


def test_default_ci_fixture_location_is_the_package_resource(monkeypatch):
    from frameit.testing.datasets import ci_dataset_root

    monkeypatch.delenv("FRAMEIT_CI_DATA_ROOT", raising=False)
    assert ci_dataset_root() == resources.files("frameit.testing").joinpath("ci_dataset")


def test_explicit_ci_fixture_environment_is_resolved_without_copying(tmp_path, monkeypatch):
    from frameit.testing.datasets import ci_dataset_root

    fixture = tmp_path / "authorized fixture"
    fixture.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRAMEIT_CI_DATA_ROOT", "authorized fixture")
    assert ci_dataset_root() == fixture
    assert list(fixture.iterdir()) == []


@pytest.mark.parametrize("value", ["", " ", "missing", "not-a-directory"])
def test_invalid_explicit_ci_fixture_never_falls_back(tmp_path, monkeypatch, value):
    from frameit.testing.datasets import ci_dataset_root

    (tmp_path / "not-a-directory").write_text("not fixture data")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FRAMEIT_CI_DATA_ROOT", value)
    with pytest.raises(ValueError, match="FRAMEIT_CI_DATA_ROOT.*directory"):
        ci_dataset_root()
