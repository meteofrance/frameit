"""Last-known attempt records on compact fixtures, not crash recovery or replay."""

from __future__ import annotations

import hashlib
import multiprocessing
import os
import select
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import dask.array as da
import numpy as np
import pytest
import xarray as xr
import yaml
from dask import delayed

from frameit.core.configuration import load_runtime, resolve_schema, to_runtime
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.testing.documentation_example import create_first_run_input


def document():
    return {
        "schema_version": 3,
        "run": {"name": "records"},
        "sources": {"weather": {"model": "arome", "files": "./input.nc",
                                "variables": {"2d": ["instructional_scalar"]}}},
        "output": {"directory": "./out"},
        "resources": {"cpus": 1, "synchronous_export": True, "scheduler": "synchronous"},
    }


def record(root, name):
    return yaml.safe_load((root / name).read_text())


def observe_checkpoint_writes(monkeypatch, observe):
    original_open = Path.open

    def opening(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.suffix == ".partial" and stream.writable():
            write = stream.write
            stream.write = lambda text: observe(stream, write, text)
        return stream

    monkeypatch.setattr(Path, "open", opening)


@pytest.mark.parametrize("portable", [False, True], ids=["installed-emitter", "python-emitter"])
def test_checkpoint_streams_safe_yaml_before_publication(tmp_path, monkeypatch, portable):
    from frameit.core.configuration import read_yaml
    from frameit.utils.atomic import write_yaml_atomic

    if portable:
        monkeypatch.delattr(yaml, "CSafeDumper", raising=False)
    path = tmp_path / "run-provenance.yaml"
    path.write_text("state: running\n")
    chunks = []

    def observe(stream, write, text):
        if not chunks:
            assert Path(stream.name).parent == tmp_path and path.read_text() == "state: running\n"
        chunks.append(len(text))
        return write(text)

    observe_checkpoint_writes(monkeypatch, observe)
    levels = [1, -0.0, None]
    value = {"units": "m s⁻¹", "label": "mesuré 🌀", "run": "001", "day": "2022-02-01",
             "levels": levels, "again": levels, "notes": ["x" * 32] * 2000}
    write_yaml_atomic(path, value)
    assert sum(n > 0 for n in chunks) > 1
    for loaded in (record(tmp_path, path.name), read_yaml(path)):
        assert loaded == value and list(loaded) == list(value)
        assert loaded["again"] is loaded["levels"]
        assert np.signbit(loaded["levels"][1])


def test_checkpoint_preserves_escaped_filesystem_name(tmp_path):
    from frameit.utils.atomic import write_yaml_atomic

    path = tmp_path / "run-request.yaml"
    value = {"prefix": "a" * 32768, "source": os.fsdecode(b"input-\x80.nc")}
    write_yaml_atomic(path, value)
    assert record(tmp_path, path.name) == value


def test_checkpoint_keeps_the_registered_safe_scalar_policy(tmp_path, monkeypatch):
    from frameit.utils.atomic import write_yaml_atomic

    monkeypatch.setattr(yaml.SafeDumper, "yaml_representers",
                        dict(yaml.SafeDumper.yaml_representers))
    yaml.SafeDumper.add_representer(float, lambda dumper, x: dumper.represent_str(format(x, ".3f")))
    path = tmp_path / "run-provenance.yaml"
    write_yaml_atomic(path, {"threshold": 1.5})
    assert record(tmp_path, path.name) == {"threshold": "1.500"}


def test_checkpoint_encoding_retry_does_not_consume_metadata_twice(tmp_path, monkeypatch):
    from frameit.utils.atomic import write_yaml_atomic

    policy = yaml.representer.SafeRepresenter
    monkeypatch.setattr(policy, "yaml_representers", dict(policy.yaml_representers))
    policy.add_representer(type(iter([])), lambda dumper, values: dumper.represent_list(list(values)))
    path = tmp_path / "run-request.yaml"
    source = os.fsdecode(b"input-\x80.nc")
    write_yaml_atomic(path, {"levels": iter([850, 500]), "source": source})
    assert record(tmp_path, path.name) == {"levels": [850, 500], "source": source}


def test_checkpoint_accepts_registered_numpy_string(tmp_path, monkeypatch):
    from frameit.utils.atomic import write_yaml_atomic

    policy = yaml.representer.SafeRepresenter
    monkeypatch.setattr(policy, "yaml_representers", dict(policy.yaml_representers))
    policy.add_representer(np.str_, policy.represent_str)
    path = tmp_path / "run-provenance.yaml"
    write_yaml_atomic(path, {"station": np.str_("001")})
    assert record(tmp_path, path.name) == {"station": "001"}


def test_checkpoint_honors_safe_alias_policy(tmp_path, monkeypatch):
    from frameit.utils.atomic import write_yaml_atomic

    monkeypatch.setattr(yaml.SafeDumper, "ignore_aliases", lambda self, value: True)
    shared = [1, 2]
    path = tmp_path / "run-status.yaml"
    write_yaml_atomic(path, {"a": shared, "b": shared})
    loaded = record(tmp_path, path.name)
    assert loaded == {"a": [1, 2], "b": [1, 2]} and loaded["a"] is not loaded["b"]


def test_checkpoint_keeps_custom_safe_resolver(tmp_path, monkeypatch):
    import re

    from frameit.utils.atomic import write_yaml_atomic

    class RecordLoader(yaml.SafeLoader):
        pass

    monkeypatch.setattr(yaml.SafeDumper, "yaml_implicit_resolvers",
                        deepcopy(yaml.SafeDumper.yaml_implicit_resolvers))
    for policy in (RecordLoader, yaml.SafeDumper):
        policy.add_implicit_resolver("tag:yaml.org,2002:null", re.compile("^MISSING$"), ["M"])
    path = tmp_path / "run-provenance.yaml"
    write_yaml_atomic(path, {"source": "MISSING"})
    assert yaml.load(path.read_text(), Loader=RecordLoader) == {"source": "MISSING"}


def test_invalid_checkpoint_preserves_last_complete_record(tmp_path):
    from frameit.utils.atomic import write_yaml_atomic

    path = tmp_path / "run-status.yaml"
    path.write_text("state: running\n")
    with pytest.raises(FileExistsError):
        write_yaml_atomic(path, {"bad": object()}, overwrite=False)
    with pytest.raises(yaml.representer.RepresenterError):
        write_yaml_atomic(path, {"bad": object()})
    assert path.read_text() == "state: running\n"
    assert list(tmp_path.iterdir()) == [path]


def test_partial_checkpoint_stream_is_never_published(tmp_path, monkeypatch):
    from frameit.utils.atomic import write_yaml_atomic

    path = tmp_path / "run-status.yaml"
    path.write_text("state: running\n")

    def fail_write(stream, write, text):
        write("state: completed\n")
        stream.flush()
        assert record(tmp_path, path.name) == {"state": "running"}
        raise OSError("checkpoint write interrupted")

    observe_checkpoint_writes(monkeypatch, fail_write)
    with pytest.raises(OSError, match="checkpoint write interrupted"):
        write_yaml_atomic(path, {"state": "completed"})
    assert list(tmp_path.iterdir()) == [path]
    assert record(tmp_path, path.name) == {"state": "running"}


@pytest.mark.parametrize("constructor", [
    "yaml", "preset_yaml", "public_yaml", "mapping", "preset_mapping",
])
def test_early_failure_keeps_captured_request_and_original_bases(
        tmp_path, monkeypatch, constructor):
    """Losing raw values at resolution, or re-reading edited YAML, breaks recovery."""
    base, launch, later = (tmp_path / name for name in ("configuration", "launch", "later"))
    for directory in (base, launch, later):
        directory.mkdir()
    create_first_run_input(base / "input.nc")
    raw = document()
    authored = deepcopy(raw)
    path = base / "case.yaml"
    path.write_text(yaml.safe_dump(raw))
    monkeypatch.chdir(launch)
    if constructor == "yaml":
        conf = SimulationConfig(**load_runtime(path))
    elif constructor == "preset_yaml":
        conf = SimulationConfig.from_yaml_with_model_preset(path)
    elif constructor == "public_yaml":
        conf = SimulationConfig.from_yaml(path)
    elif constructor == "mapping":
        conf = SimulationConfig(**to_runtime(raw, base_dir=base))
    else:
        monkeypatch.chdir(base)
        conf = SimulationConfig.from_mapping_with_model_preset(raw)
        monkeypatch.chdir(launch)
    capture_launch = base if constructor == "preset_mapping" else launch
    raw["sources"]["weather"]["files"] = "./different.nc"
    raw["output"]["directory"] = "./different-output"
    path.rename(base / "moved.yaml")
    path.write_text("schema_version: 3\nsources: {}\n")
    monkeypatch.chdir(later)
    options = ExecutionOptions.from_config(conf, max_workers=9)

    def fail_before_processing(runner, **kwargs):
        root = runner.output_dir
        request_bytes = (root / "run-request.yaml").read_bytes()
        request = record(root, "run-request.yaml")
        assert request["record_version"] == 1
        assert request["request_kind"] == ("yaml" if "yaml" in constructor else "mapping")
        assert request["authored_configuration"] == authored
        assert request["request_path"] == (str(path) if "yaml" in constructor else None)
        assert request["path_bases"] == {
            "configuration_directory": str(base), "launch_directory": str(capture_launch)}
        assert request["overrides"] == {}
        assert request["requested_execution_options"]["max_workers"] == 9
        assert request["runtime"]["code_revision"]
        assert request["runtime"]["python"].startswith("3.13.")
        resolved = record(root, "resolved-config.yaml")
        resolve_schema(resolved)
        assert resolved["sources"]["weather"]["files"] == str(base / "input.nc")
        assert resolved["resources"]["export_workers"] == 1
        status = record(root, "run-status.yaml")
        provenance = record(root, "run-provenance.yaml")
        for facts in (status, provenance):
            assert facts["request_record"] == "run-request.yaml"
            assert facts["pending"] == ["processing", "publication", "cleanup"]
            assert facts["products"] == []
            assert facts["planned_products"][0]["path"] == (
                "products/records.weather.model_grid.nc")
            assert facts["updated_at"]
        assert status["state"] == "running" and status["finished_at"] is None
        assert provenance["input_inventory"] == [str(base / "input.nc")]
        assert provenance["binding"]["weather"]["status"] == "bound"
        assert provenance["execution_options"]["max_workers"] == 1
        assert provenance["sources"] == {}
        (root / "request-bytes").write_bytes(request_bytes)
        raise RuntimeError("before source processing")

    monkeypatch.setattr("frameit.core.runner.FrameitRunner.run", fail_before_processing)
    with pytest.raises(RuntimeError, match="before source processing"):
        execute_simulation(conf, options)
    root = conf.output_dir
    status = record(root, "run-status.yaml")
    assert status["state"] == "failed"
    assert status["error"] == {
        "type": "RuntimeError", "message": "before source processing", "code": "E0999",
    }
    assert status["pending"] == ["processing", "publication"]
    assert status["products"] == []
    assert status["finished_at"] and status["updated_at"] >= status["started_at"]
    provenance = record(root, "run-provenance.yaml")
    assert provenance["pending"] == status["pending"]
    assert provenance["error"] == status["error"]
    assert (root / "run-request.yaml").read_bytes() == (root / "request-bytes").read_bytes()
    assert not (root / ".frameit-run.lock").exists()


def test_runtime_only_request_does_not_invent_authored_configuration(tmp_path, monkeypatch):
    create_first_run_input(tmp_path / "input.nc")
    runtime = to_runtime(document(), base_dir=tmp_path)
    runtime.pop("request_context", None)
    conf = SimulationConfig(**runtime)

    def fail(runner, **kwargs):
        raise RuntimeError("runtime-only failure")

    monkeypatch.setattr("frameit.core.runner.FrameitRunner.run", fail)
    with pytest.raises(RuntimeError, match="runtime-only"):
        execute_simulation(conf)
    request = record(conf.output_dir, "run-request.yaml")
    assert request["request_kind"] == "runtime"
    assert request["authored_configuration"] is None and request["request_path"] is None
    assert request["path_bases"]["configuration_directory"] is None
    assert request["path_bases"]["launch_directory"] == str(Path.cwd())


@pytest.mark.parametrize("kind", ["yaml", "mapping"])
@pytest.mark.parametrize("path_override", ["./attempt", Path("attempt")], ids=["text", "path"])
def test_raw_operational_overrides_keep_launch_base_separate_from_yaml(
        tmp_path, monkeypatch, kind, path_override):
    base, launch = tmp_path / "configuration", tmp_path / "launch"
    base.mkdir()
    launch.mkdir()
    create_first_run_input(base / "input.nc")
    raw = document()
    raw["output"]["overwrite"] = True
    authored = deepcopy(raw)
    path = base / "case.yaml"
    path.write_text(yaml.safe_dump(raw))
    overrides = {"output_directory": path_override, "cpus": 1,
                 "overwrite": False, "log_level": "ERROR"}
    original_overrides = {"output_directory": str(path_override), "cpus": 1,
                          "overwrite": False, "log_level": "ERROR"}
    if kind == "yaml":
        runtime = load_runtime(path, launch_dir=launch, overrides=overrides)
    else:
        runtime = to_runtime(raw, base_dir=base, launch_dir=launch, overrides=overrides)
    conf = SimulationConfig(**runtime)
    raw["output"]["overwrite"] = False
    overrides["output_directory"] = "./changed"
    path.unlink()
    monkeypatch.chdir(tmp_path)

    def fail(runner, **kwargs):
        raise RuntimeError("overridden failure")

    monkeypatch.setattr("frameit.core.runner.FrameitRunner.run", fail)
    with pytest.raises(RuntimeError, match="overridden failure"):
        execute_simulation(conf)
    assert conf.output_dir == launch / "attempt"
    request = record(conf.output_dir, "run-request.yaml")
    assert request["authored_configuration"] == authored
    assert request["overrides"] == original_overrides
    assert request["path_bases"] == {
        "configuration_directory": str(base), "launch_directory": str(launch)}
    resolved = record(conf.output_dir, "resolved-config.yaml")
    assert resolved["sources"]["weather"]["files"] == str(base / "input.nc")
    assert resolved["output"]["directory"] == str(launch / "attempt")
    assert resolved["output"]["overwrite"] is False
    assert resolved["logging"]["level"] == "ERROR"
    provenance = record(conf.output_dir, "run-provenance.yaml")
    for key in ("output.directory", "output.overwrite", "logging.level", "resources.cpus"):
        assert provenance["setting_sources"][key] == "cli"


def two_sources(tmp_path, fmt, synchronous):
    create_first_run_input(tmp_path / "input.nc")
    xr.Dataset({"sea_scalar": (("time_counter", "y", "x"), [
        [[0., np.nan], [2., 3.]], [[10., 11.], [12., 13.]]], {"units": "1"})},
        coords={
            "time_counter": ("time_counter", np.array(
                ["2000-01-01T00:30", "2000-01-01T01:30"], dtype="datetime64[ns]"),
                {"standard_name": "time", "axis": "T"}),
            "nav_lat": (("y", "x"), [[-20., -20.], [-19.99, -19.99]],
                        {"standard_name": "latitude", "units": "degrees_north"}),
            "nav_lon": (("y", "x"), [[60., 60.01], [60., 60.01]],
                        {"standard_name": "longitude", "units": "degrees_east"}),
        }).to_netcdf(tmp_path / "ocean.nc")
    raw = document()
    raw["sources"]["water"] = {"model": "nemo", "files": "./ocean.nc",
                                "variables": {"2d": ["sea_scalar"]}}
    raw["output"]["format"] = fmt
    raw["resources"]["synchronous_export"] = synchronous
    return SimulationConfig(**to_runtime(raw, base_dir=tmp_path))


def gated_values(values, ready, release, outcome):
    """A real writer waits on bounded IPC, then fails or completes its real data."""
    ready.set()
    if not release.wait(20):
        raise TimeoutError("test did not release the second product")
    if outcome == "failed":
        raise OSError("second product failed")
    if outcome == "interrupted":
        raise KeyboardInterrupt("second product interrupted")
    return values


def gate_second_product(monkeypatch, ready, release, outcome):
    from frameit.core.runner import FrameitRunner

    original_run = FrameitRunner.run

    def run(runner, **kwargs):
        result = original_run(runner, **kwargs)
        dataset = runner.field_products[("water", "model_grid")]
        field = dataset.sea_scalar
        field.data = da.from_delayed(
            delayed(gated_values)(field.data, ready, release, outcome),
            shape=field.shape, dtype=field.dtype)
        return result

    monkeypatch.setattr(FrameitRunner, "run", run)


def signal_checkpoint(monkeypatch, checkpointed):
    import frameit.core.run_state as run_state

    original_write = run_state.write_yaml_atomic

    def write(path, value, **kwargs):
        result = original_write(path, value, **kwargs)
        if Path(path).name == "run-status.yaml" and value["products"]:
            checkpointed.set()
        return result

    monkeypatch.setattr(run_state, "write_yaml_atomic", write)


def ordinary_reader(root, product, source, field, clock, fmt):
    subprocess.run([sys.executable, "-c", """
import sys
import numpy as np
import xarray as xr
engine, field, clock = sys.argv[3:]
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
kwargs = {'engine': 'zarr', 'consolidated': False} if engine == 'zarr' else {}
with xr.open_dataset(sys.argv[1], **kwargs) as out, xr.open_dataset(sys.argv[2]) as source:
    assert set(out.data_vars) == {field}
    np.testing.assert_array_equal(out[field].values, source[field].values)
    np.testing.assert_array_equal(out.time.values, source[clock].values)
    assert out[field].dtype == source[field].dtype
    assert out[field].attrs == source[field].attrs
    assert out.attrs['product_type'] == 'model_grid'
    assert out.attrs['source_id'] in ('weather', 'water')
    assert out.attrs['frameit_version']
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", str(root / product["path"]), str(source), fmt, field, clock],
        check=True, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("synchronous", [True, False], ids=["sync", "spawn"])
@pytest.mark.parametrize("outcome", ["failed", "interrupted"])
def test_first_publication_is_checkpointed_while_second_is_still_running(
        tmp_path, monkeypatch, fmt, synchronous, outcome):
    """A final-except-only inventory loses the first publication on node loss."""
    conf = two_sources(tmp_path, fmt, synchronous)
    originals = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (tmp_path / "input.nc", tmp_path / "ocean.nc")}
    import frameit.core.run_state as run_state

    writes = []
    original_write = run_state.write_yaml_atomic

    def write(path, value, **kwargs):
        if Path(path).name == "run-request.yaml":
            writes.append(deepcopy(value))
        return original_write(path, value, **kwargs)

    monkeypatch.setattr(run_state, "write_yaml_atomic", write)
    with multiprocessing.get_context("spawn").Manager() as manager:
        ready, release = manager.Event(), manager.Event()
        checkpointed = manager.Event()
        signal_checkpoint(monkeypatch, checkpointed)
        gate_second_product(monkeypatch, ready, release, outcome)
        with ThreadPoolExecutor(max_workers=1) as pool:
            attempt = pool.submit(execute_simulation, conf)
            try:
                assert ready.wait(20), "second writer did not reach its gate"
                assert checkpointed.wait(20), "first publication was not checkpointed"
                status = record(conf.output_dir, "run-status.yaml")
                provenance = record(conf.output_dir, "run-provenance.yaml")
                request_bytes = (conf.output_dir / "run-request.yaml").read_bytes()
                for facts in (status, provenance):
                    assert len(facts["planned_products"]) == 2
                    assert len(facts["products"]) == 1
                    assert facts["products"][0]["source"] == "weather"
                    assert facts["products"][0]["path"] == (
                        f"products/records.weather.model_grid.{('nc' if fmt == 'netcdf' else fmt)}")
                    assert facts["products"][0]["size_bytes"] > 0
                    assert facts["pending"] == ["publication", "cleanup"]
                assert status["state"] == "running" and status["finished_at"] is None
                assert status["updated_at"] > status["started_at"]
                assert len(writes) == 1
                ordinary_reader(conf.output_dir, status["products"][0],
                                tmp_path / "input.nc", "instructional_scalar", "valid_time", fmt)
                second = conf.output_dir / status["planned_products"][1]["path"]
                assert not second.exists()
            finally:
                release.set()
            with pytest.raises(OSError if outcome == "failed" else KeyboardInterrupt,
                               match=f"second product {outcome}"):
                attempt.result(timeout=30)
    status = record(conf.output_dir, "run-status.yaml")
    provenance = record(conf.output_dir, "run-provenance.yaml")
    assert status["state"] == outcome and status["pending"] == ["publication"]
    assert len(status["products"]) == 1 and len(status["planned_products"]) == 2
    assert status["error"]["type"] == ("OSError" if outcome == "failed" else "KeyboardInterrupt")
    assert provenance["products"] == status["products"]
    assert provenance["pending"] == status["pending"]
    assert provenance["state"] == outcome
    assert len(writes) == 1
    assert (conf.output_dir / "run-request.yaml").read_bytes() == request_bytes
    assert not (conf.output_dir / ".frameit-run.lock").exists()
    assert not list(conf.output_dir.rglob("*.partial"))
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest
               for path, digest in originals.items())


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_parent_interruption_drains_actual_spawned_publications(tmp_path, monkeypatch, fmt):
    """Executor shutdown may finish a worker after the parent stops waiting normally."""
    import frameit.io.netcdf_export as exporter

    conf = two_sources(tmp_path, fmt, False)
    original_completed = exporter.as_completed
    with multiprocessing.get_context("spawn").Manager() as manager:
        ready, release = manager.Event(), manager.Event()
        checkpointed = manager.Event()
        signal_checkpoint(monkeypatch, checkpointed)
        gate_second_product(monkeypatch, ready, release, "completed")

        def interrupted(futures):
            yield next(original_completed(futures))
            assert ready.wait(20)
            raise SystemExit(143)

        monkeypatch.setattr(exporter, "as_completed", interrupted)
        with ThreadPoolExecutor(max_workers=1) as pool:
            attempt = pool.submit(execute_simulation, conf)
            try:
                assert ready.wait(20)
                assert checkpointed.wait(20)
                assert len(record(conf.output_dir, "run-status.yaml")["products"]) == 1
            finally:
                release.set()
            with pytest.raises(SystemExit) as caught:
                attempt.result(timeout=30)
            assert caught.value.code == 143
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "interrupted"
    assert len(status["products"]) == 2
    assert status["pending"] == ["publication"]
    assert record(conf.output_dir, "run-provenance.yaml")["products"] == status["products"]
    for product in status["products"]:
        weather = product["source"] == "weather"
        ordinary_reader(
            conf.output_dir, product, tmp_path / ("input.nc" if weather else "ocean.nc"),
            "instructional_scalar" if weather else "sea_scalar",
            "valid_time" if weather else "time_counter", fmt)


@pytest.mark.parametrize("synchronous", [True, False], ids=["sync", "spawn"])
def test_failed_checkpoint_never_claims_success_or_loses_completed_products(
        tmp_path, monkeypatch, synchronous):
    import frameit.core.run_state as run_state

    conf = two_sources(tmp_path, "netcdf", synchronous)
    original_write = run_state.write_yaml_atomic
    failed = False

    def fail_once(path, value, **kwargs):
        nonlocal failed
        if (Path(path).name == "run-status.yaml" and value["products"] and not failed):
            failed = True
            raise OSError("publication checkpoint failed")
        return original_write(path, value, **kwargs)

    monkeypatch.setattr(run_state, "write_yaml_atomic", fail_once)
    with pytest.raises(OSError, match="publication checkpoint failed"):
        execute_simulation(conf)
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "failed"
    assert status["error"]["message"] == "publication checkpoint failed"
    assert len(status["products"]) == (1 if synchronous else 2)
    assert status["pending"] == ["publication"]
    assert record(conf.output_dir, "run-provenance.yaml")["products"] == status["products"]
    assert not (conf.output_dir / ".frameit-run.lock").exists()


def test_cleanup_failure_keeps_complete_products_and_pending_cleanup(tmp_path, monkeypatch):
    from frameit.core.runner import FrameitRunner

    conf = two_sources(tmp_path, "netcdf", True)
    original_run = FrameitRunner.run

    def run(runner, *args, **kwargs):
        result = original_run(runner, *args, **kwargs)
        consumer = runner.resources._datasets[0]
        data = consumer.resources._datasets[0]
        original_close = data._close

        def close():
            original_close()
            raise OSError("input cleanup failed")

        data.set_close(close)
        return result

    monkeypatch.setattr(FrameitRunner, "run", run)
    with pytest.raises(OSError, match="input cleanup failed"):
        execute_simulation(conf)
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "failed" and len(status["products"]) == 2
    assert status["pending"] == ["cleanup"]
    assert record(conf.output_dir, "run-provenance.yaml")["error"] == status["error"]


def test_failed_provenance_checkpoint_still_updates_authoritative_status(tmp_path, monkeypatch):
    import frameit.core.run_state as run_state

    conf = two_sources(tmp_path, "netcdf", True)
    original_write = run_state.write_yaml_atomic

    def fail_provenance(path, value, **kwargs):
        if Path(path).name == "run-provenance.yaml" and value["products"]:
            raise OSError("provenance device failure")
        return original_write(path, value, **kwargs)

    monkeypatch.setattr(run_state, "write_yaml_atomic", fail_provenance)
    with pytest.raises(OSError, match="provenance device failure"):
        execute_simulation(conf)
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "failed"
    assert len(status["products"]) == 1
    assert status["error"]["message"] == "provenance device failure"
    assert status["finished_at"] and not (conf.output_dir / ".frameit-run.lock").exists()


def test_failed_final_checkpoint_cannot_leave_a_completed_attempt(tmp_path, monkeypatch):
    import frameit.core.run_state as run_state

    conf = two_sources(tmp_path, "netcdf", True)
    original_write = run_state.write_yaml_atomic

    def fail_final(path, value, **kwargs):
        if Path(path).name == "run-provenance.yaml" and value["state"] == "completed":
            raise OSError("final provenance failure")
        return original_write(path, value, **kwargs)

    monkeypatch.setattr(run_state, "write_yaml_atomic", fail_final)
    with pytest.raises(OSError, match="final provenance failure"):
        execute_simulation(conf)
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "failed"
    assert status["error"]["message"] == "final provenance failure"
    assert len(status["products"]) == 2 and status["pending"] == ["cleanup"]


def test_checkpoint_failure_does_not_erase_the_original_processing_error(tmp_path, monkeypatch):
    import frameit.core.run_state as run_state

    conf = two_sources(tmp_path, "netcdf", True)
    original_write = run_state.write_yaml_atomic

    def fail_processing(runner, **kwargs):
        raise RuntimeError("original processing failure")

    def fail_record(path, value, **kwargs):
        if Path(path).name == "run-provenance.yaml" and value.get("error"):
            raise OSError("secondary checkpoint failure")
        return original_write(path, value, **kwargs)

    monkeypatch.setattr("frameit.core.runner.FrameitRunner.run", fail_processing)
    monkeypatch.setattr(run_state, "write_yaml_atomic", fail_record)
    with pytest.raises(RuntimeError, match="original processing failure") as exc:
        execute_simulation(conf)
    assert any("[E1808]" in note and "secondary checkpoint failure" in note
               for note in exc.value.__notes__)
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "failed"
    assert status["error"] == {
        "type": "RuntimeError", "message": "original processing failure", "code": "E0999",
    }
    assert status["products"] == [] and status["pending"] == ["processing", "publication"]


def test_processing_failure_retains_facts_already_observed_by_real_runner(tmp_path, monkeypatch):
    from frameit.core.runner import FrameitRunner

    conf = two_sources(tmp_path, "netcdf", True)
    original_run = FrameitRunner.run

    def fail(runner, **kwargs):
        original_run(runner, **kwargs)
        raise OSError("processing did not return normally")

    monkeypatch.setattr(FrameitRunner, "run", fail)
    with pytest.raises(OSError, match="did not return normally"):
        execute_simulation(conf)
    provenance = record(conf.output_dir, "run-provenance.yaml")
    assert provenance["sources"]["weather"]["selected_times"] == [
        "2000-01-01T00:00:00.000000000", "2000-01-01T01:00:00.000000000"]
    assert provenance["sources"]["water"]["selected_times"] == [
        "2000-01-01T00:30:00.000000000", "2000-01-01T01:30:00.000000000"]
    assert provenance["pending"] == ["processing", "publication"]
    assert provenance["products"] == [] and provenance["state"] == "failed"


@pytest.mark.parametrize("strict", [False, True], ids=["keep-prefix", "require-complete"])
def test_shortened_tracking_preserves_existing_incomplete_and_failure_states(
        tmp_path, monkeypatch, strict):
    from frameit.core.runner import FrameitRunner

    conf = two_sources(tmp_path, "netcdf", True)
    original_run = FrameitRunner.run

    def shortened(runner, **kwargs):
        result = original_run(runner, **kwargs)
        runner.track = xr.Dataset(attrs={
            "tracking_complete": False, "tracking_termination_reason": "test shortened track"})
        return result

    monkeypatch.setattr(FrameitRunner, "run", shortened)
    options = ExecutionOptions.from_config(conf, require_complete_tracking=strict)
    if strict:
        with pytest.raises(ValueError, match="Tracking is incomplete"):
            execute_simulation(conf, options)
    else:
        assert not execute_simulation(conf, options).tracking_complete
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == ("failed" if strict else "incomplete")
    assert status["tracking_complete"] is False
    assert status["tracking_termination_reason"] == "test shortened track"
    assert len(status["products"]) == (0 if strict else 2)
    assert status["pending"] == (["publication"] if strict else [])
    assert record(conf.output_dir, "run-provenance.yaml")["state"] == status["state"]


@pytest.mark.parametrize("name", [
    "run-request.yaml", "resolved-config.yaml", "run-provenance.yaml", "run-status.yaml",
])
@pytest.mark.parametrize("contents", ["[broken", "[]", "unrelated: work\n"])
def test_explicit_overwrite_refuses_unrecognized_record_artifacts(
        tmp_path, name, contents):
    conf = two_sources(tmp_path, "netcdf", True)
    conf.output_dir.mkdir()
    occupied = conf.output_dir / name
    occupied.write_text(contents)
    with pytest.raises(ValueError, match="unrelated|unrecognized|record"):
        execute_simulation(conf, ExecutionOptions.from_config(conf, overwrite=True))
    assert occupied.read_text() == contents
    assert list(conf.output_dir.iterdir()) == [occupied]


@pytest.mark.parametrize("kind", ["hardlink", "symlink", "directory"])
def test_request_record_cannot_replace_or_contain_a_source(tmp_path, kind):
    conf = two_sources(tmp_path, "netcdf", True)
    source = tmp_path / "input.nc"
    original = source.read_bytes()
    conf.output_dir.mkdir()
    target = conf.output_dir / "run-request.yaml"
    if kind == "hardlink":
        target.hardlink_to(source)
    elif kind == "symlink":
        target.symlink_to(source)
    else:
        target.mkdir()
        source.rename(target / "source.nc")
        source = target / "source.nc"
        conf.sources["weather"]["files"] = str(source)
        conf.yaml_config["sources"]["weather"]["files"] = str(source)
    with pytest.raises(ValueError, match="source input"):
        execute_simulation(conf, ExecutionOptions.from_config(conf, overwrite=True))
    assert source.read_bytes() == original
    assert not (conf.output_dir / ".frameit-run.lock").exists()
    assert not (conf.output_dir / "run-status.yaml").exists()
    assert not (conf.output_dir / "logs").exists()


@pytest.mark.parametrize("name", [
    "run-request.yaml", "resolved-config.yaml", "run-provenance.yaml", "run-status.yaml",
])
def test_record_no_clobber_includes_broken_symlinks(tmp_path, name):
    from frameit.core.run_state import owned_run

    root = tmp_path / "out"
    root.mkdir()
    target = root / name
    target.symlink_to(tmp_path / "missing")
    for overwrite in (False, True):
        with pytest.raises((FileExistsError, ValueError), match="artifacts|record"):
            with owned_run(root, overwrite=overwrite, initial={}):
                pytest.fail("an unrelated record alias must not be replaced")
        assert target.is_symlink() and target.readlink() == tmp_path / "missing"
        assert list(root.iterdir()) == [target]


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
def test_explicit_recognized_replacement_preserves_stale_orphan_and_user_evidence(
        tmp_path, fmt):
    conf = two_sources(tmp_path, fmt, True)
    execute_simulation(conf)
    status_path = conf.output_dir / "run-status.yaml"
    status = record(conf.output_dir, status_path.name)
    status.update(state="running", finished_at=None)
    status_path.write_text(yaml.safe_dump(status))
    lock = conf.output_dir / ".frameit-run.lock"
    lock.write_text("pid: 999999999\n")
    orphan = conf.output_dir / "products/.frameit-orphan.partial"
    orphan.write_text("interrupted unpublished bytes")
    backup = conf.output_dir / "products/.frameit-orphan.backup"
    backup.mkdir()
    (backup / "evidence").write_text("old backup")
    note = conf.output_dir / "previous-failure.txt"
    note.write_text("earlier failure evidence")
    before = {path: path.read_bytes() for path in conf.output_dir.rglob("*") if path.is_file()}
    with pytest.raises(FileExistsError, match="locked"):
        execute_simulation(conf, ExecutionOptions.from_config(conf, overwrite=True))
    assert all(path.read_bytes() == value for path, value in before.items())
    # The test created this stopped-owner lock; production must never reclaim it.
    lock.unlink()
    without_lock = {
        path: path.read_bytes() for path in conf.output_dir.rglob("*") if path.is_file()}
    with pytest.raises(FileExistsError, match="Existing run artifacts"):
        execute_simulation(conf)
    assert all(path.read_bytes() == value for path, value in without_lock.items())
    execute_simulation(conf, ExecutionOptions.from_config(conf, overwrite=True))
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "completed" and status["pending"] == []
    assert len(status["products"]) == 2
    assert orphan.read_text() == "interrupted unpublished bytes"
    assert (backup / "evidence").read_text() == "old backup"
    assert note.read_text() == "earlier failure evidence"
    assert record(conf.output_dir, "run-request.yaml")["requested_execution_options"]["overwrite"]
    assert record(conf.output_dir, "run-provenance.yaml")["pending"] == []


@pytest.mark.parametrize("fmt", ["netcdf", "zarr"])
@pytest.mark.parametrize("kill", [False, True], ids=["sigterm", "sigkill"])
def test_signal_after_first_publication_leaves_truthful_last_known_records(
        tmp_path, fmt, kill):
    conf = two_sources(tmp_path, fmt, True)
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(
        conf.request_context["authored_configuration"], sort_keys=False))
    script = tmp_path / "attempt.py"
    script.write_text("""
import os, signal, sys
import dask.array as da
from dask import delayed
from frameit.core.execution import execute_simulation
from frameit.core.runner import FrameitRunner
from frameit.core.runtime import termination_scope
from frameit.core.settings_class import SimulationConfig
def wait(values):
    os.write(int(sys.argv[2]), b'R')
    while True:
        signal.pause()
if __name__ == '__main__':
    original = FrameitRunner.run
    def run(self, **kwargs):
        result = original(self, **kwargs)
        field = self.field_products[('water', 'model_grid')].sea_scalar
        field.data = da.from_delayed(
            delayed(wait)(field.data), shape=field.shape, dtype=field.dtype)
        return result
    FrameitRunner.run = run
    with termination_scope():
        execute_simulation(SimulationConfig.from_yaml(sys.argv[1]))
""")
    read_fd, write_fd = os.pipe()
    process = subprocess.Popen(
        [sys.executable, str(script), str(path), str(write_fd)], pass_fds=(write_fd,),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    os.close(write_fd)
    try:
        assert select.select([read_fd], [], [], 20)[0], "second writer did not reach its gate"
        assert os.read(read_fd, 1) == b"R"
        status = record(conf.output_dir, "run-status.yaml")
        assert status["state"] == "running" and len(status["products"]) == 1
        assert status["pending"] == ["publication", "cleanup"]
        request_bytes = (conf.output_dir / "run-request.yaml").read_bytes()
        ordinary_reader(conf.output_dir, status["products"][0], tmp_path / "input.nc",
                        "instructional_scalar", "valid_time", fmt)
        process.send_signal(signal.SIGKILL if kill else signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == (-signal.SIGKILL if kill else 143), stdout + stderr
        final_bytes = (conf.output_dir / "run-status.yaml").read_bytes()
        status = record(conf.output_dir, "run-status.yaml")
        assert status["state"] == ("running" if kill else "interrupted")
        assert len(status["products"]) == 1
        assert status["pending"] == (["publication", "cleanup"] if kill else ["publication"])
        assert (conf.output_dir / ".frameit-run.lock").exists() == kill
        assert bool(list(conf.output_dir.rglob("*.partial"))) == kill
        assert (status["finished_at"] is None) == kill
        assert (conf.output_dir / "run-request.yaml").read_bytes() == request_bytes
        if kill:
            with pytest.raises(FileExistsError, match="locked"):
                execute_simulation(conf, ExecutionOptions.from_config(conf, overwrite=True))
            assert (conf.output_dir / "run-status.yaml").read_bytes() == final_bytes
    finally:
        os.close(read_fd)
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=20)


def test_zarr_replacement_visibility_gap_and_caught_rollback_stay_explicit(
        tmp_path, monkeypatch):
    from frameit.utils import atomic

    conf = two_sources(tmp_path, "zarr", True)
    first = execute_simulation(conf)
    product = first.products[0]
    target = Path(product["path"])
    before = {path.relative_to(target): path.read_bytes()
              for path in target.rglob("*") if path.is_file()}
    original_replace = atomic.os.replace
    observed = []

    def replace(source, destination):
        source, destination = Path(source), Path(destination)
        if source == target:
            result = original_replace(source, destination)
            assert not target.exists() and destination.is_dir()
            assert record(conf.output_dir, "run-status.yaml")["products"] == []
            observed.append("visibility gap")
            return result
        if destination == target and source.name.endswith(".partial"):
            raise OSError("caught Zarr replacement failure")
        return original_replace(source, destination)

    monkeypatch.setattr(atomic.os, "replace", replace)
    with pytest.raises(OSError, match="caught Zarr replacement failure"):
        execute_simulation(conf, ExecutionOptions.from_config(conf, overwrite=True))
    assert observed == ["visibility gap"]
    assert {path.relative_to(target): path.read_bytes()
            for path in target.rglob("*") if path.is_file()} == before
    status = record(conf.output_dir, "run-status.yaml")
    assert status["state"] == "failed" and status["products"] == []
    assert status["pending"] == ["publication"]
    assert not list(conf.output_dir.rglob("*.backup"))
    assert not list(conf.output_dir.rglob("*.partial"))
    assert "visibility gap" in product["encoding"]["publication"]
    ordinary_reader(conf.output_dir, {"path": str(target.relative_to(conf.output_dir))},
                    tmp_path / "input.nc", "instructional_scalar", "valid_time", "zarr")


def test_request_context_preserves_positional_constructor_and_keyword_copy(tmp_path):
    from dataclasses import fields
    from inspect import Parameter, signature

    template = SimulationConfig(**to_runtime(document(), base_dir=tmp_path))
    legacy_fields = tuple(item.name for item in fields(SimulationConfig)
                          if item.name != "request_context")
    args = [getattr(template, name) for name in legacy_fields[:72]]
    args[71] = True
    positional = SimulationConfig(*args)
    assert positional.infer_grid_geometry is True
    assert positional.request_context["request_kind"] == "runtime"

    parameters = signature(SimulationConfig).parameters
    positional_names = tuple(name for name, parameter in parameters.items()
                             if parameter.kind is Parameter.POSITIONAL_OR_KEYWORD)
    assert positional_names == legacy_fields == SimulationConfig.__match_args__
    assert positional_names[68:74] == (
        "schema_version", "yaml_config", "schema_sources",
        "infer_grid_geometry", "grid_geometry", "input_pattern")
    assert parameters["request_context"].kind is Parameter.KEYWORD_ONLY

    context = deepcopy(template.request_context)
    explicit = SimulationConfig(*args, request_context=context)
    assert explicit.infer_grid_geometry is True
    assert explicit.request_context == context
    context["authored_configuration"]["sources"]["weather"]["files"] = "./changed.nc"
    assert explicit.request_context["authored_configuration"]["sources"]["weather"]["files"] == (
        "./input.nc")
    explicit.request_context["overrides"]["output_directory"] = "./other"
    assert context["overrides"] == {}


def _exercise_parent_retention_boundary(tmp_path, monkeypatch, fmt, boundary):
    from collections import Counter

    import frameit.io.netcdf_export as exporter
    from frameit.core.runtime import termination_scope

    conf = two_sources(tmp_path, fmt, False)
    originals = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (tmp_path / "input.nc", tmp_path / "ocean.nc")}
    original_completed, original_export = exporter.as_completed, exporter.export_outputs
    injected, target = False, None
    retained, callbacks = [], []

    def completed(futures):
        for future in original_completed(futures):
            if boundary == "before_retention":
                original_result = future.result

                def result(timeout=None, original=original_result, finished=future):
                    nonlocal injected, target
                    facts = original(timeout=timeout)
                    if not injected:
                        assert finished.done() and finished.exception(timeout=0) is None
                        injected, target = True, facts
                        os.kill(os.getpid(), signal.SIGTERM)
                    return facts

                monkeypatch.setattr(future, "result", result)
            yield future

    def export(runner, **kwargs):
        checkpoint = kwargs["on_published"]

        def published(facts):
            nonlocal injected, target
            callbacks.append(facts["path"])
            assert sum(item["path"] == facts["path"]
                       for item in runner.published_products) == 1
            if boundary == "callback_entry" and not injected:
                injected, target = True, facts
                os.kill(os.getpid(), signal.SIGTERM)
            checkpoint(facts)
            if boundary in {"callback_error", "callback_signal"} and not injected:
                injected, target = True, facts
                if boundary == "callback_error":
                    raise OSError("after-retention callback failure")
                os.kill(os.getpid(), signal.SIGTERM)

        kwargs["on_published"] = published
        try:
            return original_export(runner, **kwargs)
        finally:
            retained.extend(deepcopy(runner.published_products))

    monkeypatch.setattr(exporter, "as_completed", completed)
    monkeypatch.setattr(exporter, "export_outputs", export)
    expected_error = OSError if boundary == "callback_error" else SystemExit
    with pytest.raises(expected_error) as caught, termination_scope():
        execute_simulation(conf)
    if boundary != "callback_error":
        assert caught.value.code == 143
    assert injected and target is not None and Path(target["path"]).exists()
    weather = target["source"] == "weather"
    ordinary_reader(
        conf.output_dir, {"path": str(Path(target["path"]).relative_to(conf.output_dir))},
        tmp_path / ("input.nc" if weather else "ocean.nc"),
        "instructional_scalar" if weather else "sea_scalar",
        "valid_time" if weather else "time_counter", fmt)
    assert [item["path"] for item in retained].count(target["path"]) == 1
    assert len(retained) == 2
    assert Counter(callbacks) == Counter({item["path"]: 1 for item in retained})
    status = record(conf.output_dir, "run-status.yaml")
    provenance = record(conf.output_dir, "run-provenance.yaml")
    assert status["state"] == ("failed" if boundary == "callback_error" else "interrupted")
    assert status["pending"] == ["publication"]
    assert status["error"]["type"] == expected_error.__name__
    assert len(status["products"]) == len(provenance["products"]) == 2
    assert status["products"] == provenance["products"]
    assert {item["path"] for item in status["products"]} == {
        item["path"] for item in status["planned_products"]}
    assert len({item["path"] for item in status["products"]}) == 2
    for product in status["products"]:
        if conf.output_dir / product["path"] == Path(target["path"]):
            continue
        weather = product["source"] == "weather"
        ordinary_reader(
            conf.output_dir, product, tmp_path / ("input.nc" if weather else "ocean.nc"),
            "instructional_scalar" if weather else "sea_scalar",
            "valid_time" if weather else "time_counter", fmt)
    assert not (conf.output_dir / ".frameit-run.lock").exists()
    assert not list(conf.output_dir.rglob("*.partial"))
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == sha
               for path, sha in originals.items())
