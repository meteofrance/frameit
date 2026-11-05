"""Fresh-process checks: native import order and interpreter shutdown matter."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_discovering_grib_loader_does_not_initialize_optional_native_decoder():
    run = subprocess.run([sys.executable, "-c", """
import resource, sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
import frameit.io.grib_utils
assert 'cfgrib' not in sys.modules and 'eccodes' not in sys.modules
print('loader discovery completed', flush=True)
"""], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "loader discovery completed" in run.stdout


@pytest.mark.skipif(importlib.util.find_spec("cfgrib") is None, reason="Optional GRIB backend")
def test_direct_grib_loading_and_native_shutdown_in_fresh_interpreter(tmp_path):
    source = Path(__file__).parents[1] / "ci_dataset/AROME/BATSIRAI"
    run = subprocess.run([sys.executable, "-c", """
import resource, sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
from frameit.io.grib_utils import concat_grib2ds_by_vert_coord
from frameit.io.loader import DatasetResources
with DatasetResources() as owned:
    user, _ = concat_grib2ds_by_vert_coord(
        sorted(Path(sys.argv[1]).glob('*.grib'))[:1],
        {'isobaricInhPa': {'variables': ['u', 'v'], 'level_selection': 'indices',
                           'level_indices': [0]}}, {}, method='fixed_box',
        index_dir=sys.argv[2], resources=owned, filter_requested=True)
    data = user['isobaricInhPa'].load()
    assert data.u.shape == data.v.shape == (1, 1, 81, 81)
    assert data.u.attrs['units'] == 'm s**-1'
    assert data.u.notnull().all() and data.v.notnull().all()
print('native cleanup completed', flush=True)
""", str(source), str(tmp_path / "index")], capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "native cleanup completed" in run.stdout


@pytest.mark.skipif(importlib.util.find_spec("cfgrib") is None, reason="Optional GRIB backend")
def test_matrix_fixture_planning_and_native_shutdown_in_fresh_interpreter(tmp_path):
    output = tmp_path / "plan"
    run = subprocess.run([sys.executable, "-c", """
import resource, sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
from frameit.cli import main
main(['run-matrix-test', '--ci', '--plan-only', '--case',
      'arome_batsirai_fixed_cart_only', '--output', sys.argv[1]])
""", str(output)], capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads((output / "run.json").read_text())
    assert report["exit_code"] == 0
    assert [case["status"] for case in report["results"]] == ["PLANNED"]
    assert len(json.loads((output / "plan.json").read_text())["fixture"]["files"]) == 5
