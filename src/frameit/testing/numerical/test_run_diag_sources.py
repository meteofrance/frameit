"""Bound NetCDF reading and producer evidence, not real-model qualification."""

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from frameit.core.configuration import to_runtime
from frameit.core.execution import ExecutionOptions, execute_simulation
from frameit.core.settings_class import SimulationConfig
from frameit.testing.numerical.test_run_diag_configuration import request
from frameit.testing.numerical.test_run_diag_lifecycle import run_diag, write_request
from frameit.testing.numerical.test_v3_run_state import record


def vortex_input(path, *, temporal="qualified", size=45, declared_height=10.0, edit_input=None):
    from pyproj import Geod

    lat = -20.0 + 0.05 * (np.arange(size) - size // 2)
    lon = 60.0 + 0.05 * (np.arange(size) - size // 2)
    xx, yy = np.meshgrid(lon, lat)
    _, _, metres = Geod(a=6371000, b=6371000).inv(
        np.full(xx.shape, 60.0), np.full(xx.shape, -20.0), xx, yy
    )
    shape = (2, size, size)
    radius = metres / 18000
    speed = np.broadcast_to(44 * radius * np.exp(1 - radius), shape)
    wind = {"units": "m s-1", "wind_reference_frame": "earth"}
    if declared_height is not None:
        wind["height_above_ground_m"] = declared_height
    time_attrs = {"standard_name": "time", "bounds": "time_bounds"}
    if temporal == "qualified":
        wind["cell_methods"] = "time: mean"
    else:
        wind["temporal_kind"] = "instantaneous"
    times = np.array(["2000-01-01T00", "2000-01-01T01"], dtype="datetime64[s]")
    dims = ("time", "latitude", "longitude")
    data = xr.Dataset(
        {
            "wind10": (dims, speed, {**wind, "standard_name": "wind_speed"}),
            "wind_levels": (
                ("time", "height", "latitude", "longitude"),
                np.stack((speed, speed + 1), axis=1),
                {**wind, "standard_name": "wind_speed"},
            ),
            "u": (dims, speed, {**wind, "standard_name": "eastward_wind"}),
            "v": (dims, np.zeros(shape), {**wind, "standard_name": "northward_wind"}),
            "mslp": (
                dims,
                np.broadcast_to(98000 + metres * 0.02, shape),
                {"units": "Pa", "standard_name": "air_pressure_at_mean_sea_level"},
            ),
            "area": (dims, np.full(shape, 3e7), {"units": "m2", "standard_name": "cell_area"}),
            "unused": (dims, np.zeros(shape)),
            "time_bounds": (
                ("time", "bounds"),
                np.stack((times - np.timedelta64(600, "s"), times), axis=1),
            ),
        },
        coords={
            "time": ("time", times, time_attrs),
            "height": (
                "height",
                [10.0, 20.0],
                {"standard_name": "height", "units": "m", "positive": "up", "axis": "Z"},
            ),
            "latitude": ("latitude", lat, {"standard_name": "latitude", "units": "degrees_north"}),
            "longitude": (
                "longitude",
                lon,
                {"standard_name": "longitude", "units": "degrees_east"},
            ),
        },
        attrs={"earth_radius": 6371000.0},
    )
    encoding = {
        var: {"units": "seconds since 2000-01-01", "calendar": "proleptic_gregorian"}
        for var in ("time", "time_bounds")
    }
    if edit_input is not None:
        edit_input(data)
    data.to_netcdf(path, engine="h5netcdf", encoding=encoding)


def vortex_parent(
    tmp_path,
    *,
    kind="original",
    model="arome",
    temporal="qualified",
    size=45,
    fields=("wind10", "mslp", "area"),
    width=190,
    output_format="netcdf",
    declared_height=10.0,
    export_track=False,
    edit_input=None,
):
    raw = request(kind=kind)
    raw["sources"]["weather"].update(
        model=model,
        files="vortex*.nc",
        variables={"2d": list(fields)},
        reader={"engine": "h5netcdf"},
    )
    raw["output"] = {"directory": "parent", "format": output_format}
    raw["resources"] = {"cpus": 1, "scheduler": "synchronous", "synchronous_export": True}
    raw["region"] = {
        "center": {"latitude": -20.0, "longitude": 60.0},
        "width_km": {"x": width, "y": width},
    }
    if export_track:
        raw["products"] = {"track": True, "model_grid": True}
    best = raw["diagnostics"]["best_track"]
    best["fields"]["cell_area"] = "area"
    best["rmw"]["azimuth_sectors"] = 4
    best["search"]["wind_radii_radius_km"] = 80
    raw_source = tmp_path / "vortex.nc"
    vortex_input(
        raw_source,
        temporal=temporal,
        size=size,
        declared_height=declared_height,
        edit_input=edit_input,
    )
    original = {key: val for key, val in raw.items() if key != "diagnostics"}
    conf = SimulationConfig(**to_runtime(original, base_dir=tmp_path))
    execute_simulation(conf, ExecutionOptions.from_config(conf))
    return write_request(tmp_path / "config.yaml", raw), raw, raw_source, conf.output_dir


@pytest.mark.parametrize(
    ("kind", "model", "earth_attrs", "mapping_attrs", "expected"),
    [
        pytest.param(
            "original", "mesonh", {}, None,
            (6371229.0, "Meso-NH default (INI_CST.XRADIUS)"), id="mesonh",
        ),
        pytest.param(
            "original", "mesonh", {"earth_radius": 6371000.0}, None,
            (6371000.0, "dataset Earth model"), id="explicit",
        ),
        pytest.param("model_grid", "mesonh", {}, None, None, id="crop"),
        pytest.param("original", "arome", {}, None, None, id="other-model"),
        pytest.param(
            "original", "mesonh", {"semi_major_axis": 6371000.0}, None, None, id="incomplete",
        ),
        pytest.param("original", "mesonh", {"earth_radius": -1.0}, None, None, id="invalid"),
        pytest.param(
            "original", "mesonh", {"earth_radius": 6371000.0}, ("crs", {"earth_radius": 6372000.0}),
            None, id="conflict",
        ),
        pytest.param("original", "mesonh", {}, ("crs", None), None, id="dangling-mapping"),
        pytest.param("original", "mesonh", {}, ("crs", {}), None, id="empty-mapping"),
        pytest.param(
            "original", "mesonh", {}, ("crs", {"grid_mapping_name": "latitude_longitude"}),
            (6371229.0, "Meso-NH default (INI_CST.XRADIUS)"), id="projection-only",
        ),
        pytest.param(
            "original", "mesonh", {"earth_radius": 6371000.0},
            ("crs: latitude longitude", {"earth_radius": 6350000.0}),
            None, id="unresolved-expanded-mapping",
        ),
        pytest.param(
            "original", "mesonh", {},
            ("crs", {
                "crs_wkt": 'GEOGCS["Test sphere",DATUM["Test",SPHEROID["S",6350000,0]],'
                           'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
                "earth_radius": 6371000.0,
            }),
            None, id="conflicting-wkt",
        ),
    ],
)
def test_original_netcdf_earth_model_default(
    tmp_path, kind, model, earth_attrs, mapping_attrs, expected,
):
    from pyproj import Geod

    def edit_input(ds):
        ds.latitude.attrs["axis"] = "Y"
        ds.longitude.attrs["axis"] = "X"
        del ds.attrs["earth_radius"]
        ds.attrs.update(earth_attrs)
        if mapping_attrs is not None:
            link, attrs = mapping_attrs
            for name in ("wind10", "mslp", "area"):
                ds[name].attrs["grid_mapping"] = link
            if attrs is not None:
                ds["crs"] = xr.DataArray(0, attrs=attrs)

    cfg, _, _, _ = vortex_parent(tmp_path, kind=kind, model=model, edit_input=edit_input)
    report = run_diag(cfg, check=True)
    if expected is None:
        assert report["status"] == "error" and report["errors"][0]["code"] == "E2003", report
        assert "Earth model" in report["errors"][0]["message"]
        return

    assert report["status"] == "ok", report["errors"]
    radius, origin = expected
    groups = report["data"]["plan"]["groups"]
    assert groups
    for group in groups:
        for source in group["sources"]:
            grid = source["grid"]
            assert grid["earth"] == [radius, radius]
            assert grid["earth_origin"] == origin
            a, b = grid["earth"]
            assert Geod(a=a, b=b).inv(0, 0, 1, 0)[2] == pytest.approx(
                radius * np.pi / 180, rel=1e-12,
            )


def test_mesonh_default_reuses_admitted_metadata_for_execution(tmp_path):
    def edit_input(ds):
        ds.latitude.attrs["axis"] = "Y"
        ds.longitude.attrs["axis"] = "X"
        del ds.attrs["earth_radius"]
        ds.unused.attrs["grid_mapping"] = "crs rubbish"
        wind = np.zeros(ds.wind10.shape)
        wind[:, ds.sizes["latitude"] // 2 + 5, ds.sizes["longitude"] // 2] = 40
        ds.wind10.data = wind

    cfg, _, _, _ = vortex_parent(tmp_path, model="mesonh", edit_input=edit_input)
    check = run_diag(cfg, check=True)
    assert check["status"] == "ok", check["errors"]
    report = run_diag(cfg)
    assert report["status"] == "ok" and report["data"]["plan"]["committed"], report["errors"]
    attempt = Path(report["data"]["plan"]["attempt_directory"])
    with xr.open_dataset(attempt / "best_track/model_best_track.nc") as ds:
        # The only threshold exceedance is 0.25 degrees due north of the centre.
        np.testing.assert_allclose(
            ds.wind_radius.isel(threshold=0, quadrant=0), 6371229.0 * np.pi / 720, rtol=1e-10,
        )
    provenance = record(attempt, "diagnostics-provenance.yaml")
    grids = [source["grid"] for group in provenance["plan"]["groups"] for source in group["sources"]]
    assert grids and all(g["earth"] == [6371229.0, 6371229.0] for g in grids)
    assert {g["earth_origin"] for g in grids} == {"Meso-NH default (INI_CST.XRADIUS)"}


def test_exact_netcdf_selection(tmp_path, monkeypatch):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper

    cfg, raw, path, root = vortex_parent(tmp_path)
    raw["diagnostics"]["best_track"]["fields"]["wind"] = {
        "speed": {
            "field": "wind_levels",
            "group": "height",
            "level": {"value": 0.01, "units": "km"},
        }
    }
    write_request(cfg, raw)
    # This file matches the current glob, but was not admitted by the parent.
    (tmp_path / "vortex-new.nc").write_bytes(b"not a NetCDF")
    report = run_diag(cfg, check=True)
    assert report["status"] == "ok", report["errors"]

    from frameit.core.configuration import resolve_schema
    from frameit.diagnostics.runner import _admit_parent
    from frameit.diagnostics.sources import open_source, plan_source

    native_get = H5NetCDFArrayWrapper._getitem
    seen = []

    def traced(array, key):
        if array.variable_name in {"wind_levels", "wind10", "unused"}:
            seen.append((array.variable_name, key))
        return native_get(array, key)

    monkeypatch.setattr(H5NetCDFArrayWrapper, "_getitem", traced)
    conf, _, _ = resolve_schema(raw, base_dir=cfg.parent)
    parent = _admit_parent(
        root, raw, base_dir=cfg.parent, source_name="weather", source_kind="original"
    )
    plan = plan_source(parent, conf["diagnostics"]["best_track"], scratch=tmp_path)
    assert seen == []  # Planning reads declarations/coordinates, not selected payload.
    with open_source(plan, scratch=tmp_path) as reader:
        wind = next(
            group for group in reader.samples(parent.centres[0].time) if group.role == "wind"
        )
        with reader.open_group(wind) as view:
            block = view.read((slice(3, 6), slice(4, 8)))
    assert block.values["speed"].shape == (3, 4)
    assert seen == [("wind_levels", (0, 0, slice(3, 6, 1), slice(4, 8, 1)))]
    path.touch()
    assert run_diag(cfg, check=True)["errors"][0]["code"] == "E2003"


def test_cropped_without_raw_or_catalogue(tmp_path, monkeypatch):
    cfg, _, raw_source, root = vortex_parent(tmp_path, kind="model_grid")
    raw_source.unlink()

    def unexpected(*args, **kwargs):
        pytest.fail("a crop must not access catalogue or raw discovery")

    monkeypatch.setattr("frameit.io.loader.inventory_source_files", unexpected)
    monkeypatch.setattr("frameit.core.metadata_catalogue.open_catalogue", unexpected)
    plan = run_diag(cfg, check=True)
    assert plan["status"] == "ok", plan["errors"]
    (product,) = (root / "products").glob("*.nc")
    product.touch()
    failure = run_diag(cfg, check=True)
    assert failure["errors"][0]["code"] == "E2003"
    assert "identity" in failure["errors"][0]["message"]


def test_wind_and_gust_evidence(tmp_path):
    cfg, raw, _, _ = vortex_parent(tmp_path, fields=("u", "v", "mslp", "area"))
    best = raw["diagnostics"]["best_track"]
    best["fields"]["wind"] = {"u": "u", "v": "v"}
    write_request(cfg, raw)
    report = run_diag(cfg, check=True)
    assert report["status"] == "ok", report["errors"]
    summaries = report["data"]["plan"]["groups"]
    wind = next(group for group in summaries if group["role"] == "wind")
    assert wind["temporal_statistic"] == "magnitude_of_mean_components"
    assert wind["averaging_seconds"] == 600
    assert wind["qualified"] is False
    assert np.hypot(np.mean([4.0, 0.0]), np.mean([0.0, 4.0])) < np.mean([4.0, 4.0])


def test_wind_location_metadata_overrides_apparent_collocation(tmp_path):
    def mark_staggered(ds):
        for name in ("u", "v"):
            ds[name].attrs.update(
                location=name,
                sustained_wind_convention="magnitude_of_mean_components_compatible_10min",
            )

    cfg, raw, _, root = vortex_parent(tmp_path, edit_input=mark_staggered)
    raw["diagnostics"]["best_track"]["fields"]["wind"] = {"u": "u", "v": "v"}
    write_request(cfg, raw)
    report = run_diag(cfg, check=True)
    assert report["status"] == "error" and report["errors"][0]["code"] == "E2003", report
    assert "point location" in report["errors"][0]["message"]
    assert not (root / "diagnostics").exists()


@pytest.mark.parametrize("kind", ["original", "model_grid"])
def test_packed_validity_metadata_fails_closed(tmp_path, kind):
    def pack_wind(ds):
        ds.wind10.attrs["valid_range"] = np.array([0, 600], dtype="int16")
        ds.wind10.encoding.update(dtype="int16", scale_factor=0.1, _FillValue=np.int16(-32768))

    cfg, _, _, root = vortex_parent(tmp_path, kind=kind, edit_input=pack_wind)
    report = run_diag(cfg, check=True)
    assert report["status"] == "error" and report["errors"][0]["code"] == "E2003", report
    assert "packed" in report["errors"][0]["message"]
    assert not (root / "diagnostics").exists()


def test_budget_and_scope(tmp_path):
    cfg, raw, _, root = vortex_parent(tmp_path)
    best = raw["diagnostics"]["best_track"]
    best["processing"] = {"working_memory_mib": 1, "max_open_files": 1}
    best["rmw"]["azimuth_sectors"] = 10**9
    write_request(Path(cfg), raw)
    report = run_diag(cfg, check=True)
    assert report["errors"][0]["code"] == "E2003"
    assert "accumulator" in report["errors"][0]["message"]
    assert not (root / "diagnostics").exists()
    assert not (root / ".frameit-run.lock").exists()


@pytest.mark.parametrize(
    "cell_methods",
    [
        "time: mean within days time: mean over days",
        "time: maximum time: mean",
    ],
)
def test_compound_temporal_operators_are_not_ten_minute_scalar_means(cell_methods):
    from types import SimpleNamespace

    from frameit.diagnostics.sources import _semantics

    attrs = {
        "units": "m s-1",
        "standard_name": "wind_speed",
        "wind_reference_frame": "earth",
        "cell_methods": cell_methods,
    }
    sample = {
        "time": "2000-01-01T00:00",
        "time_bounds": ("1999-12-31T23:50", "2000-01-01T00:00"),
        "temporal_names": ("time",),
    }
    statistic, _, qualified, _ = _semantics(
        "speed",
        SimpleNamespace(name="wind"),
        attrs,
        10.0,
        sample,
        (),
    )
    assert not qualified
    assert statistic == "unverified"
