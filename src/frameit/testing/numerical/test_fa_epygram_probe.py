"""C0 API evidence uses independently prescribed arrays and geographic checkpoints."""

from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from frameit.testing.numerical.test_fa_cubes import EPYTHON, NATIVE
from frameit.testing.numerical.test_fa_geometry import spherical_lambert


@NATIVE
@pytest.mark.parametrize("projected", [False, True])
def test_selected_surfex_library_reads_and_structural_gaps(tmp_path, projected):
    j, i = np.indices((7, 9))
    truth = (280. + 10*j + i).astype(float)
    truth[1, 1], truth[2, 2] = np.nan, 0.
    path = tmp_path / "surface.fa"
    options = {"path": str(path), "profile": "surfex_history", "hours": 1,
               "extra_metadata": True, "surface_fields": [
                   {"name": "T2M", "mask": "FULL", "values": truth.tolist()},
                   {"name": "SST", "mask": "SEA", "values": truth.tolist()}]}
    if projected:
        options["projection_latitude"] = -20.
    written = subprocess.run([EPYTHON, "-m", "frameit.testing.fa_fixture"],
                             input=json.dumps([options]), capture_output=True,
                             text=True, timeout=30)
    assert written.returncode == 0, written.stdout + written.stderr
    path.chmod(0o444)
    before = path.read_bytes()
    if projected:
        lon, lat = spherical_lambert((i - 4) * 1000., (j - 3) * 1000., 6371229., -20.)
    else:
        lon, lat = 60. + (i - 4) * .01064, -20. + (j - 3) * .01
    # Fresh FA-only process. No FrameIt production reader or same-reader oracle.
    code = """
import json, sys
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from frameit.io.fa_epygram import initialize
path, expected, lon, lat = json.loads(sys.argv[1])
with TemporaryDirectory() as directory:
    epygram = initialize(Path(directory), 6371229.)
    from falfilfa4py import FA
    original = FA.wfacilo
    decoded = []
    def counted(*args):
        decoded.append(args[2] + args[4])
        return original(*args)
    FA.wfacilo = counted
    with epygram.formats.resource(path, openmode='r', fmt='FA') as resource:
        for name in ('SFX.T2M', 'SFX.SST'):
            field = resource.readfield(name, getdata=False)
            assert field.getdata(d4=True) is None
        assert decoded == []
        field = resource.readfield('SFX.T2M')
        np.testing.assert_array_equal(field.getdata(), expected)
        assert decoded == ['SFX.T2M']
        actual_lon, actual_lat = resource.geometry.get_lonlat_grid()
        np.testing.assert_allclose(actual_lon, lon, rtol=0, atol=2.e-5)
        np.testing.assert_allclose(actual_lat, lat, rtol=0, atol=2.e-5)
        assert resource.validity.get().isoformat() == '2026-01-01T01:00:00'
assert not {'eccodes', 'cfgrib', 'ectrans4py'} & sys.modules.keys()
"""
    checked = subprocess.run([EPYTHON, "-c", code, json.dumps([
        str(path), truth.tolist(), lon.tolist(), lat.tolist()])], capture_output=True,
        text=True, timeout=30)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    probe = subprocess.run([
        EPYTHON, "-m", "frameit.testing.fa_epygram_probe", "FA", str(path),
        "--fields", "SFX.T2M", "SFX.SST", "--read-fields", "SFX.T2M",
        "--metadata-fields", "SFX.PROGRAM", "SFX.DTCUR", "SFX._FBUF_DIM1",
        "--earth-radius-m", "6371229"], capture_output=True, text=True, timeout=30)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    report = json.loads(probe.stdout[probe.stdout.index("{\n"):])
    assert report["native_calls"]["wfaitou"] == report["native_calls"]["wfairme"] == 1
    assert report["decoded_fields"] == ["SFX.T2M"]
    assert all(item["metadata_payload_calls"] == 0 for item in report["fields"].values())
    assert report["fields"]["SFX.T2M"]["read"]["valid_zero"] == 1
    assert report["fields"]["SFX.T2M"]["read"]["nonfinite"] == 1
    assert report["metadata"]["SFX.PROGRAM"]["read"]["value"].rstrip() == "AROME"
    assert report["metadata"]["SFX._FBUF_DIM1"]["read"]["value"] == [63, 63]
    # Characterize the actual T0 API gap: this scalar is NOT the full state clock.
    assert report["metadata"]["SFX.DTCUR"]["word_count"] == 4
    assert report["metadata"]["SFX.DTCUR"]["read"]["value"] == 2026
    assert report["source_stat_unchanged"]
    assert path.read_bytes() == before


@NATIVE
def test_grib_library_metadata_selection_preserves_native_pressure_units(tmp_path):
    ec = pytest.importorskip("eccodes")
    path = tmp_path / "atmosphere.grib"
    with path.open("wb") as stream:
        for level in (700, 850):
            handle = ec.codes_grib_new_from_samples("regular_ll_pl_grib2")
            try:
                for key, value in {"Ni": 7, "Nj": 5, "jScansPositively": 1,
                                   "latitudeOfFirstGridPointInDegrees": -20.04,
                                   "latitudeOfLastGridPointInDegrees": -19.96,
                                   "longitudeOfFirstGridPointInDegrees": 59.93616,
                                   "longitudeOfLastGridPointInDegrees": 60.06384,
                                   "iDirectionIncrementInDegrees": .02128,
                                   "jDirectionIncrementInDegrees": .02,
                                   "dataDate": 20260101, "dataTime": 0, "step": 1,
                                   "paramId": 130, "level": level}.items():
                    ec.codes_set(handle, key, value)
                ec.codes_set_values(handle, np.arange(35) + 280.)
                ec.codes_write(handle, stream)
            finally:
                ec.codes_release(handle)
    path.chmod(0o444)
    before = path.read_bytes()
    selector = {"shortName": "t", "typeOfLevel": "isobaricInhPa", "level": 850}
    command = [EPYTHON, "-m", "frameit.testing.fa_epygram_probe", "GRIB", str(path),
               "--max-records", "2", "--selectors", json.dumps([selector])]
    probe = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    report = json.loads(probe.stdout[probe.stdout.index("{\n"):])
    assert report["message_count"] == report["inventory_count"] == 2
    selected, = report["selected"]
    assert selected["metadata"]["level"] == 850
    assert selected["metadata"]["typeOfLevel"] == "isobaricInhPa"
    assert selected["metadata"]["units"] == "K"
    assert selected["metadata_only"]["levels"] == [85000]  # library field is in Pa
    assert selected["metadata_only"]["valid"] == "2026-01-01 01:00:00"
    assert not selected["metadata_only"]["data_present"]
    # Compare the actual current public contract, not another EPyGrAM round trip.
    # No production switch: listfields/select does not replace lazy xarray grouping.
    from frameit.core.preflight import _grib_metadata
    from frameit.io.grib_utils import concat_grib2ds_by_vert_coord
    from frameit.io.loader import DatasetResources

    metadata = _grib_metadata(path)
    levels = next(ds for ds in metadata if "isobaricInhPa" in ds.coords)
    assert levels.isobaricInhPa.values.tolist() == [700., 850.]
    assert levels.isobaricInhPa.attrs["units"] == "hPa"
    assert levels.t.attrs["units"] == selected["metadata"]["units"] == "K"
    assert levels.attrs["_frameit_forecast_reference_times"] == ["2026-01-01T00:00:00.000000000"]
    assert str(levels.valid_time.values[0]) == "2026-01-01T01:00:00.000000000"
    with DatasetResources() as resources:
        groups, _ = concat_grib2ds_by_vert_coord([path], {
            "isobaricInhPa": {"variables": ["t"], "levels": [850]}}, {},
            index_dir=tmp_path / "indexes", resources=resources, filter_requested=True)
        data = groups["isobaricInhPa"]
        assert data.isobaricInhPa.values.tolist() == [850.]
        np.testing.assert_array_equal(data.t.squeeze(), (np.arange(35) + 280.).reshape(5, 7))
        assert data.t.attrs["units"] == "K"
        data.to_netcdf(tmp_path / "selected.nc", engine="netcdf4")
    ordinary = subprocess.run([EPYTHON, "-c", """
import sys, numpy as np, xarray as xr
with xr.open_dataset(sys.argv[1], engine='netcdf4') as ds:
    assert ds.isobaricInhPa.values.tolist() == [850.]
    assert ds.t.attrs['units'] == 'K'
    np.testing.assert_array_equal(ds.t.squeeze(), (np.arange(35)+280.).reshape(5,7))
assert not {'frameit', 'epygram', 'falfilfa4py'} & sys.modules.keys()
""", str(tmp_path / "selected.nc")], capture_output=True, text=True, timeout=30)
    assert ordinary.returncode == 0, ordinary.stdout + ordinary.stderr
    ambiguous = subprocess.run(command[:-1] + [json.dumps([{"shortName": "t"}])],
                               capture_output=True, text=True, timeout=30)
    assert ambiguous.returncode != 0 and "exactly one message" in ambiguous.stderr
    assert path.read_bytes() == before
