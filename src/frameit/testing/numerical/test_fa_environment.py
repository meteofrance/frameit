"""One installed stack, isolated FA processes and normal native shutdown."""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

FULL_STACK = all(importlib.util.find_spec(name) is not None for name in
                 ("epygram", "falfilfa4py", "eccodes", "cfgrib", "xesmf", "esmpy"))

UNIFIED_CHECK = """
import json, resource, subprocess, sys
from pathlib import Path
import yaml
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
from frameit.core.execution import execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_fa_pipeline import primary_pair_document, PRIMARY_NATIVE_CHECK
root, synchronous = Path(sys.argv[1]), sys.argv[2] == 'True'
raw = primary_pair_document(root, synchronous=synchronous)
raw['input']['sources']['surfex']['input']['fa'].pop('python_executable')
raw['polar']['enabled'] = True
originals = {Path(path): Path(path).read_bytes() for source in raw['input']['sources'].values()
             for path in source['input']['files']}
original_run, interpreters = subprocess.run, []
def observed(argv, *args, **kwargs):
    if argv[1:3] == ['-m', 'frameit.io.fa_worker']:
        interpreters.append(argv[0])
    return original_run(argv, *args, **kwargs)
subprocess.run = observed
conf = SimulationConfig.from_mapping_with_model_preset(raw)
assert conf.input_sources['surfex']['input']['fa']['python_executable'] is None
result = execute_simulation(conf)
assert result.ok and len(result.products) == 7
assert interpreters and set(interpreters) == {sys.executable}, interpreters
status = yaml.safe_load((conf.output_dir / 'run-status.yaml').read_text())
provenance = yaml.safe_load((conf.output_dir / 'run-provenance.yaml').read_text())
assert status['state'] == 'completed'
assert (provenance['common_polar_target']['verification'] ==
        'exact_time_radius_azimuth_longitude_latitude')
decoder = provenance['sources']['surfex']['fa_decoder']
assert decoder['backend_versions']['FA_backend'] == 'epygram'
assert decoder['backend_versions']['FA_python'] == sys.version.split()[0]
assert set(decoder['payload_reads']) == {'surface-1.fa', 'surface-2.fa'}
replay = SimulationConfig.from_yaml(conf.output_dir / 'resolved-config.yaml')
assert replay.input_sources['surfex']['input']['fa']['python_executable'] is None
paths = {p['group']: p['path'] for p in result.products if p['role'] == 'cart'}
paths['track'] = str(conf.output_dir / 'products/primary-pair.track.nc')
checked = original_run([sys.executable, '-c', PRIMARY_NATIVE_CHECK, json.dumps(paths)],
                       capture_output=True, text=True, timeout=30)
assert checked.returncode == 0, checked.stdout + checked.stderr
assert all(path.read_bytes() == before for path, before in originals.items())
assert not list(conf.output_dir.rglob('*.partial'))
assert not {'epygram', 'falfilfa4py', 'ectrans4py'} & sys.modules.keys()
print('Unified primary pair complete; normal process shutdown must follow', flush=True)
"""


@pytest.mark.skipif(not FULL_STACK, reason="optional unified FA/GRIB/polar stack not installed")
@pytest.mark.parametrize("synchronous", [True, False])
def test_default_interpreter_coupled_exports_and_shutdown(tmp_path, synchronous):
    # The outer process observes native teardown too, beyond the final Python assertion.
    completed = subprocess.run([sys.executable, "-X", "faulthandler", "-c", UNIFIED_CHECK,
                                str(tmp_path), str(synchronous)],
                               capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr
