import os

import pytest

from frameit.testing.numerical.test_run_diag_lifecycle import run_diag
from frameit.testing.numerical.test_run_diag_sources import vortex_parent


def test_zarr_scopes_and_accessed_identity(tmp_path, monkeypatch):
    zarr = pytest.importorskip("zarr")
    from zarr.storage import LocalStore

    cfg, _, raw, root = vortex_parent(tmp_path, kind="model_grid", output_format="zarr")
    raw.unlink()
    actual_get = LocalStore.get
    reads = []

    async def trace(store, key, *args, **kwargs):
        reads.append(key)
        assert zarr.config.get("async.concurrency") == 1
        assert zarr.config.get("threading.max_workers") == 1
        return await actual_get(store, key, *args, **kwargs)

    monkeypatch.setattr(LocalStore, "get", trace)
    with zarr.config.set({"async.concurrency": 3, "threading.max_workers": 2}):
        check = run_diag(cfg, check=True)
        assert check["status"] == "ok", check["errors"]
        assert not any(key.startswith("wind10/c/") for key in reads)
        assert zarr.config.get("async.concurrency") == 3
        assert zarr.config.get("threading.max_workers") == 2
        assert not (root / "diagnostics").exists()

        report = run_diag(cfg)
        assert report["status"] == "ok", report["errors"]
        assert any(key.startswith("wind10/c/") for key in reads)
        assert zarr.config.get("async.concurrency") == 3

        from frameit.diagnostics.sources import _Provider

        recheck = _Provider.recheck

        def modified(provider):
            (file,) = provider.plan.files
            objects = provider.zarr_evidence[file.path]
            key = next(key for key in objects if key.startswith("wind10/c/"))
            accessed = file.path / key
            st = accessed.stat()
            os.utime(accessed, ns=(st.st_atime_ns, st.st_mtime_ns + 1000))
            recheck(provider)

        monkeypatch.setattr(_Provider, "recheck", modified)
        failed = run_diag(cfg)
        assert not failed["data"]["plan"]["committed"]
        assert failed["errors"][0]["code"] == "E2003"
        assert "accessed" in failed["errors"][0]["message"]
        assert zarr.config.get("threading.max_workers") == 2


def test_grib_message_once(tmp_path, monkeypatch):
    ec = pytest.importorskip("eccodes")
    from frameit.core.configuration import to_runtime
    from frameit.core.execution import ExecutionOptions, execute_simulation
    from frameit.core.settings_class import SimulationConfig
    from frameit.testing.numerical.test_run_diag_configuration import request
    from frameit.testing.numerical.test_run_diag_lifecycle import snapshot, write_request
    from frameit.testing.numerical.test_v3_grib_reads import write_messages

    data = write_messages(
        tmp_path / "source.grib",
        [
            {"param": 165, "group": "heightAboveGround", "level": 10, "missing": False},
            {"param": 166, "group": "heightAboveGround", "level": 10, "missing": False},
            {"param": 151, "group": "meanSea", "level": 0, "missing": False},
            {"param": 130, "group": "isobaric", "level": 850, "missing": False},
        ],
    )
    raw = request(kind="original")
    raw["sources"]["weather"].update(files=data.name, format="grib", variables={"2d": ["prmsl"]})
    raw["region"] = {"center": {"latitude": -19.5, "longitude": 61.0}}
    raw["products"] = {"track": True, "model_grid": True}
    raw["resources"] = {"cpus": 1, "scheduler": "synchronous", "synchronous_export": True}
    conf = SimulationConfig(**to_runtime(raw, base_dir=tmp_path))
    execute_simulation(conf, ExecutionOptions.from_config(conf, export_netcdf=False))
    before = snapshot(conf.output_dir)
    best = raw["diagnostics"]["best_track"]
    best["wind_time_policy"] = "native_proxy"
    best["fields"] = {"wind": {"u": "u10", "v": "v10"}, "sea_level_pressure": "prmsl"}
    best["search"] = {
        "pressure_radius_km": 150,
        "maximum_wind_radius_km": 200,
        "wind_radii_radius_km": 250,
    }
    cfg = write_request(tmp_path / "grib.yaml", raw)
    actual = ec.codes_get_values
    seen = []

    def track(handle):
        seen.append(ec.codes_get(handle, "paramId"))
        return actual(handle)

    monkeypatch.setattr(ec, "codes_get_values", track)
    report = run_diag(cfg, check=True)
    assert report["status"] == "ok" and seen == [], report["errors"]
    report = run_diag(cfg)
    assert report["status"] == "ok", report["errors"]
    assert sorted(seen) == [151, 165, 166]
    assert snapshot(conf.output_dir) == before
