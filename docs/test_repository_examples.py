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


def test_factory_and_preset():
    from frameit.tracking.PressureCentroid_Tracker import PressureCentroidTracker
    from frameit.tracking.tracker_core import build_tracker_from_config

    conf = SimulationConfig.from_yaml_with_model_preset(
        ROOT / "example/config_file/conf_pressure_centroid.yml")
    # Schema parsing defers geometry-dependent tracker construction.
    assert conf.infer_grid_geometry and conf.resolution == 0
    conf.resolution = 2500
    tracker = build_tracker_from_config(conf)
    assert isinstance(tracker, PressureCentroidTracker)
    assert tracker.half_search == 40
    assert conf.requested_variables_tracker["pressure_centroid"]["isobaricInhPa"][
        "level_selection"] == "all"
    conf.atm_model = "MNH"
    assert build_tracker_from_config(conf).model == "MNH"


def test_all_shipped_example_yaml_uses_new_schema():
    paths = [p for p in (ROOT / 'example').rglob('*') if p.suffix in {'.yml', '.yaml'}]
    assert paths
    for path in paths:
        assert SimulationConfig.from_yaml(path).schema_version == '2.1'


def test_source_examples_declare_conventions():
    for path in (ROOT / 'example').rglob('*.yml'):
        source = yaml.safe_load(path.read_text())
        conf = SimulationConfig.from_mapping_with_model_preset(source)
        assert conf.wind_pairs, path
        assert conf.wind_reference_frame is None
        assert conf.cartesian_horizontal_winds == 'mass_earth'


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
    assert len([p for p in result.products if p['role'] == 'cart']) == 5
    replay = SimulationConfig.from_yaml_with_model_preset(conf.output_dir / 'resolved-config.yaml')
    assert replay.time_alignment == 'preceding_hour'
    assert replay.input_sources['nemo_u']['input']['files'] == [str(data / 'nemo_u.nc')]


@pytest.mark.parametrize('representation', ['native', 'mass_earth'])
def test_croco_mnh_portable_example_runs_both_current_representations(tmp_path, representation):
    example = ROOT / 'example/config_file/croco_mesonh.yaml'
    fixture = coupled_document(tmp_path)
    raw = yaml.safe_load(example.read_text())
    for name in ('ocean', 'atmosphere'):
        entry = raw['input']['sources'][name]['input']
        entry.pop('directory')
        entry.pop('pattern')
        entry['files'] = fixture['input']['sources'][name]['input']['files']
    for path in raw['input']['sources']['atmosphere']['input']['files']:
        with xr.open_dataset(path) as header:
            ds = header.load()
        ds['PRES'] = (('time', 'level', 'nj', 'ni'), np.full((1, 3, 7, 7), 999.), {'units': 'hPa'})
        ds = ds.assign_coords(level=[0., 1., 2.])
        ds['MSLP'] = (('nj', 'ni'), np.full((7, 7), 1000.), {'units': 'hPa'})
        for field, units in (('LE_SEA', 'W/m2'), ('FMU_SEA', 'kg/ms2'), ('FMV_SEA', 'kg/ms2')):
            ds[field] = (('nj', 'ni'), np.full((7, 7), 2.), {'comment': f'X_Y_{field} ({units})'})
        ds.to_netcdf(path, mode='w')
    path = raw['input']['sources']['ocean']['input']['files'][0]
    with xr.open_dataset(path) as header:
        ds = header.load()
    ds['w'] = xr.zeros_like(ds.temp).assign_attrs(units='meter second-1', standard_name='upward_sea_water_velocity')
    ds.to_netcdf(path, mode='w')
    raw['input']['sources']['ocean']['variables']['s_rho']['levels'] = {'indices': [0, 2]}
    raw['input']['sources']['atmosphere']['variables']['level']['levels'] = {'indices': [1, 2]}
    raw['tracking']['fixed_box']['center'] = {'latitude': -20., 'longitude': 60.}
    raw['domain']['width_km'] = {'x': 2., 'y': 2.}
    raw['output']['directory'] = str(tmp_path/'example-output')
    raw['output']['cartesian']['horizontal_vectors'] = 'earth_centered' if representation == 'mass_earth' else representation
    result = execute_simulation(SimulationConfig.from_mapping_with_model_preset(raw))
    assert result.ok, result
    ocean = next(p['path'] for p in result.products if p['role'] == 'cart'
                 and p.get('source_group') == 's_rho')
    with xr.open_dataset(ocean) as out:
        values = out.u.values
        np.testing.assert_allclose(values[np.isfinite(values)], 2. if representation == 'native' else -4., atol=1e-12)
        assert np.isfinite(values).any()
        if representation == 'mass_earth':
            assert np.isnan(values).any()  # The fixture has a dry native bracket.
        np.testing.assert_allclose(out.w, 0.)
        assert 's_rho' in out.w.dims and 's_w' not in out.w.dims


def test_independent_checker_accepts_reference_and_rejects_wrong_time_count(cli_attempts):
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


def test_slurm_launcher_isolates_retries_and_propagates_failure(tmp_path):
    """Exercise the shell boundary locally; the srun shim is not a scheduler test."""
    inputs = tmp_path / 'input with spaces'
    inputs.mkdir()
    dataset(inputs)
    config = inputs / 'case.yaml'
    config.write_text(yaml.safe_dump(document(inputs, input={'files': ['native.nc']})))
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
    for _ in range(2):
        run = subprocess.run(
            ['bash', str(launcher), str(config), str(parent)], cwd=tmp_path,
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
        ['bash', str(launcher), str(config), str(parent)], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert failed.returncode == 1
