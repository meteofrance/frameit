"""Selected native NetCDF reads: payload bounds, support roles and admission."""

import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from frameit.core.preflight import bind_source, inventory_source
from frameit.core.settings_class import SimulationConfig
from frameit.io.loader import DatasetResources
from frameit.io.netcdf_utils import concat_nc2ds_by_vert_coord
from frameit.processing.requests import bind_requests
from frameit.testing.numerical.test_croco_netcdf import croco_scene
from frameit.testing.numerical.test_croco_vectors import vector_scene
from frameit.testing.numerical.test_nemo_netcdf import nemo_scene
from frameit.testing.numerical.test_request_selection import binding_scene
from frameit.testing.numerical.test_wind_collocation import native


def _binding(tmp_path, scenes, model, variables, *, time=None, engine="h5netcdf"):
    paths = []
    for index, scene in enumerate(scenes):
        path = tmp_path / f"source-{index}.nc"
        scene.to_netcdf(path, engine="h5netcdf")
        paths.append(path)
    declaration = {
        "model": model, "files": list(map(str, paths)), "variables": variables,
        "reader": {"engine": engine},
    }
    if time is not None:
        declaration["time"] = time
    conf = SimulationConfig.from_mapping_with_model_preset({
        "schema_version": 3, "sources": {"source": declaration},
        "output": {"directory": str(tmp_path / "out")},
    })
    inventory_source(conf, "source")
    binding = bind_source(conf, "source")
    assert binding["status"] == "bound", binding["deferred_checks"]
    source = conf.simulation_parameter["request_plan"]["sources"]["source"]
    return paths, binding, source


def _load(paths, binding, source, *, engine="h5netcdf", resources=None):
    native_dimensions = {dim for record in binding["records"]
                         for dim in source["fields"][record["field_id"]]["dimensions"]}
    return concat_nc2ds_by_vert_coord(
        paths, {}, {}, strict=True, selected_records=binding, source_plan=source,
        engine=engine, chunks={dim: 100 for dim in (
            "time", "time_counter", "valid_time", "level", "deptht", "s_rho")
            if dim in native_dimensions},
        resources=resources,
    )


def _payload_reads(monkeypatch, scenes, names):
    """Trace the real backend request after xarray's indexing decomposition."""
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper
    from xarray.backends.netCDF4_ import NetCDF4ArrayWrapper

    dimensions = {name: scene[name].dims for scene in scenes for name in names if name in scene}
    reads = []
    for wrapper in (H5NetCDFArrayWrapper, NetCDF4ArrayWrapper):
        original = wrapper._getitem

        def tracked(array, key, original=original):
            name = array.variable_name
            if name in names:
                positions = {
                    dim: np.atleast_1d(np.arange(size)[index]).tolist()
                    for dim, size, index in zip(dimensions[name], array.shape, key, strict=True)
                }
                reads.append((name, positions))
            return original(array, key)

        monkeypatch.setattr(wrapper, "_getitem", tracked)
    return reads


def test_selected_mesonh_dtcur_is_retained_along_assembled_time(tmp_path):
    times = np.array(["2024-12-10T01", "2024-12-10T02"], dtype="datetime64[ns]")
    scenes = [
        xr.Dataset({"SST": (("time", "nj", "ni"), np.full((1, 2, 2), value), {"units": "K"}),
                    "DTCUR": ((), time, {"standard_name": "time"})},
                   coords={"time": [time], "nj": [0, 1], "ni": [0, 1]})
        for time, value in zip(times, (280., 281.), strict=True)]
    paths, binding, source = _binding(tmp_path, scenes, "mesonh", {"2d": ["SST"]})
    with DatasetResources() as resources:
        products, _ = _load(paths, binding, source, resources=resources)
        product, = products.values()
        assert product.DTCUR.dims == ("time",)
        np.testing.assert_array_equal(product.DTCUR, times)
        assert product.DTCUR.attrs["standard_name"] == "time"
        np.testing.assert_array_equal(product.SST[:, 0, 0], [280., 281.])


@pytest.mark.parametrize("case", ["scalar_time", "partial_alias"])
def test_selected_mesonh_dtcur_respects_admitted_sample_axis(tmp_path, case):
    times = np.array(["2024-12-10T01", "2024-12-10T02"], dtype="datetime64[ns]")
    scenes = [
        xr.Dataset({"SST": (("time", "nj", "ni"), np.full((1, 2, 2), value), {"units": "K"}),
                    "DTCUR": ((), stamp, {"standard_name": "time"})},
                   coords={"time": [stamp], "nj": [0, 1], "ni": [0, 1]})
        for stamp, value in zip(times, (280., 281.), strict=True)]
    if case == "scalar_time":
        scenes = [scenes[0].isel(time=0)]
    else:
        scenes[1] = scenes[1].drop_vars("DTCUR")
    paths, binding, source = _binding(tmp_path, scenes, "mesonh", {"2d": ["SST"]})
    with DatasetResources() as resources:
        products, _ = _load(paths, binding, source, resources=resources)
        product, = products.values()
        if case == "scalar_time":
            assert product.DTCUR.dims == ()
            assert product.DTCUR.values[()] == times[0]
            assert np.all(product.SST.values == 280.)
        else:
            assert "DTCUR" not in product
            assert "DTCUR" in product.attrs["frameit_omitted_time_alias"]
            np.testing.assert_array_equal(product.time, times)
            np.testing.assert_array_equal(product.SST[:, 0, 0], [280., 281.])


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
def test_internal_vertical_stencils_preserve_native_indices_and_product_reads(
        tmp_path, monkeypatch, engine):
    dims = ("time", "isobaric", "y", "x")
    values = np.arange(72., dtype=float).reshape(3, 4, 2, 3)
    scene = xr.Dataset({name: (dims, values + offset, {
        "units": "m2 s-2" if name == "z" else "m s-1"})
        for name, offset in (("u", 0), ("v", 100), ("z", 200))}, coords={
        "time": np.array(["2026-01-01T00", "2026-01-01T01", "2026-01-01T02"],
                         dtype="datetime64[ns]"),
        "isobaric": ("isobaric", [850., 700., 500., 300.],
                          {"axis": "Z", "units": "hPa"}),
        "latitude": ("y", [-20., -19.], {"units": "degrees_north"}),
        "longitude": ("x", [60., 61., 62.], {"units": "degrees_east"}),
    })
    paths, _, source = _binding(
        tmp_path, [scene], "arome", {"3d": ["z"], "levels": {"indices": [2]}},
        time={"stride": 2}, engine=engine)
    binding = bind_requests(source, source["requests"], required_inputs={
        name: {"values": [850, 700] if name == "z" else [850, 700, 500], "units": "hPa"}
        for name in ("u", "v", "z")})
    assert binding["status"] == "bound"
    reads = _payload_reads(monkeypatch, [scene], {"u", "v", "z"})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, engine=engine, resources=resources)
        assert not reads
        out = next(iter(internal["internal"].values()))
        np.testing.assert_array_equal(out.isobaric, [850., 700., 500.])
        np.testing.assert_array_equal(out.isobaric_source_native_index, [0, 1, 2])
        assert out.isobaric.attrs == scene.isobaric.attrs
        out.load(scheduler="synchronous")
        for name in ("u", "v"):
            np.testing.assert_array_equal(
                out[name], scene[name].isel(time=[0, 2], isobaric=[0, 1, 2]))
        np.testing.assert_array_equal(out.z.sel(isobaric=[850, 700]),
                                      scene.z.isel(time=[0, 2], isobaric=[0, 1]))
        assert np.isnan(out.z.sel(isobaric=500)).all()
        assert {name for name, _ in reads} == {"u", "v", "z"}
        for name, positions in reads:
            assert set(positions["time"]) <= {0, 2}
            assert set(positions["isobaric"]) <= ({0, 1} if name == "z" else {0, 1, 2})
        reads.clear()
        product = next(iter(users.values()))
        np.testing.assert_array_equal(product.isobaric, [500.])
        np.testing.assert_array_equal(product.z, scene.z.isel(time=[0, 2], isobaric=[2]))
        assert reads and all(name == "z" and positions["isobaric"] == [2]
                             for name, positions in reads)


@pytest.mark.parametrize("problem", [
    "clock", "cycle", "member", "horizontal", "vertical_attributes",
    "overlapping_index", "reused_index",
])
def test_internal_vertical_alignment_rejects_incompatible_coordinates(problem):
    from frameit.tracking.tracker_core import merge_internal_stencils

    def dataset(name, labels, indices):
        return xr.Dataset({name: (("time", "isobaric", "y", "x"),
                                  np.zeros((1, len(labels), 2, 2)))}, coords={
            "time": [np.datetime64("2026-01-01", "ns")],
            "forecast_reference_time": np.datetime64("2025-12-31", "ns"),
            "isobaric": ("isobaric", labels, {"units": "hPa"}),
            "isobaric_source_native_index": ("isobaric", indices, {"units": "1"}),
            "y": [0, 1], "x": [0, 1],
        })

    left = dataset("u", [850., 700.], [0, 1])
    right = dataset("z", [700., 500.], [1, 2])
    if problem == "clock":
        right = right.assign_coords(time=[np.datetime64("2026-01-01T01", "ns")])
    elif problem == "cycle":
        right = right.assign_coords(forecast_reference_time=np.datetime64("2025-12-30", "ns"))
    elif problem == "member":
        right = right.expand_dims(number=[0])
    elif problem == "horizontal":
        right = right.assign_coords(x=[1, 2])
    elif problem == "vertical_attributes":
        right.isobaric.attrs["units"] = "Pa"
    else:
        right.isobaric_source_native_index.values[-1 if problem == "reused_index" else 0] = 0
    with pytest.raises(ValueError, match="internal|Internal"):
        merge_internal_stencils([left, right], {"isobaric"})


def test_internal_native_index_preserves_existing_coordinate_attributes(tmp_path):
    paths, _, source = _binding(
        tmp_path, [nemo_scene()], "nemo", {"3d": ["votemper"], "levels": {"indices": [0]}})
    binding = bind_requests(source, source["requests"],
                             required_inputs={"votemper": {"indices": [0, 1]}})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, resources=resources)
        exported = next(iter(users.values())).deptht_source_native_index
        selected = next(iter(internal["internal"].values())).deptht_source_native_index
        assert selected.attrs == exported.attrs
        assert selected.attrs["long_name"] == "zero-based native source deptht index"
        np.testing.assert_array_equal(selected, [0, 1])


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
def test_nemo_selected_keeps_both_clocks_bounds_and_original_indices(tmp_path, monkeypatch, engine):
    scene = nemo_scene()
    paths, binding, source = _binding(
        tmp_path, [scene], "nemo",
        {"3d": ["votemper"], "levels": {"indices": [1, 0], "units": "km"}},
        time={"values": ["2024-12-11T00:30:00"]}, engine=engine,
    )
    reads = _payload_reads(monkeypatch, [scene], {"votemper"})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, engine=engine, resources=resources)
        out = next(iter(users.values()))
        assert not reads and not internal
        assert set(out.data_vars) == {"votemper"}
        assert hasattr(out.votemper.data, "dask")
        np.testing.assert_array_equal(out.time_centered, scene.time_centered[:1])
        np.testing.assert_array_equal(out.time_counter_bounds, scene.time_counter_bounds[:1])
        np.testing.assert_array_equal(out.time_centered_bounds, scene.time_centered_bounds[:1])
        np.testing.assert_array_equal(out.deptht_source_native_index, [1, 0])
        np.testing.assert_array_equal(out.deptht, [.003, .001])
        np.testing.assert_array_equal(out.deptht_bounds, [[.002, .004], [0., .002]])
        assert out.deptht.attrs["units"] == "km"
        assert out.time.encoding["calendar"] == "proleptic_gregorian"
        np.testing.assert_array_equal(out.votemper, scene.votemper[:1, [1, 0]])
        assert out.votemper.attrs == scene.votemper.attrs
    assert reads and all(positions["time_counter"] == [0] for _, positions in reads)


@pytest.mark.parametrize("model,problem", [
    ("nemo", "geography_units"), ("nemo", "calendar"),
    ("croco", "transform"), ("croco", "positive"), ("croco", "curve_range"),
    ("croco", "critical_depth"), ("croco", "formula_units"),
])
def test_selected_ocean_does_not_bypass_native_admission(tmp_path, monkeypatch, model, problem):
    scene = nemo_scene() if model == "nemo" else croco_scene()
    field = "votemper" if model == "nemo" else "temp"
    if problem == "geography_units":
        scene.nav_lat.attrs.pop("units")
    elif problem == "calendar":
        for name in ("time_counter", "time_centered"):
            scene[name].encoding["calendar"] = "julian"
    elif problem == "transform":
        scene["Vtransform"] = xr.DataArray(1.)
    elif problem == "positive":
        scene.s_rho.attrs["positive"] = "down"
    elif problem == "curve_range":
        scene.Cs_rho.values[1] = -2.
    elif problem == "critical_depth":
        scene.hc.values[...] = 0.
    else:
        scene.zeta.attrs["units"] = "cm"
    paths, binding, source = _binding(
        tmp_path, [scene], model, {"3d": [field], "levels": {"indices": [1]}})
    reads = _payload_reads(monkeypatch, [scene], {field, "zeta"})
    with pytest.raises(ValueError, match="NEMO|CROCO"):
        _load(paths, binding, source)
    assert not reads


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
def test_croco_selected_formula_support_is_bound_lazy_and_not_extra_fields(
        tmp_path, monkeypatch, engine):
    scene = croco_scene()
    paths, binding, source = _binding(
        tmp_path, [scene], "croco", {"3d": ["temp"], "levels": {"indices": [1, 0]}},
        time={"values": ["2024-12-10T01:00:00"]}, engine=engine,
    )
    reads = _payload_reads(
        monkeypatch, [scene], {"temp", "salt", "zeta", "h", "Cs_rho", "Cs_w"})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, engine=engine, resources=resources)
        out = next(iter(users.values()))
        assert not [name for name, _ in reads if name in {"temp", "salt", "zeta", "h", "Cs_w"}]
        assert set(out.data_vars) == {"temp"}
        assert "internal" in internal
        assert hasattr(out.temp.data, "dask") and hasattr(out.zeta.data, "dask")
        np.testing.assert_array_equal(out.s_rho_source_native_index, [1, 0])
        np.testing.assert_array_equal(out.s_rho, [-.5, -.9])
        np.testing.assert_array_equal(out.Cs_rho, [-.25, -.8])
        np.testing.assert_array_equal(out.scrum_time, scene.scrum_time[:1])
        for name in ("temp", "zeta", "h"):
            expected = scene[name].isel({dim: value for dim, value in {
                "time": [0], "s_rho": [1, 0]}.items() if dim in scene[name].dims})
            np.testing.assert_array_equal(out[name], expected)
            assert out[name].attrs == scene[name].attrs
        assert all(name in out for name in out.s_rho.attrs["formula_terms"].split()[1::2])
        assert out.time.encoding["calendar"] == "gregorian"
        # Independent CF g2 check: h20,hc5,s=-.5,C=-.25,zeta1 -> -5.3 m.
        depth = out.zeta + (out.zeta + out.h) * (
            out.hc * out.s_rho + out.h * out.Cs_rho) / (out.hc + out.h)
        np.testing.assert_allclose(depth.isel(time=0, s_rho=0), -5.3, rtol=0, atol=1e-12)
        # Ordinary serialization verifies this reader's coordinate contract, not the writer.
        product = tmp_path / "reader-contract.nc"
        out.to_netcdf(product, engine=engine)
        subprocess.run([sys.executable, "-c", """
import sys
import numpy as np
import xarray as xr
with xr.open_dataset(sys.argv[1]) as out, xr.open_dataset(sys.argv[2]) as source:
    assert set(out.data_vars) == {'temp'}
    np.testing.assert_array_equal(out.temp, source.temp.isel(time=[0], s_rho=[1,0]))
    np.testing.assert_array_equal(out.s_rho_source_native_index, [1,0])
    assert out.temp.attrs['units'] == 'Celsius'
    assert out.time.encoding['calendar'] == 'gregorian'
    assert all(name in out for name in out.s_rho.attrs['formula_terms'].split()[1::2])
    s = (out.hc*out.s_rho + out.h*out.Cs_rho)/(out.hc + out.h)
    np.testing.assert_allclose((out.zeta + (out.zeta + out.h)*s).isel(time=0,s_rho=0),
                               -5.3, rtol=0, atol=1e-12)
assert not any(n == 'frameit' or n.startswith('frameit.') for n in sys.modules)
""", str(product), str(paths[0])], check=True, capture_output=True, text=True)
    assert reads and not any(name in {"salt", "Cs_w"} for name, _ in reads)
    for name, positions in reads:
        if "time" in positions:
            assert positions["time"] == [0], (name, positions)
        if "s_rho" in positions:
            assert set(positions["s_rho"]) <= {0, 1}, (name, positions)


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
@pytest.mark.parametrize("model", ["arome", "mesonh"])
@pytest.mark.parametrize("name,axis,positions", [
    ("UT", "level", [2, 0]), ("VT", "level", [2]), ("WT", "level_w", [2, 0]),
])
def test_native_components_read_no_companions_or_excluded_levels(
        tmp_path, monkeypatch, engine, model, name, axis, positions):
    scene = xr.concat([native(), native().assign_coords(
        time=[np.datetime64("2024-01-01T01", "ns")])], dim="time")
    scene[name].attrs["units"] = "cm s-1"
    scene[name].encoding["_FillValue"] = 1e20
    scene[name].values[1, positions[0], 1, 1] = 0.
    scene[name].values[1, positions[0], 1, 2] = np.nan
    paths, binding, source = _binding(
        tmp_path, [scene], model, {"3d": [name], "levels": {"indices": positions}},
        time={"values": ["2024-01-01T01:00:00"]}, engine=engine,
    )
    reads = _payload_reads(monkeypatch, [scene], {"UT", "VT", "WT"})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, engine=engine, resources=resources)
        out = next(iter(users.values()))
        assert not reads and not internal
        assert set(out.data_vars) == {name}
        assert out[name].dims == scene[name].dims
        assert out.sizes[axis] == len(positions)
        assert out[name].attrs == scene[name].attrs
        np.testing.assert_array_equal(out[name], scene[name].isel(time=[1], **{axis: positions}))
    assert reads and {variable for variable, _ in reads} == {name}
    for _, selected in reads:
        assert selected["time"] == [1]
        assert set(selected[axis]) <= set(positions)


@pytest.mark.parametrize("name", ["u", "v", "tracer_w"])
def test_croco_native_faces_and_w_never_add_companions(tmp_path, monkeypatch, name):
    scene = vector_scene()
    scene[name].values[0, 0, 2, 2] = 0.
    scene[name].values[0, 0, 2, 3] = np.nan
    paths, binding, source = _binding(
        tmp_path, [scene], "croco", {"3d": [name], "levels": {"indices": [0]}},
        time={"values": ["2024-12-10T01:00:00"]},
    )
    reads = _payload_reads(monkeypatch, [scene], {"u", "v", "tracer_w", "temp", "salt", "angle"})
    with DatasetResources() as resources:
        users, _ = _load(paths, binding, source, resources=resources)
        out = next(iter(users.values()))
        assert not reads
        assert set(out.data_vars) == {name}
        assert out[name].dims == scene[name].dims
        axis = "s_w" if name == "tracer_w" else "s_rho"
        if axis == "s_w":
            assert out.s_w.attrs["standard_name"] == "ocean_s_coordinate_g2"
            assert out.s_w.attrs["source_standard_name"] == "ocean_s_coordinate_g2_at_w_location"
        np.testing.assert_array_equal(out[name], scene[name].isel(time=[0], **{axis: [0]}))
        assert out[name].attrs == {
            key: value for key, value in scene[name].attrs.items() if key != "coordinates"}
        if name in {"u", "v"}:
            assert out[name].encoding["coordinates"] == f"lat_{name} lon_{name}"
            np.testing.assert_array_equal(out[f"lat_{name}"], scene[f"lat_{name}"])
    assert {variable for variable, _ in reads} == {name}


@pytest.mark.parametrize("export_mask", [False, True])
def test_output_and_internal_same_name_keep_independent_native_selections(
        tmp_path, monkeypatch, export_mask):
    from frameit.processing.requests import bind_requests

    scene = binding_scene()[["W"]]
    scene["mask"] = xr.ones_like(scene.W)
    scene["mask"].values[1, 5, 0, 0] = 0.
    scene["mask"].attrs = {"units": "1", "flag_values": [0, 1], "flag_meanings": "dry wet"}
    scene.W.attrs["ancillary_variables"] = "mask"
    paths, binding, source = _binding(
        tmp_path, [scene], "mesonh",
        {"3d": ["W", "mask"] if export_mask else ["W"], "levels": {"indices": [5, 0]}},
        time={"values": ["2026-01-01T01:00:00"]},
    )
    # Two native binder results exercise the frozen read interface, not a transform.
    support_request = deepcopy(source["requests"])
    support_request["levels"] = {"indices": [5, 6, 0, 1]}
    support = bind_requests(source, support_request)
    assert support["status"] == "bound"
    binding["dependencies"]["mask"] = support["dependencies"]["mask"]
    reads = _payload_reads(monkeypatch, [scene], {"W", "mask"})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, resources=resources)
        out = next(iter(users.values()))
        ancillary = next(iter(internal["internal"].values()))
        assert not reads
        np.testing.assert_array_equal(out.level_w, [45., -5.])
        np.testing.assert_array_equal(ancillary.level_w, [45., 55., -5., 5.])
        np.testing.assert_array_equal(out.W, scene.W.isel(time=[1], level_w=[5, 0]))
        if export_mask:
            np.testing.assert_array_equal(out["mask"], scene["mask"].isel(time=[1], level_w=[5, 0]))
        product_reads = list(reads)
        np.testing.assert_array_equal(
            ancillary["mask"], scene["mask"].isel(time=[1], level_w=[5, 6, 0, 1]))
        assert set(out.data_vars) == ({"W", "mask"} if export_mask else {"W"})
        assert set(ancillary.data_vars) == {"mask"}
        assert ancillary["mask"].attrs["flag_meanings"] == "dry wet"
        assert ancillary["mask"].attrs["units"] == "1"
        np.testing.assert_array_equal(ancillary["mask"].attrs["flag_values"], [0, 1])
    assert product_reads and all(set(p["level_w"]) <= {0, 5} for _, p in product_reads)
    assert any(set(p["level_w"]) == {0, 1, 5, 6} for _, p in reads)
    assert all(p["time"] == [1] for _, p in reads)


def test_moving_coordinates_static_payload_and_auxiliary_forecast_clock(tmp_path, monkeypatch):
    times = np.array(["2026-01-01T00", "2026-01-01T01", "2026-01-01T02"], dtype="datetime64[ns]")
    scene = xr.Dataset({
        "static": (("y", "x"), [[0., np.nan], [2., 3.]], {"units": "1"}),
    }, coords={
        "valid_time": ("sample", times, {"standard_name": "time", "bounds": "interval"}),
        "sample": ("sample", [41, 42, 43], {"long_name": "native sample identifier"}),
        "time": xr.DataArray(times[0], attrs={"standard_name": "forecast_reference_time"}),
        "latitude": (("sample", "y", "x"), np.arange(12.).reshape(3, 2, 2),
                     {"standard_name": "latitude", "units": "degrees_north"}),
        "longitude": (("sample", "y", "x"), np.arange(12.).reshape(3, 2, 2) + 60.,
                      {"standard_name": "longitude", "units": "degrees_east"}),
    })
    # Static payloads still carry the selected moving-coordinate contexts.
    scene["moving"] = (("sample", "y", "x"), np.arange(12.).reshape(3, 2, 2), {"units": "1"})
    scene["interval"] = (("sample", "nv"), times[:, None] + np.array(
        [-30, 30], dtype="timedelta64[m]"))
    scene.valid_time.encoding["units"] = "minutes since 2026-01-01"
    scene.interval.encoding["units"] = "minutes since 2026-01-01"
    paths, binding, source = _binding(
        tmp_path, [scene], "arome", {"2d": ["static", "moving"]},
        time={"values": ["2026-01-01T00:00:00", "2026-01-01T02:00:00"]},
    )
    reads = _payload_reads(monkeypatch, [scene], {"static", "moving"})
    with DatasetResources() as resources:
        users, _ = _load(paths, binding, source, resources=resources)
        assert not reads
        static = next(ds for ds in users.values() if "static" in ds)
        moving = next(ds for ds in users.values() if "moving" in ds)
        assert static.static.dims == ("y", "x")
        np.testing.assert_array_equal(static.static, [[0., np.nan], [2., 3.]])
        np.testing.assert_array_equal(moving.moving, scene.moving[[0, 2]])
        np.testing.assert_array_equal(moving.latitude, scene.latitude[[0, 2]])
        np.testing.assert_array_equal(moving.longitude, scene.longitude[[0, 2]])
        np.testing.assert_array_equal(moving["sample"], [41, 43])
        np.testing.assert_array_equal(moving.interval, scene.interval[[0, 2]])
        assert moving.forecast_reference_time.values == times[0]
    assert reads and all(set(p.get("sample", [])) <= {0, 2} for _, p in reads)


def test_croco_time_series_support_stays_lazy_with_distinct_static_providers(tmp_path, monkeypatch):
    scenes = [croco_scene().isel(time=[index]) for index in (0, 1)]
    scenes[1]["h"] = scenes[1].h + 1.
    scenes[1].h.attrs["units"] = "meter"
    paths, binding, source = _binding(
        tmp_path, scenes, "croco", {"3d": ["temp"], "levels": {"indices": [1]}})
    reads = _payload_reads(monkeypatch, scenes, {"temp", "zeta", "h", "salt"})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, resources=resources)
        assert not reads
        out = next(iter(users.values()))
        np.testing.assert_array_equal(out.h[:, 0, 0], [20., 21.])
        np.testing.assert_array_equal(out.zeta[:, 0, 0], [1., 2.])
        support = next(ds for ds in internal["internal"].values() if "h" in ds)
        np.testing.assert_array_equal(support.h[:, 0, 0], [20., 21.])
        np.testing.assert_array_equal(out.temp, xr.concat(
            [scene.temp.isel(s_rho=[1]) for scene in scenes], dim="time"))
    assert reads and not any(name == "salt" for name, _ in reads)


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
def test_croco_retained_multi_time_static_support_is_not_eager(tmp_path, monkeypatch, engine):
    scene = croco_scene()
    # Excluded sigma samples must not be read even for admission.
    scene.Cs_rho.values[2] = -2.
    paths, binding, source = _binding(
        tmp_path, [scene], "croco", {"3d": ["temp"], "levels": {"indices": [0]}},
        engine=engine)
    reads = _payload_reads(monkeypatch, [scene], {"temp", "h", "zeta", "Cs_rho", "salt"})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, engine=engine, resources=resources)
        assert not [n for n, _ in reads if n in {"temp", "h", "zeta", "salt"}]
        out = next(iter(users.values()))
        assert out.h.dims == ("eta_rho", "xi_rho")
        assert next(ds for ds in internal["internal"].values() if "h" in ds).h.dims == (
            "eta_rho", "xi_rho")
        np.testing.assert_array_equal(out.temp, scene.temp.isel(s_rho=[0]))
        np.testing.assert_array_equal(out.zeta, scene.zeta)
        np.testing.assert_array_equal(out.h, scene.h)
    assert reads and all(p.get("s_rho", [0]) == [0] for _, p in reads)
    assert not any(n == "salt" for n, _ in reads)


@pytest.mark.parametrize("field,axis", [
    ("vozocrtx", "depthu"), ("vomecrty", "depthv"), ("vovecrtz", "depthw"),
])
def test_nemo_native_components_copy_without_unit_or_basis_changes(
        tmp_path, monkeypatch, field, axis):
    scene = nemo_scene(field=field, depth=axis)
    scene[field].attrs.update(units="cm s-1", standard_name={
        "vozocrtx": "sea_water_x_velocity", "vomecrty": "sea_water_y_velocity",
        "vovecrtz": "upward_sea_water_velocity"}[field])
    scene["unrequested"] = xr.zeros_like(scene[field])
    paths, binding, source = _binding(
        tmp_path, [scene], "nemo", {"3d": [field], "levels": {"indices": [0]}},
        time={"values": ["2024-12-11T00:30:00"]})
    reads = _payload_reads(monkeypatch, [scene], {field, "unrequested"})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, resources=resources)
        out = next(iter(users.values()))
        assert not reads and not internal
        assert set(out.data_vars) == {field} and out.sizes[axis] == 1
        np.testing.assert_array_equal(
            out[field], scene[field].isel(time_counter=[0], **{axis: [0]}))
        assert out[field].attrs == scene[field].attrs
    assert reads and {n for n, _ in reads} == {field}
    assert all(p["time_counter"] == [0] and p[axis] == [0] for _, p in reads)


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
def test_variable_shards_use_bound_providers_and_never_open_excluded_file(
        tmp_path, monkeypatch, engine):
    scene = binding_scene()[["S"]]
    other = scene.rename(S="other")
    excluded = scene.assign_coords(time=scene.time + np.timedelta64(5, "h"))
    paths, binding, source = _binding(
        tmp_path, [scene, other, excluded], "mesonh", {"2d": ["S", "other"]},
        time={"values": ["2026-01-01T01:00:00"]}, engine=engine)
    opened = []
    original = xr.open_dataset

    def tracked(path, **kwargs):
        opened.append(Path(path))
        return original(path, **kwargs)

    monkeypatch.setattr(xr, "open_dataset", tracked)
    reads = _payload_reads(monkeypatch, [scene, other, excluded], {"S", "other"})
    with DatasetResources() as resources:
        users, internal = _load(paths, binding, source, engine=engine, resources=resources)
        assert not reads and not internal
        out = next(iter(users.values()))
        assert set(out.data_vars) == {"S", "other"}
        for field in ("S", "other"):
            np.testing.assert_array_equal(out[field], scene.S.isel(time=[1]))
    assert opened == paths[:2]
    assert reads and all(p["time"] == [1] for _, p in reads)


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
@pytest.mark.parametrize("lead_positions", [[1], [0, 2]])
def test_cycle_locators_slice_before_payload_work(tmp_path, monkeypatch, engine, lead_positions):
    cycles = np.array(["2026-01-01T00", "2026-01-01T06"], dtype="datetime64[ns]")
    scene = xr.Dataset({
        "T": (("cycle", "lead", "level", "y", "x"), np.arange(24.).reshape(2, 3, 2, 1, 2),
              {"units": "K"}),
    }, coords={
        "forecast_reference_time": ("cycle", cycles, {"standard_name": "forecast_reference_time"}),
        "valid_time": (("cycle", "lead"), cycles[:, None]
                       + np.arange(3)[None, :] * np.timedelta64(1, "h"),
                       {"standard_name": "time"}),
        "cycle": [91, 92], "lead": [0, 1, 2],
        "level": ("level", [10., 20.], {"axis": "Z", "units": "m"}),
    })
    paths, binding, source = _binding(
        tmp_path, [scene], "arome", {"3d": ["T"], "levels": {"indices": [1]}},
        time={"cycle": "2026-01-01T06:00:00", "values": [
            f"2026-01-01T{6 + position:02d}:00:00" for position in lead_positions]},
        engine=engine)
    reads = _payload_reads(monkeypatch, [scene], {"T"})
    with DatasetResources() as resources:
        users, _ = _load(paths, binding, source, engine=engine, resources=resources)
        assert not reads
        out = next(iter(users.values()))
        np.testing.assert_array_equal(out.T, scene.T.isel(
            cycle=[1], lead=lead_positions, level=[1]))
        np.testing.assert_array_equal(out.forecast_reference_time, cycles[1:])
        np.testing.assert_array_equal(out.cycle, [92])
        np.testing.assert_array_equal(out.lead, lead_positions)
        np.testing.assert_array_equal(out.time, scene.valid_time.isel(
            cycle=[1], lead=lead_positions))
    assert reads and all(p["cycle"] == [1] and set(p["lead"]) <= set(lead_positions)
                         and p["level"] == [1]
                         for _, p in reads)


def test_multiple_varying_native_sample_axes_fail_without_payload_reads(tmp_path, monkeypatch):
    times = np.array(["2026-01-01T00", "2026-01-01T01", "2026-01-01T02",
                      "2026-01-01T03"], dtype="datetime64[ns]").reshape(2, 2)
    scene = xr.Dataset({
        "S": (("row", "column", "y", "x"), np.arange(4.).reshape(2, 2, 1, 1), {"units": "1"}),
    }, coords={
        "valid_time": (("row", "column"), times, {"standard_name": "time"}),
        "row": [10, 20], "column": [30, 40],
    })
    paths, binding, source = _binding(
        tmp_path, [scene], "arome", {"2d": ["S"]},
        time={"values": ["2026-01-01T00:00:00", "2026-01-01T03:00:00"]})
    reads = _payload_reads(monkeypatch, [scene], {"S"})
    with pytest.raises(ValueError, match="multiple native sample axes"):
        _load(paths, binding, source)
    assert not reads


def test_selected_arome_retains_existing_clock_collision_admission(tmp_path, monkeypatch):
    scene = binding_scene()[["S"]].rename(time="valid_time")
    scene.attrs = {}
    scene = scene.assign_coords(time=("valid_time", scene.valid_time.values))
    paths, binding, source = _binding(tmp_path, [scene], "arome", {"2d": ["S"]})
    reads = _payload_reads(monkeypatch, [scene], {"S"})
    with pytest.raises(ValueError, match="conflicts with configured|unambiguous"):
        _load(paths, binding, source)
    assert not reads


@pytest.mark.parametrize("owned,fail", [(True, False), (True, True), (False, True)])
def test_selected_original_handles_close_and_failure_preserves_prior_owner(
        tmp_path, monkeypatch, owned, fail):
    scene = binding_scene()[["S"]]
    paths, binding, source = _binding(tmp_path, [scene], "mesonh", {"2d": ["S"]})
    if fail:
        binding["products"]["model_grid"]["S"]["records"][-1]["locator"]["path"] = str(
            tmp_path / "not-admitted.nc")
    opened, closed = [], []
    original = xr.open_dataset

    def tracked(path, **kwargs):
        ds = original(path, **kwargs)
        close, token = ds._close, len(opened)
        opened.append(Path(path))

        def closing():
            closed.append(token)
            close()

        ds.set_close(closing)
        return ds

    monkeypatch.setattr(xr, "open_dataset", tracked)
    resources = None if owned else DatasetResources()
    if resources is not None:
        resources.open_netcdf(paths[0], engine="h5netcdf", chunks={})
    reads = _payload_reads(monkeypatch, [scene], {"S"})
    if fail:
        with pytest.raises(ValueError, match="admitted"):
            _load(paths, binding, source, resources=resources)
        assert not reads
        if owned:
            assert closed == [0]
        else:
            assert closed == [1] and len(resources._datasets) == 1
            resources.close()
    else:
        users, _ = _load(paths, binding, source)
        out = next(iter(users.values()))
        assert not closed and not reads
        np.testing.assert_array_equal(out.S, scene.S)
        out.close()
        out.close()
    assert set(closed) == set(range(len(opened)))


@pytest.mark.parametrize("gate", ["pending", "destination", "polar"])
def test_pending_or_non_native_binding_never_reads_payload(tmp_path, monkeypatch, gate):
    scene = binding_scene()[["S"]]
    paths, binding, source = _binding(tmp_path, [scene], "mesonh", {"2d": ["S"]})
    if gate == "pending":
        binding["status"] = "pending_method_binding"
    elif gate == "destination":
        binding["products"]["model_grid"]["S"]["records"][0]["selection_grid_id"] = "destination"
    else:
        binding["products"]["polar"] = binding["products"].pop("model_grid")
    reads = _payload_reads(monkeypatch, [scene], {"S"})
    with pytest.raises(ValueError, match="bound|transformation|polar"):
        _load(paths, binding, source)
    assert not reads


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4"])
def test_vertical_moving_coordinate_metadata_uses_own_sample_indexers(
        tmp_path, monkeypatch, engine):
    scene = binding_scene()[["T", "level_bounds"]]
    values = np.arange(72.).reshape(2, 6, 2, 3)
    scene = scene.assign_coords({
        "latitude": (("time", "level", "y", "x"), values,
                     {"standard_name": "latitude", "units": "degrees_north"}),
        "longitude": (("time", "level", "y", "x"), values + 60.,
                      {"standard_name": "longitude", "units": "degrees_east"}),
    })
    paths, binding, source = _binding(
        tmp_path, [scene], "mesonh", {"3d": ["T"], "levels": {"indices": [5, 0], "units": "km"}},
        time={"values": ["2026-01-01T01:00:00"]}, engine=engine)
    reads = _payload_reads(monkeypatch, [scene], {"T"})
    with DatasetResources() as resources:
        users, _ = _load(paths, binding, source, engine=engine, resources=resources)
        assert not reads
        out = next(iter(users.values()))
        np.testing.assert_array_equal(out.latitude, scene.latitude.isel(time=[1], level=[5, 0]))
        np.testing.assert_array_equal(out.longitude, scene.longitude.isel(time=[1], level=[5, 0]))
        np.testing.assert_array_equal(out.level, [.05, 0.])
        np.testing.assert_array_equal(out.T, scene.T.isel(time=[1], level=[5, 0]))
    assert reads and all(p["time"] == [1] and set(p["level"]) <= {0, 5} for _, p in reads)
