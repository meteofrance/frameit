"""RAM planning uses bound sizes and execution settings, never field payloads."""

import json
from math import prod

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.cli import _cmd_validate
from frameit.core.execution import execute_simulation
from frameit.core.memory_estimate import estimate_run_memory
from frameit.core.preflight import collect_preflight
from frameit.core.reports import project_report, render_projection
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_inspect_metadata import guard_netcdf_payloads, v3_config
from frameit.testing.numerical.test_v3_grib_reads import write_messages
from frameit.testing.numerical.test_v3_operations import scene as vertical_scene
from frameit.testing.numerical.test_v3_polar import configuration as polar_config
from frameit.testing.numerical.test_v3_polar import scene
from frameit.testing.numerical.test_v3_resources import allocation  # noqa: F401

GIB = 1024**3


def _request(tmp_path, **resources):
    return {
        "schema_version": 3, "run": {"name": "memory"},
        "sources": {"weather": {
            "model": "mesonh", "files": str(tmp_path / "input.nc"), "variables": {"2d": ["q"]},
        }},
        "resources": {"cpus": 1, "synchronous_export": True, **resources},
        "output": {"directory": str(tmp_path / "out")},
    }


def _estimate(request):
    result = collect_preflight(request)
    assert not result.errors, result.errors
    plan = result.facts.get("memory_estimate")
    assert plan is not None, "Full validation has no modeled RAM estimate"
    assert plan["status"] == "estimated", plan
    assert 0 < plan["estimated_median_rss_bytes"] <= plan["estimated_peak_rss_bytes"]
    assert plan["estimated_peak_rss_bytes"] < plan["recommended_allocation_bytes"]
    return plan


def test_validate_formats_a_metadata_only_estimate(tmp_path, monkeypatch, capsys):
    path = tmp_path / "input.nc"
    scene().to_netcdf(path, engine="h5netcdf")
    config = tmp_path / "frameit.yaml"
    config.write_text(yaml.safe_dump(_request(tmp_path)))
    guard_netcdf_payloads(monkeypatch, {"q"})
    assert _cmd_validate(config, json_output=True) == 0
    report = json.loads(capsys.readouterr().out)
    plan = report["data"]["plan"].get("memory_estimate")
    assert plan is not None, "The JSON report lacks the RAM estimate"
    peak, typical = plan["estimated_peak_rss_bytes"], plan["estimated_median_rss_bytes"]
    recommendation = plan["recommended_allocation_bytes"]
    assert 0 < typical <= peak < recommendation
    assert 3 * peak <= 2 * recommendation and recommendation % GIB == 0
    assert plan["inputs"]["weather"]["largest_input_block_bytes"] == 9 * 9 * 8
    for phrase in ("Estimated peak RSS", "Estimated median RSS", "Recommended allocation"):
        assert phrase in render_projection(report)
    assert not (tmp_path / "out").exists()


def test_read_blocks_use_selected_levels_decoded_dtype_and_requested_chunks(tmp_path):
    ds = vertical_scene().drop_vars("V").rename(U="q")
    ds["q"] = ds.q.astype("float32")
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = _request(tmp_path)
    source = raw["sources"]["weather"]
    source["variables"] = {"3d": ["q"], "levels": {"indices": [1]}}
    block = _estimate(raw)["inputs"]["weather"]["largest_input_block_bytes"]
    assert block == 3 * 3 * 4
    source["reader"] = {"chunks": {"ni": 2}}
    assert _estimate(raw)["inputs"]["weather"]["largest_input_block_bytes"] == 2 * 3 * 4
    source["variables"].pop("levels")
    assert _estimate(raw)["inputs"]["weather"]["largest_input_block_bytes"] == 2 * 3 * 3 * 4


def test_estimate_increases_with_grid_and_concurrent_dask_tasks(tmp_path, allocation):  # noqa: F811
    path = tmp_path / "input.nc"
    ds = scene()
    ds.to_netcdf(path, engine="h5netcdf")
    small = _estimate(_request(tmp_path))
    ds = ds.interp(ni=np.linspace(-4000., 4000., 31), nj=np.linspace(-4000., 4000., 31))
    ds.to_netcdf(path, engine="h5netcdf")
    large = _estimate(_request(tmp_path))
    parallel = _estimate(_request(tmp_path, cpus=2, compute_workers=2))
    assert small["estimated_peak_rss_bytes"] < large["estimated_peak_rss_bytes"]
    assert large["estimated_peak_rss_bytes"] < parallel["estimated_peak_rss_bytes"]


def test_spawned_export_accounts_for_only_jobs_that_can_run(tmp_path, allocation):  # noqa: F811
    scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = _request(tmp_path, cpus=4, export_workers=4, synchronous_export=False)
    spawned = _estimate(raw)
    assert spawned["concurrency"]["spawned_export_workers"] == 1
    raw["region"] = {"center": {"latitude": -20., "longitude": 60.}}
    raw["products"] = {"model_grid": True, "track": True}
    both = _estimate(raw)
    assert both["concurrency"]["spawned_export_workers"] == 2
    assert both["estimated_peak_rss_bytes"] > spawned["estimated_peak_rss_bytes"]
    raw["resources"]["synchronous_export"] = True
    synchronous = _estimate(raw)
    assert synchronous["concurrency"]["spawned_export_workers"] == 0
    assert synchronous["estimated_peak_rss_bytes"] < both["estimated_peak_rss_bytes"]


def test_zarr_writer_buffers_include_the_shard_time_extent(tmp_path):
    scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = _request(tmp_path)
    raw["output"].update(format="zarr", writer={"shards": {"time": 1}})
    small = _estimate(raw)["products"]["weather.model_grid"]["largest_writer_block_bytes"]
    raw["output"]["writer"]["shards"]["time"] = 3
    large = _estimate(raw)["products"]["weather.model_grid"]["largest_writer_block_bytes"]
    assert small == 9 * 9 * 8 and large == 3 * small


def test_polar_peak_grows_with_the_bound_target(tmp_path, monkeypatch):
    scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    guard_netcdf_payloads(monkeypatch, {"q"})
    small = _estimate(polar_config(tmp_path))
    huge = _estimate(polar_config(
        tmp_path, products={"polar": {"radius_km": 2.5, "azimuth_count": 32}},
    ))
    assert small["phases"]["polar"]["peak_rss_bytes"] < huge["phases"]["polar"]["peak_rss_bytes"]


def test_polar_operator_can_assemble_more_than_one_reader_tile(tmp_path, monkeypatch):
    ds = scene().interp(ni=np.linspace(-4000., 4000., 31), nj=np.linspace(-4000., 4000., 31))
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    raw = polar_config(
        tmp_path, source={"reader": {"chunks": {"ni": 2, "nj": 2}}},
        products={"polar": {"radius_km": 1.5, "azimuth_count": 8}},
    )
    guard_netcdf_payloads(monkeypatch, {"q"})
    ram = _estimate(raw)
    assert ram["inputs"]["atmosphere"]["largest_input_block_bytes"] == 2 * 2 * 8
    assert ram["products"]["atmosphere.polar"]["largest_processing_block_bytes"] >= 31 * 31 * 8


def test_grib_counts_full_decode_working_record_without_decoding(tmp_path, monkeypatch):
    file = write_messages(tmp_path / "wind.grib", [{"level": 850, "hour": 1}])
    monkeypatch.setattr("frameit.io.grib_utils._grib_payload",
                        lambda *args: pytest.fail("RAM planning decoded a GRIB payload"))
    request = v3_config(tmp_path, [file], model="arome", variables={"3d": ["u"]})
    ram = _estimate(request)
    assert ram["inputs"]["weather"]["largest_eager_native_record_bytes"] == 3 * 2 * 8


@pytest.mark.parametrize("kind", ["model_grid", "polar"])
def test_writer_block_counts_bound_grib_members(tmp_path, monkeypatch, kind):
    file = write_messages(tmp_path / "wind.grib", [
        {"level": level, "member": member}
        for level in (850, 700) for member in (0, 1)
    ])
    raw = _request(tmp_path)
    raw["sources"]["weather"] = {"model": "arome", "files": str(file), "variables": {"3d": ["u"]}}
    if kind == "polar":
        raw["region"] = {"center": {"longitude": 60., "latitude": -20.}}
        raw["products"] = {"polar": {"radius_km": 2.5, "azimuth_count": 8}}
    raw["output"]["writer"] = {"chunks": {"time": 1}}
    with monkeypatch.context() as guarded:
        guarded.setattr("frameit.io.grib_utils._grib_payload",
                        lambda *args: pytest.fail("RAM planning decoded a GRIB payload"))
        estimate = _estimate(raw)["products"][f"weather.{kind}"]["largest_writer_block_bytes"]
        raw["output"]["writer"]["chunks"]["number"] = 1
        per_member = _estimate(raw)["products"][f"weather.{kind}"]["largest_writer_block_bytes"]
        del raw["output"]["writer"]["chunks"]["number"]

    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok
    with xr.open_dataset(result.products[0]["path"], engine="h5netcdf") as product:
        assert product.u.sizes["number"] == 2
        actual_chunk_bytes = prod(product.u.encoding["chunksizes"]) * product.u.dtype.itemsize
    assert estimate == 2 * per_member
    if kind == "model_grid":
        assert actual_chunk_bytes == 2 * 2 * 3 * 2 * 8
        assert estimate == actual_chunk_bytes


def test_unavailable_estimate_does_not_change_validation_verdict(tmp_path):
    result = collect_preflight(_request(tmp_path))
    assert result.errors
    ram = result.facts.get("memory_estimate")
    assert ram is not None and ram["status"] == "unavailable"
    for key in ("estimated_peak_rss_bytes", "estimated_median_rss_bytes",
                "recommended_allocation_bytes"):
        assert ram[key] is None
    assert "RAM estimate unavailable" in render_projection(project_report(result))


def test_object_dtype_without_a_size_has_no_recommendation(tmp_path):
    ds = scene()
    ds["q"] = xr.full_like(ds.q, "open-ended text", dtype=object)
    ds.to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    result = collect_preflight(_request(tmp_path))
    assert not result.errors
    # Some NetCDF versions expose a fixed U dtype for coded strings. An unknown
    # decoded object dtype cannot be costed using its pointer size.
    for record in result.facts["sources"]["weather"]["field_binding"]["records"]:
        record["decoded_dtype"] = "object"
    ram = estimate_run_memory(result.facts)
    assert ram["status"] == "unavailable" and ram["recommended_allocation_bytes"] is None


def test_schema_only_and_inspect_have_no_ram_recommendation(tmp_path):
    request = _request(tmp_path)
    assert "memory_estimate" not in collect_preflight(request, schema_only=True).facts
    scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    assert "memory_estimate" not in collect_preflight(request, command="inspect").facts


def test_tui_displays_estimate_and_accepts_a_report_without_it(tmp_path):
    from frameit.validate_tui import _overview

    scene().to_netcdf(tmp_path / "input.nc", engine="h5netcdf")
    report = project_report(collect_preflight(_request(tmp_path)))
    args = report, tmp_path / "frameit.yaml", False, {}
    text = _overview(*args, has_warnings=False)
    assert "Estimated peak RSS" in text and "Recommended allocation" in text
    report["data"]["plan"].pop("memory_estimate")
    assert "Estimated peak RSS" not in _overview(*args, has_warnings=False, saved=True)
