"""Output isolation and scientific request regressions."""

import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import xarray as xr

from frameit.testing.catalog import load_cases


def test_direct_export_uses_products_directory(tmp_path):
    from frameit.io.netcdf_export import export_outputs

    track = xr.Dataset(
        {"lon": ("time", [60.0]), "lat": ("time", [-17.5])},
        coords={"time": np.array(["2022-02-01"], dtype="datetime64[ns]")},
    )
    runner = SimpleNamespace(
        conf=SimpleNamespace(simulation_name="TEST"), output_dir=tmp_path / "default",
        track=track,
    )
    for override in (None, tmp_path / "override"):
        root = runner.output_dir if override is None else override
        result = export_outputs(runner, institution="test", out_dir=override, synchronous=True)
        assert result["track"] == root / "products" / "TEST.track.nc"
        with xr.open_dataset(result["track"]) as saved:
            np.testing.assert_allclose(saved["lon"], track["lon"])
        assert list(root.iterdir()) == [root / "products"]


def test_full_arome_requests_do_not_inherit_vertical_velocity():
    cases = load_cases(mode="full")
    for case in cases:
        requests = case["config"]["requested_variables_user"]
        if case["dataset_id"].startswith("AROME/"):
            assert all("w" not in spec["variables"] for spec in requests.values())
        elif "level_w" in requests:
            assert "WT" in requests["level_w"]["variables"]
    w_only = next(case for case in load_cases() if case["id"] == "mnh_chido_w_only_polar")
    assert w_only["config"]["polar_variables"] == {"level_w": {"variables": ["WT"]}}


def test_grib_cache_is_local_distinct_and_reused(tmp_path):
    from frameit.io.grib_utils import concat_grib2ds_by_vert_coord
    from frameit.io.loader import DatasetResources

    fixture = (Path(__file__).parents[1] / "ci_dataset" / "AROME" / "BATSIRAI"
               / "arome_BATSIRAI_20220201+0000P.grib")
    inputs = []
    for name in ("first", "second"):
        directory = tmp_path / name
        directory.mkdir()
        target = directory / fixture.name
        shutil.copyfile(fixture, target)
        inputs.append(target)
    cache = tmp_path / "run" / "cache"
    request = {"surface": {"variables": ["prmsl"]}}

    def load():
        with DatasetResources() as resources:
            # Open separately: identical fixture times should not be concatenated.
            for source in inputs:
                user, _ = concat_grib2ds_by_vert_coord(
                    [source], request, {}, index_dir=cache, resources=resources,
                )
                assert "prmsl" in user["surface"]

    load()
    indexes = list(cache.glob("*.idx"))
    assert len(indexes) >= 2
    assert len({path.name.split(".")[-3] for path in indexes}) == 2
    before = {path.name: path.stat().st_mtime_ns for path in indexes}
    load()
    assert {path.name: path.stat().st_mtime_ns for path in cache.glob("*.idx")} == before
    assert all(list(source.parent.iterdir()) == [source] for source in inputs)
