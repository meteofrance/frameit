"""C8 resource bounds on compact v3 inputs, not production/HPC qualification."""

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import dask
import numpy as np
import pytest
import xarray as xr
import yaml
from threadpoolctl import threadpool_info

from frameit.core.configuration import resolve_operational_overrides, to_runtime
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.runtime import (
    NATIVE_THREAD_VARIABLES,
    execution_scope,
    resolve_execution_resources,
)
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_v3_polar import scene


@pytest.fixture
def allocation(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: set(range(8)))
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "4")


def configuration(tmp_path, *, resources=None, **extra):
    return SimulationConfig(**to_runtime({
        "schema_version": 3,
        "sources": {"weather": {"model": "mesonh", "files": str(tmp_path / "input.nc"),
                                "variables": {"2d": ["q"]}}},
        "output": {"directory": str(tmp_path / "output")},
        "resources": {"cpus": 1, **(resources or {})},
        **extra,
    }))


@pytest.mark.parametrize("cpus,budget", [(None, 4), (1, 1), (3, 3)])
def test_requested_budget_bounds_all_nested_workers(allocation, cpus, budget):
    effective, facts = resolve_execution_resources(ExecutionOptions(cpus=cpus))
    assert facts["cpu_budget"] == effective.cpus == budget
    assert effective.max_workers * effective.dask_workers * effective.native_threads <= budget
    assert effective.native_threads == 1 and not effective.synchronous_export
    assert facts["reader_workers"] == 1
    assert facts["setting_sources"]["resources.cpus"] == (
        "automatic" if cpus is None else "explicit")


@pytest.mark.parametrize("options,match", [
    (ExecutionOptions(cpus=5), r"resources.cpus.*5.*available.*4"),
    (ExecutionOptions(cpus=1, dask_workers=2), "exceeds CPU budget"),
    (ExecutionOptions(cpus=2, max_workers=2, dask_workers=2), "exceeds CPU budget"),
    (ExecutionOptions(cpus=2, dask_workers=2, native_threads=2), "exceeds CPU budget"),
])
def test_explicit_resource_excess_fails(allocation, options, match):
    with pytest.raises(ValueError, match=match):
        resolve_execution_resources(options)


def test_inactive_pools_do_not_consume_budget_and_nested_scope_restores(allocation, monkeypatch):
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "7")
    before = {name: os.environ.get(name) for name in NATIVE_THREAD_VARIABLES}
    scheduler, workers = dask.config.get("scheduler", None), dask.config.get("num_workers", None)
    effective, facts = resolve_execution_resources(ExecutionOptions(
        cpus=2, max_workers=20, synchronous_export=True,
        dask_scheduler="synchronous", dask_workers=30, native_threads=2))
    assert effective.max_workers == effective.dask_workers == 1
    assert facts["export_start_method"] is None
    with pytest.raises(RuntimeError, match="test exit"):
        with execution_scope(effective):
            assert dask.config.get("scheduler") == "synchronous"
            with execution_scope(replace(effective, native_threads=1)):
                assert all(pool["num_threads"] == 1 for pool in threadpool_info())
            assert os.environ["OPENBLAS_NUM_THREADS"] == "2"
            raise RuntimeError("test exit")
    assert {name: os.environ.get(name) for name in NATIVE_THREAD_VARIABLES} == before
    assert dask.config.get("scheduler", None) == scheduler
    assert dask.config.get("num_workers", None) == workers


def test_v3_budget_rejected_before_output_side_effects(tmp_path, allocation):
    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, resources={"cpus": 5})
    with pytest.raises(ValueError, match="resources.cpus") as exc:
        execute_simulation(conf)
    assert exc.value.frameit_code == "E1701"
    assert not conf.output_dir.exists()


def test_effective_origins_distinguish_cli_yaml_default_and_automatic(tmp_path, allocation):
    scene().to_netcdf(tmp_path / "input.nc")
    raw = configuration(tmp_path).yaml_config
    document, origins = resolve_operational_overrides(raw, overrides={"cpus": 2})
    conf = SimulationConfig(**to_runtime(document))
    conf.schema_sources = origins
    options = ExecutionOptions.from_config(conf)
    effective, facts = resolve_execution_resources(options)
    assert effective.cpus == 2
    assert facts["setting_sources"]["resources.cpus"] == "cli"
    assert facts["setting_sources"]["resources.native_threads"] == "yaml"
    assert facts["setting_sources"]["resources.compute_workers"] == "automatic"
    defaults = ExecutionOptions.from_config(configuration(tmp_path), cpus=2)
    _, facts = resolve_execution_resources(defaults)
    assert facts["setting_sources"]["resources.cpus"] == "cli"
    assert facts["setting_sources"]["resources.native_threads"] == "default"


def _export_probe(block, *, directory):
    """Record real Dask task context, including inside a spawned interpreter."""
    if block.size:
        import threading
        import time

        fact = {"pid": os.getpid(), "scheduler": dask.config.get("scheduler", None),
                "workers": dask.config.get("num_workers", None),
                "native_environment": {n: os.environ.get(n) for n in NATIVE_THREAD_VARIABLES},
                "native_pools": [pool["num_threads"] for pool in threadpool_info()]}
        path = Path(directory) / f"{os.getpid()}-{threading.get_ident()}-{time.time_ns()}.json"
        path.write_text(json.dumps(fact))
    return block


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("synchronous", [False, True])
@pytest.mark.parametrize("compute_workers", [1, 2])
def test_v3_actual_export_uses_effective_budget_and_mode(
        tmp_path, monkeypatch, fmt, synchronous, compute_workers):
    import dask.array as da

    from frameit.io import netcdf_export

    source = tmp_path / "input.nc"
    scene().to_netcdf(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    probe = tmp_path / "probe"
    probe.mkdir()
    conf = configuration(tmp_path, resources={
        "synchronous_export": synchronous, "cpus": compute_workers,
        "compute_workers": compute_workers, "export_workers": 1},
                         output={"directory": str(tmp_path / "output"), "format": fmt})
    original = netcdf_export.export_outputs

    def instrument(runner, **kwargs):
        dataset = runner.field_products[("weather", "model_grid")]
        dataset["q"] = dataset.q.copy(data=da.map_blocks(
            _export_probe, dataset.q.data, directory=str(probe), dtype=dataset.q.dtype))
        return original(runner, **kwargs)

    monkeypatch.setattr(netcdf_export, "export_outputs", instrument)
    result = execute_simulation(conf)
    facts = [json.loads(path.read_text()) for path in probe.glob("*.json")]
    assert facts
    assert all((fact["pid"] == os.getpid()) == synchronous for fact in facts)
    assert all(fact["workers"] == compute_workers and fact["scheduler"] == "threads"
               for fact in facts)
    assert all(set(fact["native_environment"].values()) == {"1"} for fact in facts)
    assert all(all(n == 1 for n in fact["native_pools"]) for fact in facts)
    assert result.execution_resources["cpu_budget"] == compute_workers
    assert result.execution_resources["export_workers"] == 1
    assert len(result.products) == 1
    product = result.products[0]
    subprocess.run([sys.executable, "-c", """
import sys, numpy as np, xarray as xr
out = (xr.open_zarr(sys.argv[1],consolidated=False) if sys.argv[3] == 'zarr'
       else xr.open_dataset(sys.argv[1]))
with out, xr.open_dataset(sys.argv[2]) as source:
    np.testing.assert_array_equal(out.q,source.q)
    assert out.q.dtype == source.q.dtype and out.q.attrs == source.q.attrs
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", product["path"], str(source), fmt], check=True, capture_output=True, text=True)
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    resolved = yaml.safe_load((conf.output_dir / "resolved-config.yaml").read_text())
    assert status["state"] == "completed" and len(status["products"]) == 1
    assert provenance["runtime"]["execution_resources"]["cpu_budget"] == compute_workers
    assert provenance["setting_sources"]["resources.compute_workers"] == "yaml"
    assert resolved["resources"]["cpus"] == compute_workers
    assert resolved["resources"]["compute_workers"] == compute_workers
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def _failed_export(block):
    if block.size:
        raise OSError("task11 synthetic writer failure")
    return block


@pytest.mark.parametrize("synchronous", [False, True])
def test_v3_export_failure_retains_only_actual_complete_products(
        tmp_path, monkeypatch, synchronous):
    import dask.array as da

    from frameit.io import netcdf_export

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, resources={"synchronous_export": synchronous},
                         region={"center": {"latitude": -20., "longitude": 60.}},
                         products={"model_grid": True, "polar": {
                             "radius_km": 2.5, "azimuth_count": 8}})
    original = netcdf_export.export_outputs

    def instrument(runner, **kwargs):
        dataset = runner.field_products[("weather", "polar")]
        dataset["q"] = dataset.q.copy(data=da.map_blocks(
            _failed_export, dataset.q.data, dtype=dataset.q.dtype))
        return original(runner, **kwargs)

    monkeypatch.setattr(netcdf_export, "export_outputs", instrument)
    with pytest.raises(OSError, match="task11 synthetic writer failure"):
        execute_simulation(conf)
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    assert status["state"] == "failed"
    for record in (status, provenance):
        assert [p["role"] for p in record["products"]] == ["model_grid"]
        assert record["error"]["code"] == "E1806"
        assert "task11 synthetic writer failure" in record["error"]["message"]
    with xr.open_dataset(conf.output_dir / status["products"][0]["path"]) as saved:
        np.testing.assert_array_equal(saved.q, scene().q)
    assert not (conf.output_dir / "products/analysis.weather.polar.nc").exists()
    assert not list(conf.output_dir.rglob("*.partial"))


@pytest.mark.parametrize("namespace,key", [
    ("input", "x"), ("model_grid", "ni"), ("polar", "heightAboveGround"), ("writer", "ni"),
])
def test_unmatched_namespace_fails_without_payload_or_publication(
        tmp_path, monkeypatch, namespace, key):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core.preflight import preflight

    scene().expand_dims(heightAboveGround=[10., 20.]).assign_coords(
        heightAboveGround=("heightAboveGround", [10., 20.], {"axis": "Z", "units": "m"})
    ).to_netcdf(tmp_path / "input.nc")
    source = {"model": "mesonh", "files": str(tmp_path / "input.nc"),
              "variables": {"3d": ["q"]}}
    products = {"model_grid": {}, "polar": {"radius_km": 2.5, "azimuth_count": 8}}
    output = {"directory": str(tmp_path / "output")}
    if namespace == "input":
        source["reader"] = {"chunks": {key: 1}}
    elif namespace == "writer":
        output["writer"] = {"chunks": {key: 1}}
    else:
        products[namespace]["processing"] = {"chunks": {key: 1}}
    conf = configuration(tmp_path, sources={"weather": source}, output=output, products=products,
                         region={"center": {"latitude": -20., "longitude": 60.}})
    original = H5NetCDFArrayWrapper.__getitem__

    def no_payload(array, index):
        assert array.variable_name != "q"
        return original(array, index)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
    with pytest.raises(ValueError, match="chunk|writer"):
        preflight(conf)
    assert not conf.output_dir.exists()


@pytest.mark.parametrize("qualified", [False, True])
def test_polar_chunks_follow_public_standard_and_inventory_qualified_axes(tmp_path, qualified):
    from frameit.core.coupled import bind_sources

    paths = []
    for name, levels in (("q", [10., 20.]), ("other", [30., 40.])) if qualified else (
            ("q", [10., 20.]),):
        ds = scene().rename(q=name).expand_dims(heightAboveGround=levels).assign_coords(
            heightAboveGround=("heightAboveGround", levels, {"axis": "Z", "units": "m"}))
        path = tmp_path / f"{name}.nc"
        ds.to_netcdf(path)
        paths.append(str(path))
    kwargs = {
        "sources": {"weather": {"model": "mesonh", "files": paths,
                                "variables": {"3d": ["q", "other"] if qualified else ["q"]}}},
        "region": {"center": {"latitude": -20., "longitude": 60.}},
        "products": {"polar": {"radius_km": 2.5, "azimuth_count": 8}},
        "resources": {"synchronous_export": True},
    }
    conf = configuration(tmp_path, **kwargs)
    bind_sources(conf)
    planned = conf.simulation_parameter["request_plan"]["products"][0]
    axis = next(d for d in planned["dimensions"]["q"] if d.startswith("height_above_ground"))
    assert (axis == "height_above_ground") != qualified
    kwargs["products"]["polar"].update(
        fields={"weather": ["q"]},
        processing={"chunks": {axis: 1, "radius": 2, "azimuth": 4}, "profile": True})
    conf = configuration(tmp_path, **kwargs)
    result = execute_simulation(conf)
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    processing = provenance["sources"]["weather"]["polar"]["processing"]
    assert processing["chunks"]["q"][axis] == [1, 1]
    assert processing["chunks"]["q"]["radius"] == [2, 2]
    assert processing["chunks"]["q"]["azimuth"] == [4, 4]
    assert processing["weight_zero_tolerance"] == 1e-14
    assert processing["source_halo_points"] == 1
    assert processing["plan_cache"] == {"entries": 8, "max_bytes": 128 * 1024**2}
    with xr.open_dataset(result.products[0]["path"]) as saved:
        assert axis in saved.q.dims and saved.q.sizes[axis] == 2
        np.testing.assert_allclose(saved.q, 7., rtol=0, atol=1e-10)


def test_input_product_and_writer_layouts_are_independent(tmp_path):
    source = tmp_path / "input.nc"
    scene().to_netcdf(source)
    conf = configuration(tmp_path, resources={"synchronous_export": True}, sources={"weather": {
        "model": "mesonh", "files": str(source), "variables": {"2d": ["q"]},
        "time": {"values": ["2024-01-01T01:00:00"]},
        "reader": {"chunks": {"time": 3, "ni": 3, "nj": -1}},
    }}, products={"model_grid": {"processing": {"chunks": {"x": 4, "y": 3}}}},
        output={"directory": str(tmp_path / "output"),
                "writer": {"chunks": {"time": 1, "x": 2, "y": 2}}})
    result = execute_simulation(conf)
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    layouts = provenance["layouts"]
    applications = layouts["inputs"]["weather"]["applications"]
    assert applications and all(p["chunks"]["time"] == [1] for p in applications)
    assert all(p["chunks"]["ni"] == [3, 3, 3] for p in applications)
    chunks = layouts["products"]["weather.model_grid"]["chunks"]["q"]
    assert chunks["x"] == [4, 4, 1] and chunks["y"] == [3, 3, 3]
    assert result.products[0]["encoding"]["chunks"]["q"] == [1, 2, 2]
    with xr.open_dataset(result.products[0]["path"]) as out, xr.open_dataset(source) as original:
        np.testing.assert_array_equal(out.q, original.q.isel(time=[1]))


@pytest.mark.parametrize("profile", [False, True])
def test_v3_profile_gates_measurements_and_reports_bounded_cache(tmp_path, monkeypatch, profile):
    from frameit.processing.polar import contracts, polar_proj, regrid_plan

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, resources={"synchronous_export": True},
                         region={"center": {"latitude": -20., "longitude": 60.}},
                         products={"polar": {"radius_km": 2.5, "azimuth_count": 8,
                                             "processing": {"profile": profile, "plan_cache": {
                                                 "entries": 1, "max_bytes": 1}}}})
    if not profile:
        monkeypatch.setattr(polar_proj, "dask_graph_tasks", lambda *a: pytest.fail(
            "profile=false must not count graphs"))
        monkeypatch.setattr(polar_proj, "process_peak_rss_bytes", lambda: pytest.fail(
            "profile=false must not measure RSS"))
        for module in (polar_proj, regrid_plan, contracts):
            monkeypatch.setattr(module, "perf_counter", lambda: pytest.fail(
                "profile=false must not timestamp optional polar work"))
    result = execute_simulation(conf)
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    report = provenance["sources"]["weather"]["polar"]
    assert report["regrid_performance"]["retained_bytes"] == 0
    assert report["regrid_performance"]["retained_entries"] == 0
    assert report["regrid_performance"]["oversized_plans"] >= 1
    assert report["processing"]["profile"] is profile
    for cache, names in (
        (report["regrid_performance"], ("signature_s", "construction_s", "application_s")),
        (report["source_geometry_cache"], ("normalization_s", "fingerprint_s")),
    ):
        assert cache["timing"]["enabled"] is profile
        for name in names:
            assert cache[name] >= 0 if profile else cache[name] is None
    if profile:
        assert report["profile"]["graph_tasks"] > 0
        assert report["profile"]["process_peak_rss_bytes"] > 0
    else:
        assert report["profile"] is None
    with xr.open_dataset(result.products[0]["path"]) as out:
        np.testing.assert_allclose(out.q, 7., rtol=0, atol=1e-10)


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_layout_keys_match_the_product_union_not_every_source(tmp_path, monkeypatch, fmt):
    from frameit.core import preflight

    weather = scene().expand_dims(heightAboveGround=[10., 20.]).assign_coords(
        heightAboveGround=("heightAboveGround", [10., 20.], {"axis": "Z", "units": "m"}))
    weather.to_netcdf(tmp_path / "weather.nc")
    water = scene().rename(q="sea", ni="x", nj="y", time="time_counter",
                           latitude="nav_lat", longitude="nav_lon")
    water.to_netcdf(tmp_path / "water.nc")
    writer = {"chunks": {"x_t": 3, "radius": 1}}
    if fmt == "zarr":
        writer["shards"] = {"x_t": 6, "radius": 2}
    conf = configuration(tmp_path, resources={"synchronous_export": True}, sources={
        "weather": {"model": "mesonh", "files": str(tmp_path / "weather.nc"),
                    "variables": {"3d": ["q"]}, "reader": {"chunks": {"heightAboveGround": 1}}},
        "water": {"model": "nemo", "files": str(tmp_path / "water.nc"),
                  "variables": {"2d": ["sea"]}, "reader": {"chunks": {"x": 3}}},
    }, products={
        "model_grid": {"processing": {"chunks": {"height_above_ground": 1, "x_t": 3}}},
        "polar": {"radius_km": 2.5, "azimuth_count": 8,
                  "processing": {"chunks": {"height_above_ground": 1, "radius": 2}}},
    }, region={"center": {"latitude": -20., "longitude": 60.}},
        output={"directory": str(tmp_path / "output"), "format": fmt, "writer": writer})
    original_bind = preflight.bind_source
    children = []

    def bind(child, name, **kwargs):
        children.append((name, child))
        return original_bind(child, name, **kwargs)

    monkeypatch.setattr(preflight, "bind_source", bind)
    preview = preflight.preflight(conf)
    assert [name for name, _ in children] == ["weather", "water"]
    for name, child in children:
        assert child.polar_output_chunks == (
            {"height_above_ground": 1, "radius": 2} if name == "weather" else {"radius": 2})
        assert child.yaml_config["products"]["polar"]["processing"]["chunks"] == {
            "height_above_ground": 1, "radius": 2}
    assert preview["layouts"]["products"]["water.polar"]["applied_settings"] == {"radius": 2}
    assert preview["layouts"]["writer"]["chunks"]["weather.polar"] == {"radius": 1}
    assert not conf.output_dir.exists()
    result = execute_simulation(conf)
    assert [name for name, _ in children] == ["weather", "water", "weather", "water"]
    assert len(result.products) == 4
    for item in result.products:
        opener = xr.open_zarr if fmt == "zarr" else xr.open_dataset
        with opener(item["path"], **({"consolidated": False} if fmt == "zarr" else {})) as out:
            name = "q" if item["source"] == "weather" else "sea"
            assert ("height_above_ground" in out[name].dims) == (name == "q")
            np.testing.assert_allclose(out[name], 7., rtol=0, atol=1e-10)


def test_native_reader_union_does_not_require_each_grid_to_match(tmp_path):
    from frameit.testing.numerical.test_v3_outputs import mnh_scene

    mnh_scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, resources={"synchronous_export": True}, sources={"weather": {
        "model": "mesonh", "files": str(tmp_path / "input.nc"),
        "variables": {"3d": ["T", "U"]}, "reader": {"chunks": {"ni_u": 2}},
    }}, products={"model_grid": {"processing": {"chunks": {"x_u": 1}}}})
    result = execute_simulation(conf)
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    targets = provenance["layouts"]["inputs"]["weather"]["targets"]
    assert targets["T"] == {} and targets["U"] == {"ni_u": 2}
    chunks = provenance["layouts"]["products"]["weather.model_grid"]["chunks"]
    assert chunks["U"]["x_u"] == [1, 1, 1, 1]
    assert "x_u" not in chunks["T"]
    assert len(result.products) == 1


def test_scope_replaces_unbounded_inherited_dask_pool_and_restores_it():
    import threading
    import time

    lock = threading.Lock()
    active = peak = 0

    def task():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(.005)
        with lock:
            active -= 1
        return 1

    with ThreadPoolExecutor(max_workers=2) as inherited, dask.config.set(pool=inherited):
        with execution_scope(ExecutionOptions(cpus=1, dask_workers=1)):
            assert sum(dask.compute(*(dask.delayed(task)() for _ in range(8)))) == 8
        assert peak == 1
        assert dask.config.get("pool") is inherited
        assert inherited.submit(lambda: 3).result() == 3


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_writer_option_override_records_actual_effective_layout(tmp_path, fmt):
    from frameit.core.configuration import resolved_configuration

    conf = configuration(tmp_path, output={"directory": str(tmp_path / "output"),
                                          "format": fmt, "writer": {"chunks": {"x": 2}}})
    key = "zarr_chunk_size" if fmt == "zarr" else "netcdf_chunk_size"
    options = ExecutionOptions.from_config(conf, **{key: {"x": 3}})
    assert resolved_configuration(conf, options)["output"]["writer"]["chunks"] == {"x": 3}
    options = replace(options, **{key: {}})
    assert not resolved_configuration(conf, options)["output"]["writer"].get("chunks")


@pytest.mark.parametrize("frontend,namespace", [
    ("bind", "product"), ("preflight", "writer"), ("execute", "reader"),
])
@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_failed_union_validation_revokes_shared_and_owning_clearance(
        tmp_path, monkeypatch, frontend, namespace, fmt):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core import coupled, preflight
    from frameit.processing.polar.contracts import require_executable_products

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, resources={"synchronous_export": True},
                         region={"center": {"latitude": -20., "longitude": 60.}},
                         products={"polar": {"radius_km": 2.5, "azimuth_count": 8,
                                             "shared_grid": True}},
                         output={"directory": str(tmp_path / "output"), "format": fmt})
    coupled.bind_sources(conf)
    old_source = conf.simulation_parameter["request_plan"]["sources"]["weather"]
    old_binding = old_source["requests"]["binding"]
    assert old_binding["status"] == "bound"
    assert conf.simulation_parameter["common_polar_target"]
    if namespace == "product":
        conf.yaml_config["products"]["polar"]["processing"] = {"chunks": {"not_an_axis": 1}}
    elif namespace == "writer":
        conf.yaml_config["output"]["writer"]["chunks"] = {"not_an_axis": 1}
    else:
        for source in (conf.sources["weather"], conf.yaml_config["sources"]["weather"]):
            source["reader"] = {"chunks": {"not_an_axis": 1}}
    children = []
    original_bind, original_read = preflight.bind_source, H5NetCDFArrayWrapper.__getitem__

    def bind(child, name, **kwargs):
        children.append(child)
        return original_bind(child, name, **kwargs)

    def no_payload(array, key):
        assert array.variable_name != "q"
        return original_read(array, key)

    monkeypatch.setattr(preflight, "bind_source", bind)
    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
    operation = {"bind": coupled.bind_sources, "preflight": preflight.preflight,
                 "execute": execute_simulation}[frontend]
    with pytest.raises(ValueError, match="chunk|writer"):
        operation(conf)
    assert len(children) == 1
    assert not conf.output_dir.exists()
    assert "common_polar_target" not in conf.simulation_parameter
    assert conf.source_requests["weather"]["binding"] is None
    assert old_source["requests"]["binding"] is None
    with pytest.raises(ValueError, match="owning source"):
        require_executable_products(old_binding, old_source)
    child = children[0]
    source = child.simulation_parameter["request_plan"]["sources"]["weather"]
    assert child.source_requests["weather"]["binding"] is None
    assert source["requests"]["binding"] is None and source["field_binding"] is None


def test_product_chunks_cannot_match_only_an_unrequested_polar_field(tmp_path):
    from frameit.core.coupled import bind_sources

    source = scene().expand_dims(heightAboveGround=[10., 20.]).assign_coords(
        heightAboveGround=("heightAboveGround", [10., 20.], {"axis": "Z", "units": "m"}))
    source["surface"] = scene().q
    source.to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, sources={"weather": {
        "model": "mesonh", "files": str(tmp_path / "input.nc"),
        "variables": {"3d": ["q"], "2d": ["surface"]},
    }}, region={"center": {"latitude": -20., "longitude": 60.}}, products={
        "model_grid": {"processing": {"chunks": {"height_above_ground": 1}}},
        "polar": {"radius_km": 2.5, "azimuth_count": 8, "fields": {"weather": ["surface"]},
                  "processing": {"chunks": {"height_above_ground": 1}}},
    })
    with pytest.raises(ValueError, match="polar.*chunks"):
        bind_sources(conf)
    assert conf.source_requests["weather"]["binding"] is None
    assert not conf.output_dir.exists()


def test_cache_timing_toggle_preserves_plans_masks_counters_and_lru(monkeypatch):
    from frameit.processing.polar import contracts, regrid_plan
    from frameit.testing.numerical.test_polar_regrid_plan import plan_inputs

    source, grid, target = plan_inputs()
    field = source.q.isel(time=0).copy(deep=True)
    field[2, 3] = np.nan
    off = regrid_plan.PolarRegridPlanCache(maxsize=1)
    on = regrid_plan.PolarRegridPlanCache(maxsize=1)
    geometry = contracts.SourceGeometryCache(maxsize=1)
    projected = []
    for offset in (0., .001, 0.):
        moved = target.assign(lon=target.lon + offset)
        reference = on.get(grid, moved)
        expected = on.apply(reference, field)
        with monkeypatch.context() as guard:
            for module in (regrid_plan, contracts):
                guard.setattr(module, "perf_counter", lambda: pytest.fail(
                    "disabled cache timing must not read a clock"))
            actual = off.get(grid, moved, profile=False)
            result = off.apply(actual, field, profile=False)
            cropped, native, footprint = geometry.get(
                source.isel(time=0, drop=True), "longitude", "latitude", profile=False)
        assert actual.construction_s is None
        assert actual.signature == reference.signature
        np.testing.assert_array_equal(actual.supported.weights.toarray(),
                                      reference.supported.weights.toarray())
        for value, wanted in zip(result, expected, strict=True):
            xr.testing.assert_identical(value, wanted)
        assert native.lon.size and cropped.q.size and footprint["x_slice"]
        for key in ("hits", "misses", "builds", "applications", "evictions", "retained_bytes",
                    "retained_entries", "oversized_plans"):
            assert off.statistics(profile=False)[key] == on.statistics()[key]
        projected.append(result[0])
    xr.testing.assert_identical(projected[0], projected[2])
    assert off.statistics(profile=False)["construction_s"] is None
    assert geometry.statistics(profile=False)["fingerprint_s"] is None
    assert off.statistics()["timing"]["measured_calls"]["construction_s"] == 0
    cached = off.get(grid, target)
    assert cached.construction_s is None
    assert off.statistics()["construction_s"] is None
    assert off.statistics()["signature_s"] >= 0
    off.get(grid, target.assign(lon=target.lon + .002))
    timed = off.statistics()
    assert timed["construction_s"] >= 0
    assert timed["timing"]["measured_calls"]["construction_s"] == 1
    geometry.get(source.isel(time=0, drop=True), "longitude", "latitude")
    before = geometry.statistics()
    with monkeypatch.context() as guard:
        guard.setattr(contracts, "perf_counter", lambda: pytest.fail("off after on timestamped"))
        geometry.get(source.isel(time=0, drop=True), "longitude", "latitude", profile=False)
    assert geometry.statistics()["fingerprint_s"] == before["fingerprint_s"]
    assert geometry.statistics()["normalization_s"] is None


def test_v3_injected_cache_profile_changes_do_not_mutate_other_callers(tmp_path, monkeypatch):
    from frameit.processing.polar import contracts, polar_proj, regrid_plan

    scene().to_netcdf(tmp_path / "input.nc")
    cache = regrid_plan.PolarRegridPlanCache(maxsize=1)
    original = polar_proj.execute_source_polar
    saved, signatures = [], []
    monkeypatch.setattr(polar_proj, "execute_source_polar",
                        lambda *a, **k: original(*a, plan_cache=cache, **k))
    for index, profile in enumerate((False, True, False, True)):
        conf = configuration(tmp_path, resources={"synchronous_export": True},
                             region={"center": {"latitude": -20., "longitude": 60.}},
                             products={"polar": {"radius_km": 2.5, "azimuth_count": 8,
                                                 "processing": {"profile": profile}}},
                             output={"directory": str(tmp_path / f"output-{index}")})
        with monkeypatch.context() as guard:
            if not profile:
                for module in (polar_proj, regrid_plan, contracts):
                    guard.setattr(module, "perf_counter", lambda: pytest.fail(
                        "v3 injected cache ignored profile=false"))
            result = execute_simulation(conf)
        with xr.open_dataset(result.products[0]["path"]) as out:
            saved.append(out.q.load())
        report = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())[
            "sources"]["weather"]["polar"]
        signatures.append([r["regrid_plan_signatures"] for r in report["records"]])
        assert report["regrid_performance"]["timing"]["enabled"] is profile
        assert report["regrid_performance"]["construction_s"] is None
    assert cache.counters["builds"] == 1 and cache.counters["hits"] == 11
    assert cache.statistics()["timing"]["measured_calls"]["construction_s"] == 0
    for value in saved[1:]:
        xr.testing.assert_identical(value, saved[0])
    assert all(value == signatures[0] for value in signatures)
    plan = next(iter(cache._plans.values()))
    before = cache.statistics()["timing"]["measured_calls"]["application_s"]
    cache.apply(plan, xr.DataArray(np.ones(plan.geometry.source_lon.shape),
                                  dims=("y_box", "x_box")))
    assert cache.statistics()["timing"]["measured_calls"]["application_s"] == before + 1


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("origin,budget", [("yaml", 3), ("cli", 2), ("automatic", 4)])
def test_native_preflight_keeps_discovery_unbound_and_layouts_pending(
        tmp_path, monkeypatch, allocation, fmt, origin, budget):
    from copy import deepcopy

    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core import coupled, preflight

    source_path = tmp_path / "input.nc"
    scene().to_netcdf(source_path)
    before = hashlib.sha256(source_path.read_bytes()).hexdigest()
    writer = {"chunks": {"x": 4}, **({"shards": {"x": 8}} if fmt == "zarr" else {})}
    conf = configuration(tmp_path, resources={"cpus": 3}, sources={"weather": {
        "model": "mesonh", "files": str(source_path), "variables": {"2d": ["q"]},
        "reader": {"chunks": {"ni": 3}},
    }}, products={"model_grid": {"processing": {"chunks": {"x": 2}}}},
        output={"directory": str(tmp_path / "output"), "format": fmt, "writer": writer})
    if origin == "automatic":
        conf.yaml_config["resources"].pop("cpus")
        conf = SimulationConfig(**to_runtime(conf.yaml_config))
    authored = deepcopy(conf.yaml_config)
    options = ExecutionOptions.from_config(conf, **({"cpus": 2} if origin == "cli" else {}))
    original_read = H5NetCDFArrayWrapper.__getitem__

    def no_payload(array, key):
        assert array.variable_name != "q"
        return original_read(array, key)

    def no_binding(*args, **kwargs):
        pytest.fail("native metadata discovery must not bind scientific requests")

    monkeypatch.setattr(coupled, "bind_sources", no_binding)
    monkeypatch.setattr(preflight, "bind_source", no_binding)
    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
    report = preflight.preflight(conf, execution_options=options)
    assert report["execution_resources"]["cpu_budget"] == budget
    assert report["configuration"]["resources"]["cpus"] == budget
    assert report["configuration"]["resources"]["compute_workers"] == 1
    assert report["configuration"]["resources"]["export_workers"] == budget
    for facts in (report["setting_sources"], report["execution_resources"]["setting_sources"]):
        assert facts["resources.cpus"] == origin
        assert facts["resources.compute_workers"] == "automatic"
    source = report["sources"]["weather"]
    assert source["requests"]["binding"] is None and source.get("field_binding") is None
    assert conf.source_requests["weather"]["binding"] is None
    assert {r["name"] for r in source["records"]} == {"q"}
    assert source["file_inventory"][0]["reason"] == "supplies selected records"
    assert report["deferred_checks"]
    layouts = report["layouts"]
    assert layouts["pending"] == "field/method binding"
    assert layouts["inputs"]["weather"]["requested"] == {"ni": 3}
    assert layouts["inputs"]["weather"]["applications"] == []
    assert layouts["inputs"]["weather"]["estimates"] is None
    product = layouts["products"]["weather.model_grid"]
    assert product["requested"] == {"x": 2}
    assert product["applicable_dimensions"] is None and product["applied_settings"] is None
    assert product["resolved_chunks"] == "pending field/method binding"
    assert layouts["writer"]["requested"] == {
        "chunks": {"x": 4}, "shards": {"x": 8} if fmt == "zarr" else {}}
    assert layouts["writer"]["chunks"] is None and layouts["writer"]["shards"] is None
    assert conf.yaml_config == authored
    assert not conf.output_dir.exists()
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("frontend", ["bind", "execute"])
@pytest.mark.parametrize("namespace", ["reader", "product", "writer"])
def test_native_pending_layouts_still_fail_at_actual_binding(
        tmp_path, monkeypatch, frontend, namespace):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    from frameit.core import coupled, preflight

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path, resources={"synchronous_export": True})
    if namespace == "reader":
        for source in (conf.sources["weather"], conf.yaml_config["sources"]["weather"]):
            source["reader"] = {"chunks": {"not_an_axis": 1}}
    elif namespace == "product":
        conf.yaml_config["products"]["model_grid"] = {"processing": {"chunks": {"not_an_axis": 1}}}
    else:
        conf.yaml_config["output"]["writer"]["chunks"] = {"not_an_axis": 1}
    children = []
    original_bind, original_read = preflight.bind_source, H5NetCDFArrayWrapper.__getitem__

    def bind(child, name, **kwargs):
        children.append(child)
        return original_bind(child, name, **kwargs)

    def no_payload(array, key):
        assert array.variable_name != "q"
        return original_read(array, key)

    monkeypatch.setattr(preflight, "bind_source", bind)
    monkeypatch.setattr(H5NetCDFArrayWrapper, "__getitem__", no_payload)
    report = preflight.preflight(conf)
    assert not children and report["layouts"]["pending"] == "field/method binding"
    assert report["sources"]["weather"]["requests"]["binding"] is None
    operation = coupled.bind_sources if frontend == "bind" else execute_simulation
    with pytest.raises(ValueError, match="chunk|writer"):
        operation(conf)
    assert len(children) == 1
    assert not conf.output_dir.exists()
    for owner in (conf, children[0]):
        source = owner.simulation_parameter["request_plan"]["sources"]["weather"]
        assert owner.source_requests["weather"]["binding"] is None
        assert source["requests"]["binding"] is None and source.get("field_binding") is None
        assert "common_polar_target" not in owner.simulation_parameter


@pytest.mark.parametrize("overrides,match", [
    ({"cpus": 5}, "resources.cpus"),
    ({"cpus": 1, "dask_workers": 2}, "exceeds CPU budget"),
    ({"cpus": 2, "max_workers": 2, "dask_workers": 2}, "exceeds CPU budget"),
])
def test_native_preflight_rejects_invalid_resources_without_binding_or_outputs(
        tmp_path, monkeypatch, allocation, overrides, match):
    from frameit.core import coupled, preflight

    scene().to_netcdf(tmp_path / "input.nc")
    conf = configuration(tmp_path)
    options = ExecutionOptions.from_config(conf, **overrides)
    monkeypatch.setattr(coupled, "bind_sources", lambda *a, **k: pytest.fail(
        "invalid native resources must fail without scientific binding"))
    with pytest.raises(ValueError, match=match):
        preflight.preflight(conf, execution_options=options)
    assert not conf.output_dir.exists()
    assert conf.source_requests["weather"]["binding"] is None


@pytest.mark.parametrize("scheduler,native_threads,synchronous,origins", [
    ("threads", 1, False, ("default", "default", "default")),
    ("synchronous", 1, False, ("explicit", "default", "default")),
    ("threads", 2, False, ("default", "explicit", "default")),
    ("threads", 1, True, ("default", "default", "explicit")),
    ("synchronous", 2, True, ("explicit", "explicit", "explicit")),
])
def test_direct_resource_fallback_origins_survive_resolution_and_provenance(
        tmp_path, allocation, scheduler, native_threads, synchronous, origins):
    from frameit.core.configuration import resolved_configuration, resolved_sources
    from frameit.core.runtime import runtime_provenance

    conf = configuration(tmp_path)
    options = ExecutionOptions(cpus=2, dask_scheduler=scheduler, native_threads=native_threads,
                               synchronous_export=synchronous)
    keys = ("resources.scheduler", "resources.native_threads", "resources.synchronous_export")
    for _ in range(2):
        supplied = dict(options.setting_sources)
        effective, facts = resolve_execution_resources(options)
        assert options.setting_sources == supplied
        assert (effective.dask_scheduler, effective.native_threads,
                effective.synchronous_export) == (scheduler, native_threads, synchronous)
        resolved = resolved_configuration(conf, effective)["resources"]
        assert (resolved["scheduler"], resolved["native_threads"],
                resolved["synchronous_export"]) == (scheduler, native_threads, synchronous)
        for sources in (facts["setting_sources"], effective.setting_sources,
                        resolved_sources(conf, effective),
                        runtime_provenance(facts)["execution_resources"]["setting_sources"]):
            assert tuple(sources[key] for key in keys) == origins
        with execution_scope(effective):
            active = runtime_provenance()["execution_resources"]["setting_sources"]
            assert tuple(active[key] for key in keys) == origins
        options = effective


@pytest.mark.parametrize("nondefault", [False, True])
def test_direct_resource_fallback_never_overwrites_supplied_origins(allocation, nondefault):
    supplied = {"resources.scheduler": "cli", "resources.native_threads": "yaml",
                "resources.synchronous_export": "automatic"}
    options = ExecutionOptions(cpus=2, setting_sources=dict(supplied),
                               dask_scheduler="synchronous" if nondefault else "threads",
                               native_threads=2 if nondefault else 1,
                               synchronous_export=nondefault)
    for _ in range(2):
        effective, facts = resolve_execution_resources(options)
        for sources in (options.setting_sources, effective.setting_sources,
                        facts["setting_sources"]):
            assert {key: sources[key] for key in supplied} == supplied
        options = effective
    assert supplied == {"resources.scheduler": "cli", "resources.native_threads": "yaml",
                        "resources.synchronous_export": "automatic"}


def test_direct_resource_nondefaults_reach_actual_execution_provenance(tmp_path, allocation):
    scene().to_netcdf(tmp_path / "input.nc")
    source_hash = hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest()
    conf = configuration(tmp_path)
    options = ExecutionOptions(cpus=2, dask_scheduler="synchronous", native_threads=2,
                               synchronous_export=True)
    result = execute_simulation(conf, options=options)
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    status = yaml.safe_load((conf.output_dir / "run-status.yaml").read_text())
    resolved = yaml.safe_load((conf.output_dir / "resolved-config.yaml").read_text())["resources"]
    assert status["state"] == "completed" and len(result.products) == 1
    assert resolved["scheduler"] == "synchronous"
    assert resolved["native_threads"] == 2 and resolved["synchronous_export"] is True
    assert options.setting_sources == status["requested_execution_options"]["setting_sources"] == {}
    for sources in (
        result.execution_resources["setting_sources"],
        status["resources"]["setting_sources"],
        status["runtime"]["execution_resources"]["setting_sources"],
        status["effective_execution_options"]["setting_sources"],
        provenance["execution_options"]["setting_sources"],
        provenance["execution_resources"]["setting_sources"],
        provenance["runtime"]["execution_resources"]["setting_sources"],
        provenance["setting_sources"],
    ):
        assert all(sources[key] == "explicit" for key in (
            "resources.scheduler", "resources.native_threads", "resources.synchronous_export"))
    with xr.open_dataset(result.products[0]["path"]) as saved:
        np.testing.assert_array_equal(saved.q, scene().q)
    assert hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest() == source_hash


def test_automatic_reader_description_matches_selected_view_applications(tmp_path):
    source = scene()
    source.to_netcdf(tmp_path / "input.nc", engine="h5netcdf",
                     encoding={"q": {"chunksizes": (1, 3, 3)}})
    before = hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest()
    with xr.open_dataset(tmp_path / "input.nc", engine="h5netcdf") as stored:
        assert stored.q.encoding["chunksizes"] == (1, 3, 3)
    conf = configuration(tmp_path, resources={"synchronous_export": True}, sources={"weather": {
        "model": "mesonh", "files": str(tmp_path / "input.nc"), "variables": {"2d": ["q"]},
        "reader": {"engine": "h5netcdf"}, "time": {"values": ["2024-01-01T01:00:00"]},
    }})
    result = execute_simulation(conf)
    provenance = yaml.safe_load((conf.output_dir / "run-provenance.yaml").read_text())
    layout = provenance["layouts"]["inputs"]["weather"]
    assert layout["requested"] == {} and layout["targets"]["q"] == {}
    assert layout["automatic"] == (
        "Dask resolves chunks on selected backend views; applications record actual sizes")
    assert layout["applications"] and all(
        item["field"] == "q" and item["chunks"] == {"time": [1], "nj": [9], "ni": [9]}
        for item in layout["applications"])
    with xr.open_dataset(result.products[0]["path"]) as saved:
        np.testing.assert_array_equal(saved.q, source.q.isel(time=[1]))
    assert hashlib.sha256((tmp_path / "input.nc").read_bytes()).hexdigest() == before
