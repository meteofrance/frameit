"""Source-checkout examples and launchers; not installed runtime tests."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr
import yaml

from frameit.core.execution import execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_configuration_v2_1 import dataset, document
from frameit.testing.numerical.test_croco_mnh_coupling import coupled_document
from frameit.testing.numerical.test_hpc_execution import cli_attempts as cli_attempts
from frameit.testing.numerical.test_hpc_execution import cli_environment
from frameit.testing.numerical.test_nemo_arome_coupling import preceding_document


ROOT = Path(__file__).resolve().parents[1]
SLURM_EXAMPLES = ROOT / 'example/slurm'


@pytest.mark.parametrize("filename", [
    "conf_example.yml", "conf_pressure_centroid_mnh.yml", "conf_multifield_mnh.yml",
    "arome_fa_native_cubes.yaml", "nemo_arome.yaml", "croco_mesonh.yaml",
    "conf_pressure_centroid.yml", "conf_multifield_arome.yml",
    "coupled_fa.yaml", "coupled_cyclone_polar.yaml", "coupled_arome_fa_polar.yaml",
])
def test_unambiguous_examples_emit_direct_v3_without_changing_quantities(filename):
    path = ROOT / "example/config_file" / filename
    raw = yaml.safe_load(path.read_text())
    conf = SimulationConfig.from_yaml(path)
    assert raw["schema_version"] == conf.schema_version == 3
    assert "input" not in raw and "tracking" not in raw
    assert raw["products"]["model_grid"] is True and raw["products"]["track"] is True
    if filename in {"conf_pressure_centroid_mnh.yml", "conf_multifield_mnh.yml"}:
        source = raw["sources"]["atmosphere"]
        assert source["variables"] == {"2d": ["MSLP", "UM10", "VM10"]}
        assert raw["region"]["width_km"] == {"x": 500, "y": 500}
        assert {tuple(pair[k] for k in ("u", "v", "basis")) for pair in source["wind_pairs"]} == {
            ("UM10", "VM10", "earth"), ("UT_ZM", "VT_ZM", "earth")}
        if filename == "conf_multifield_mnh.yml":
            assert raw["region"]["tracker"]["on_incomplete"] == "keep_prefix"
            assert conf.multifield_vortex["on_track_loss"] == "stop"
    elif filename == "conf_example.yml":
        assert raw["sources"]["atmosphere"]["variables"] == {"2d": ["u10", "v10", "prmsl"]}
        assert raw["region"]["tracker"]["method"] == "pressure_wind"
    elif filename == "conf_pressure_centroid.yml":
        assert raw["sources"]["atmosphere"]["variables"] == {
            "2d": ["u10", "v10", "prmsl"],
            "3d": {"isobaric": {"names": ["u", "v"],
                                    "levels": {"values": [850, 700], "units": "hPa"}}}}
        assert raw["region"]["tracker"]["motion"] == {
            "max_iterations": 50, "solver": "aitken", "relaxation": .25, "tolerance_m": 250}
        assert raw["products"]["polar"]["radius_km"] == 250
        assert raw["products"]["polar"]["azimuth_count"] == 36
    elif filename == "conf_multifield_arome.yml":
        assert raw["sources"]["atmosphere"]["variables"] == {"2d": ["prmsl", "u10", "v10"]}
        assert raw["region"]["tracker"]["seed"] == {
            "latitude": -20., "longitude": 60., "motion_u_m_s": 0., "motion_v_m_s": 0.}
        assert raw["region"]["tracker"]["on_incomplete"] == "keep_prefix"
        assert "polar" not in raw["products"]
    elif filename == "arome_fa_native_cubes.yaml":
        source = raw["sources"]["atmosphere"]
        assert source["variables"] == {
            "3d": ["temperature", "u", "v"], "levels": {"indices": [0, 2]}}
        assert source["native_cubes"]["u"]["records"] == [
            "S001WIND.U.PHYS", "S002WIND.U.PHYS", "S003WIND.U.PHYS"]
        assert not source.get("transforms")
    elif filename == "nemo_arome.yaml":
        assert set(raw["sources"]) == {"atmosphere", "ocean"}
        assert raw["sources"]["ocean"]["variables"] == {
            "3d": ["votemper", "vozocrtx", "vomecrty", "vovecrtz"],
            "levels": {"indices": [0, 1]}}
        assert raw["region"]["sources_coupling_time_association"] == "preceding_hour"
    elif filename == "croco_mesonh.yaml":
        assert raw["sources"]["ocean"]["variables"]["3d"] == ["temp", "salt", "u", "v", "w"]
        assert raw["sources"]["ocean"]["variables"]["levels"] == {"indices": [0, 49]}
        assert raw["sources"]["atmosphere"]["variables"]["levels"] == {"indices": [1, 70]}
        assert raw["sources"]["atmosphere"]["interpretation"] == "mesonh_surfex_sea"
    else:
        assert set(raw["sources"]) == {"atmosphere", "surface"}
        surface = raw["sources"]["surface"]
        assert surface["profile"] == "surfex_history"
        assert surface["fa"]["earth_radius_m"] == 6371229.
        assert all(item["units"] == "K" and item["kind"] == "continuous"
                   and item["temporal_kind"] == "instantaneous"
                   and item["allow_unscaled"] is False
                   for item in surface["field_metadata"].values())
        if filename == "coupled_fa.yaml":
            assert surface["variables"] == {"2d": ["SFX.T2M"]}
            assert raw["sources"]["atmosphere"]["variables"] == {
                "3d": {"heightAboveGround": {
                    "names": ["t2m"], "levels": {"values": [2], "units": "m"}}}}
            assert "polar" not in raw["products"]
        else:
            assert surface["variables"] == {"2d": ["SFX.T2M", "SFX.SST"]}
            assert raw["products"]["polar"]["radial_step_km"] == 4
            assert raw["products"]["polar"]["azimuth_count"] == 72
            assert raw["products"]["polar"]["shared_grid"] is True
            assert raw["products"]["polar"]["missing_data_policy"] == "strict"


def test_factory_and_preset():
    from frameit.tracking.PressureCentroid_Tracker import PressureCentroidTracker
    from frameit.tracking.tracker_core import build_tracker_from_config

    conf = SimulationConfig.from_yaml_with_model_preset(
        ROOT / "example/config_file/conf_pressure_centroid.yml")
    # Schema parsing defers geometry-dependent tracker construction.
    assert conf.infer_grid_geometry and conf.resolution == 0
    conf.resolution = 2500
    with pytest.raises(ValueError, match="support is not resolved"):
        build_tracker_from_config(conf)
    tracker = PressureCentroidTracker.from_config(conf)
    assert isinstance(tracker, PressureCentroidTracker)
    assert tracker.half_search == 40
    assert not conf.requested_variables_tracker
    assert conf.simulation_parameter["request_plan"]["sources"]["atmosphere"]["records"] is None
    conf.atm_model = "MNH"
    assert PressureCentroidTracker.from_config(conf).model == "MNH"


def test_all_shipped_example_yaml_uses_new_schema():
    paths = [p for p in (ROOT / 'example').rglob('*') if p.suffix in {'.yml', '.yaml'}]
    assert paths
    for path in paths:
        assert SimulationConfig.from_yaml(path).schema_version == 3


def test_source_examples_declare_conventions():
    for path in (ROOT / 'example').rglob('*.yml'):
        source = yaml.safe_load(path.read_text())
        conf = SimulationConfig.from_mapping_with_model_preset(source)
        atmosphere = source['sources']['atmosphere']
        assert atmosphere['wind_pairs'], path
        assert conf.wind_reference_frame is None
        selected = set(atmosphere['variables'].get('2d', []))
        selected.update(
            f'{group}.{name}' for group, spec in atmosphere['variables'].get('3d', {}).items()
            for name in spec['names'])
        expected = {pair[component] for pair in atmosphere['wind_pairs']
                    for component in ('u', 'v') if pair[component] in selected}
        assert {field for transform in atmosphere['transforms']
                for field in transform['fields']} == expected
        assert all(transform['sampling'] == (
            'native' if atmosphere['model'] == 'arome' else 'mass')
                   and transform['basis'] == 'earth'
                   for transform in atmosphere['transforms'])


def test_portable_nemo_arome_example_with_preceding_hour_inputs(tmp_path):
    example = ROOT / 'example/config_file/nemo_arome.yaml'
    data = tmp_path / 'data'
    data.mkdir()
    preceding_document(data)
    config = tmp_path / 'nemo_arome.yaml'
    shutil.copyfile(example, config)
    conf = SimulationConfig.from_yaml_with_model_preset(config)
    result = execute_simulation(conf)
    assert result.ok, result
    assert len([p for p in result.products if p['role'] == 'model_grid']) == 2
    ocean = next(p for p in result.products if p['source'] == 'ocean')
    assert set(ocean['fields']) == {'votemper', 'vozocrtx', 'vomecrty', 'vovecrtz'}
    replay = SimulationConfig.from_yaml_with_model_preset(conf.output_dir / 'resolved-config.yaml')
    assert replay.time_alignment == 'preceding_hour'
    assert replay.sources['ocean']['files'] == [
        str(data / f'nemo_{grid}.nc') for grid in ('t', 'u', 'v', 'w')]


@pytest.mark.parametrize('representation', ['native', 'mass_earth'])
def test_croco_mnh_portable_example_runs_both_current_representations(tmp_path, representation):
    example = ROOT / 'example/config_file/croco_mesonh.yaml'
    fixture = coupled_document(tmp_path)
    raw = yaml.safe_load(example.read_text())
    for name in ('ocean', 'atmosphere'):
        entry = raw['sources'][name]
        entry['files'] = fixture['sources'][name]['files']
    for path in raw['sources']['atmosphere']['files']:
        with xr.open_dataset(path) as header:
            ds = header.load()
        ds['PRES'] = (('time', 'level', 'nj', 'ni'), np.full((1, 3, 7, 7), 999.), {'units': 'hPa'})
        ds = ds.assign_coords(level=[0., 1., 2.])
        ds['MSLP'] = (('nj', 'ni'), np.full((7, 7), 1000.), {'units': 'hPa'})
        for field, units in (('LE_SEA', 'W/m2'), ('FMU_SEA', 'kg/ms2'), ('FMV_SEA', 'kg/ms2')):
            ds[field] = (('nj', 'ni'), np.full((7, 7), 2.), {'comment': f'X_Y_{field} ({units})'})
        ds.to_netcdf(path, mode='w')
    path = raw['sources']['ocean']['files'][0]
    with xr.open_dataset(path) as header:
        ds = header.load()
    ds['w'] = xr.zeros_like(ds.temp).assign_attrs(units='meter second-1', standard_name='upward_sea_water_velocity')
    ds.to_netcdf(path, mode='w')
    raw['sources']['ocean']['variables']['levels'] = {'indices': [0, 2]}
    raw['sources']['atmosphere']['variables']['levels'] = {'indices': [1, 2]}
    raw['region']['center'] = {'latitude': -20., 'longitude': 60.}
    raw['region']['width_km'] = {'x': 2., 'y': 2.}
    raw['output']['directory'] = str(tmp_path/'example-output')
    if representation == 'native':
        raw['sources']['ocean'].pop('transforms')
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    ocean = next(p['path'] for p in result.products if p['role'] == 'model_grid'
                 and p['source'] == 'ocean')
    with xr.open_dataset(ocean) as out:
        values = out.u.values
        np.testing.assert_allclose(values[np.isfinite(values)], 2. if representation == 'native' else -4., atol=1e-12)
        assert np.isfinite(values).any()
        if representation == 'mass_earth':
            assert np.isnan(values).any()  # The fixture has a dry native bracket.
        np.testing.assert_allclose(out.w, 0.)
        assert 's_rho' in out.w.dims and 's_w' not in out.w.dims


def test_independent_checker_accepts_reference_and_rejects_wrong_time_count(cli_attempts, tmp_path):
    tmp_path = cli_attempts
    checker = SLURM_EXAMPLES / 'check_run.py'
    checked = subprocess.run([
        sys.executable, str(checker), str(tmp_path / 'spawn'), '--expected-times', '2',
        '--reference', str(tmp_path / 'sync'), '--report', str(tmp_path / 'check.json'),
    ], capture_output=True, text=True, timeout=30, env=cli_environment())
    assert checked.returncode == 0, checked.stdout + checked.stderr
    wrong_count = subprocess.run([
        sys.executable, str(checker), str(tmp_path / 'spawn'), '--expected-times', '3',
    ], capture_output=True, text=True, env=cli_environment(), timeout=30)
    assert wrong_count.returncode == 1 and '"ok": false' in wrong_count.stdout
    broken = tmp_path / 'broken-centres'
    shutil.copytree(cli_attempts / 'spawn', broken)
    status_path = broken / 'run-status.yaml'
    status = yaml.safe_load(status_path.read_text())
    product = next(item for item in status['products'] if item['role'] == 'model_grid')
    path = broken / product['path']
    with xr.open_dataset(path) as source:
        changed = source.load()
    changed['center_longitude'] = changed.center_longitude + 1
    changed.to_netcdf(path)
    product['size_bytes'] = path.stat().st_size
    status_path.write_text(yaml.safe_dump(status))
    wrong_centres = subprocess.run(
        [sys.executable, str(checker), str(broken)], capture_output=True, text=True,
        env=cli_environment(), timeout=30)
    assert wrong_centres.returncode == 1 and 'Broken track linkage' in wrong_centres.stdout


@pytest.mark.parametrize("array", [False, True])
def test_slurm_launcher_isolates_retries_and_propagates_failure(tmp_path, array):
    """Exercise the shell boundary locally; the srun shim is not a scheduler test."""
    inputs = tmp_path / 'input with spaces'
    inputs.mkdir()
    dataset(inputs)
    config = inputs / 'case.yaml'
    raw = document(inputs)
    raw['sources']['atmosphere']['files'] = ['native.nc']
    config.write_text(yaml.safe_dump(raw))
    parent = tmp_path / 'attempts with spaces'
    parent.mkdir()
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    srun = bin_dir / 'srun'
    srun.write_text('''#!/bin/sh
test "$MPLBACKEND" = caller-backend || exit 97
while [ "$#" -gt 0 ]; do
    case "$1" in --nodes=*|--ntasks=*) shift ;; *) break ;; esac
done
exec "$@"
''')
    srun.chmod(0o755)
    activation = tmp_path / 'activate.sh'
    activation.write_text(f'export PATH="{Path(sys.executable).parent}:$PATH"\n')
    env = {
        **cli_environment(), 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
        'SLURM_NTASKS': '1', 'FRAMEIT_ENV_SCRIPT': str(activation),
        'MPLBACKEND': 'caller-backend',
    }
    launcher = SLURM_EXAMPLES / 'frameit.sbatch'
    if array:
        listing = tmp_path / "complete cases.txt"
        listing.write_text(str(config.resolve()) + "\n")
        config = listing
        env["SLURM_ARRAY_TASK_ID"] = "0"
        launcher = tmp_path / "spool/slurm_script"
        launcher.parent.mkdir()
        shutil.copyfile(SLURM_EXAMPLES / "array.sbatch", launcher)
    for _ in range(2):
        run = subprocess.run(
            ['bash', str(launcher), str(config), str(parent),
             *([str(SLURM_EXAMPLES / 'frameit.sbatch')] if array else [])], cwd=tmp_path,
            env=env, capture_output=True, text=True, timeout=45,
        )
        assert run.returncode == 0, run.stdout + run.stderr
    attempts = list(parent.iterdir())
    assert len(attempts) == 2
    for attempt in attempts:
        assert (attempt / 'work').is_dir()
        status = yaml.safe_load((attempt / 'run' / 'run-status.yaml').read_text())
        assert status['state'] == 'completed'
        assert status['effective_execution_options']['overwrite'] is False
        assert status['effective_execution_options']['require_complete_tracking'] is True
    (inputs / 'native.nc').unlink()
    failed = subprocess.run(
        ['bash', str(launcher), str(config), str(parent),
         *([str(SLURM_EXAMPLES / 'frameit.sbatch')] if array else [])], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert failed.returncode == 1


@pytest.mark.parametrize("polar", [False, True])
@pytest.mark.parametrize("track", [False, True])
def test_independent_checker_uses_product_clocks_and_optional_track(tmp_path, polar, track):
    from frameit.testing.documentation_example import create_tutorial_inputs

    if polar:
        pytest.importorskip("xesmf")
    create_tutorial_inputs(tmp_path / "data", translating=True)
    raw = yaml.safe_load((ROOT / "example/tutorials/analytic-moving.yaml").read_text())
    if not polar:
        raw["products"].pop("polar")
    if not track:
        raw["products"].pop("track")
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(raw))
    execute_simulation(SimulationConfig.from_yaml(path))
    checker = SLURM_EXAMPLES / "check_run.py"
    command = [sys.executable, str(checker), str(tmp_path / "results/analytic-moving")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    import json

    report = json.loads(result.stdout)
    assert report["time_counts"]["atmosphere"] == report["time_counts"]["ocean"] == 2
    product = tmp_path / "results/analytic-moving/products/analytic-moving.atmosphere.model_grid.nc"
    with xr.open_dataset(product) as original:
        altered = original.load().assign_coords(time=original.time + np.timedelta64(1, "s"))
    altered.to_netcdf(product)
    status_path = tmp_path / "results/analytic-moving/run-status.yaml"
    status = yaml.safe_load(status_path.read_text())
    descriptor = next(p for p in status["products"]
                      if p["role"] == "model_grid" and p["source"] == "atmosphere")
    descriptor["size_bytes"] = product.stat().st_size
    status_path.write_text(yaml.safe_dump(status))
    rejected = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert rejected.returncode == 1 and "clock" in rejected.stdout.lower()


def test_repeated_case_loop_keeps_success_failure_and_retry_separate(tmp_path):
    inputs = tmp_path / "inputs with spaces"
    inputs.mkdir()
    dataset(inputs)
    raw = document(inputs, resources={"cpus": 1, "synchronous_export": True})
    good, bad = inputs / "good.yaml", inputs / "retry.yaml"
    good.write_text(yaml.safe_dump(raw))
    raw["sources"]["atmosphere"]["variables"] = {"2d": ["absent"]}
    bad.write_text(yaml.safe_dump(raw))
    parent = tmp_path / "attempts with spaces"
    parent.mkdir()
    command = ["bash", str(ROOT / "example/repeat_cases.sh"), str(parent)]
    first = subprocess.run([*command, str(good), str(inputs / "missing.yaml"), str(bad)],
                           capture_output=True, text=True,
                           env=cli_environment(), timeout=60)
    assert first.returncode == 1, first.stdout + first.stderr
    attempts = list(parent.iterdir())
    assert len(attempts) == 3
    assert sorted((p / "exit-code").read_text().strip() for p in attempts) == ["0", "1", "1"]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
              for root in attempts for p in root.rglob("*") if p.is_file()}
    bad.write_text(good.read_text())
    retry = subprocess.run([*command, str(bad)], capture_output=True, text=True,
                           env=cli_environment(), timeout=45)
    assert retry.returncode == 0, retry.stdout + retry.stderr
    assert len(list(parent.iterdir())) == 4
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before


def test_checker_preserves_non_gregorian_sample_and_centre_clocks(tmp_path):
    import cftime
    from frameit.testing.numerical.test_v3_regions import scalar_scene

    path = tmp_path / "weather.nc"
    declaration = scalar_scene(path, hours=(0, 1))
    with xr.open_dataset(path) as original:
        value = original.load().assign_coords(time=[
            cftime.Datetime360Day(2000, 2, 29), cftime.Datetime360Day(2000, 2, 30)])
    value.to_netcdf(path, mode="w")
    raw = {"schema_version": 3, "sources": {"atmosphere": declaration},
           "region": {"center": {"latitude": -20., "longitude": 60.},
                      "width_km": {"x": 2., "y": 2.}},
           "products": {"model_grid": True, "track": True},
           "output": {"directory": str(tmp_path / "out")},
           "resources": {"cpus": 1, "synchronous_export": True}}
    execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    checked = subprocess.run([sys.executable, str(SLURM_EXAMPLES / "check_run.py"),
                              str(tmp_path / "out")], capture_output=True, text=True, timeout=30)
    assert checked.returncode == 0, checked.stdout + checked.stderr


@pytest.mark.parametrize("interval", [False, True])
def test_checker_rejects_track_units_and_recorded_interval_corruption(tmp_path, interval):
    if interval:
        data = tmp_path / "data"
        data.mkdir()
        preceding_document(data)
        raw = yaml.safe_load((ROOT / "example/config_file/nemo_arome.yaml").read_text())
    else:
        from frameit.testing.documentation_example import create_tutorial_inputs

        create_tutorial_inputs(tmp_path / "data", translating=True)
        raw = yaml.safe_load((ROOT / "example/tutorials/analytic-moving.yaml").read_text())
    raw["output"]["directory"] = str(tmp_path / "out")
    raw["resources"] = {"cpus": 1, "synchronous_export": True}
    config = tmp_path / "case.yaml"
    config.write_text(yaml.safe_dump(raw))
    execute_simulation(SimulationConfig.from_yaml(config))
    command = [sys.executable, str(SLURM_EXAMPLES / "check_run.py"), str(tmp_path / "out")]
    valid = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert valid.returncode == 0, valid.stdout + valid.stderr
    status_path = tmp_path / "out/run-status.yaml"
    status = yaml.safe_load(status_path.read_text())
    descriptor = next(p for p in status["products"] if (
        p["source"] == "ocean" if interval else p["role"] == "track"))
    path = tmp_path / "out" / descriptor["path"]
    with xr.open_dataset(path) as original:
        changed = original.load()
    if interval:
        for name in ("time_counter_bounds", "time_centered_bounds"):
            changed[name] = changed[name] + np.timedelta64(2, "h")
    else:
        changed.latitude.attrs["units"] = "radians"
    changed.to_netcdf(path)
    descriptor["size_bytes"] = path.stat().st_size
    status_path.write_text(yaml.safe_dump(status))
    invalid = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert invalid.returncode == 1, invalid.stdout
    assert ("interval" if interval else "contract") in invalid.stdout.lower()


def test_repeated_wrapper_forwards_termination_and_records_it(tmp_path):
    import selectors
    import signal

    config = tmp_path / "case.yaml"
    config.write_text("schema_version: 3\n")
    parent = tmp_path / "attempts"
    parent.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ready, stopped = tmp_path / "ready", tmp_path / "stopped"
    shim = bin_dir / "python"
    shim.write_text('''#!/bin/sh
if [ "$1" = "-m" ]; then
    exec "$REAL_PYTHON" -c '
import os, signal
from pathlib import Path
def stop(*_):
    Path(os.environ["STOPPED"]).write_text("cleaned")
    raise SystemExit(143)
signal.signal(signal.SIGTERM, stop)
Path(os.environ["READY"]).write_text(str(os.getpid()))
print("ready", flush=True)
signal.pause()
'
fi
exec "$REAL_PYTHON" "$@"
''')
    shim.chmod(0o755)
    env = {**cli_environment(), "REAL_PYTHON": sys.executable, "READY": str(ready),
           "STOPPED": str(stopped), "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
    child = None
    process = subprocess.Popen(
        ["bash", str(ROOT / "example/repeat_cases.sh"), str(parent), str(config), str(config)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=10), "Case did not start"
        assert process.stdout.readline() == "ready\n"
        child = int(ready.read_text())
        process.send_signal(signal.SIGTERM)
        _, stderr = process.communicate(timeout=10)
        assert process.returncode == 143, stderr
        assert stopped.read_text() == "cleaned"
        with pytest.raises(ProcessLookupError):
            os.kill(child, 0)
        attempts = list(parent.iterdir())
        assert len(attempts) == 1
        assert (attempts[0] / "exit-code").read_text() == "143\n"
    finally:
        if child is not None:
            try:
                os.kill(child, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=10)


def test_between_case_termination_preserves_completed_receipt(tmp_path):
    import selectors
    import signal

    parent = tmp_path / "attempts"
    parent.mkdir()
    first, second = tmp_path / "first.yaml", tmp_path / "second.yaml"
    first.write_text("schema_version: 3\n")
    second.write_text(first.read_text())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "python"
    shim.write_text('''#!/bin/sh
if [ "$1" = "-m" ]; then exit 0; fi
if [ "$3" = "$SECOND" ]; then
    exec "$REAL_PYTHON" -c 'import os, sys; os.write(int(os.environ["READY_FD"]), b"ready"); sys.stdin.readline()'
fi
exec "$REAL_PYTHON" "$@"
''')
    shim.chmod(0o755)
    ready, notify = os.pipe()
    env = {**cli_environment(), "REAL_PYTHON": sys.executable, "SECOND": str(second),
           "READY_FD": str(notify), "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
    process = subprocess.Popen(
        ["bash", str(ROOT / "example/repeat_cases.sh"), str(parent), str(first), str(second)],
        env=env, pass_fds=(notify,), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    os.close(notify)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(ready, selectors.EVENT_READ)
            assert selector.select(timeout=10), "Second case resolution did not start"
        assert os.read(ready, 5) == b"ready"
        receipt, = parent.glob("*/exit-code")
        before = receipt.read_bytes(), receipt.stat().st_mtime_ns
        assert before[0] == b"0\n"
        process.send_signal(signal.SIGTERM)
        _, stderr = process.communicate(input="\n", timeout=10)
        assert process.returncode == 143, stderr
        assert (receipt.read_bytes(), receipt.stat().st_mtime_ns) == before
        assert len(list(parent.iterdir())) == 1
    finally:
        os.close(ready)
        if process.poll() is None:
            process.terminate()
            process.communicate(input="\n", timeout=10)
