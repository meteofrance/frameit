import numpy as np
import pytest
import xarray as xr

from frameit.core.configuration import validate_wind_pressure_initial_guess
from frameit.core.settings_class import SimulationConfig
from frameit.tracking.PressureWind_Tracker import PressureWindTracker


def dataset(curved=False):
    p = np.full((2, 7, 15), 101000.)
    p[:, 3, 2] = 98000.  # Deeper, unwanted disturbance.
    p[:, 3, 11] = 99000.
    ds = xr.Dataset({
        'prmsl': (('time', 'y', 'x'), p),
        'u10': (('time', 'y', 'x'), p - 97000., {'units': 'm s-1'}),
        'v10': (('time', 'y', 'x'), np.zeros_like(p), {'units': 'm s-1'}),
    }, coords={'time': np.array(['2026-10-23', '2026-10-23T06:00'], dtype='datetime64[ns]'),
               'latitude': ('y', np.arange(7)*.1 - 6.1),
               'longitude': ('x', np.arange(15)*.1 + 49.)})
    if curved:
        lat, lon = xr.broadcast(ds.latitude, ds.longitude)
        ds = ds.assign_coords(latitude=lat, longitude=lon)
    return ds


def tracker(seed=None):
    return PressureWindTracker({'mslp': 'prmsl', 'u10m': 'u10', 'v10m': 'v10'},
                               11000, search_half_width_km=20,
                               refine_half_width_km=11, initial_guess=seed)


@pytest.mark.parametrize('curved', [False, True])
def test_seed_selects_local_disturbance_and_then_follows_it(curved):
    ds = dataset(curved)
    np.testing.assert_array_equal(tracker()._track_method(ds).cx, [2, 2])
    result = tracker({'latitude': -5.8, 'longitude': 50.1,
                      'search_radius_km': 20})._track_method(ds)
    np.testing.assert_array_equal(result.cx, [11, 11])
    np.testing.assert_array_equal(result.cy, [3, 3])


def test_seed_no_coverage_or_all_missing_fails_without_global_fallback():
    seed = {'latitude': -5.8, 'longitude': 50.1, 'search_radius_km': 20}
    ds = dataset()
    ds.prmsl[:, :, 9:] = np.nan
    with pytest.raises(ValueError, match='no finite MSLP'):
        tracker(seed)._track_method(ds)
    with pytest.raises(ValueError, match='no finite MSLP'):
        tracker({**seed, 'latitude': 40})._track_method(dataset())


def test_geodesic_circle_excludes_diagonal_and_accepts_wrapped_longitudes():
    ds = dataset()
    ds.prmsl[:, 4, 12] = 97000.  # In a bounding square, outside the 12-km circle.
    ds = ds.assign_coords(longitude=ds.longitude + 360)
    result = tracker({'latitude': -5.8, 'longitude': 50.1,
                      'search_radius_km': 12})._track_method(ds)
    np.testing.assert_array_equal(result.cx, [11, 11])
    assert result.attrs['wind_pressure_initial_search_radius_km'] == 12


@pytest.mark.parametrize('update', [{'latitude': 91}, {'longitude': 181},
                                  {'latitude': True}, {'longitude': np.nan},
                                  {'search_radius_km': 0}, {'search_radius_km': np.inf},
                                  {'search_radius_km': None}, {'typo': 1}])
def test_invalid_seed(update):
    with pytest.raises(ValueError):
        validate_wind_pressure_initial_guess(
            {'latitude': -5.8, 'longitude': 50., 'search_radius_km': 100, **update})


def test_schema_maps_seed_to_tracker():
    seed = {'latitude': -5.8, 'longitude': 50., 'search_radius_km': 100}
    conf = SimulationConfig.from_mapping_with_model_preset({
        'schema_version': '2.1', 'model': 'arome',
        'input': {'pattern': '*.grib', 'format': 'grib'},
        'tracking': {'method': 'pressure_wind', 'pressure_wind': {'initial_guess': seed}}})
    conf.resolution = 2500
    assert PressureWindTracker.from_config(conf).initial_guess == seed


@pytest.mark.parametrize("case,expected,read_counts", [
    ("ordinary", [1, 1], {"p": 2, "u": 2, "v": 2}),
    ("pressure_fallback", [1, 5], {"p": 3, "u": 2, "v": 2}),
    ("wind_fallback", [5, 5], {"p": 2, "u": 3, "v": 3}),
])
def test_lazy_search_windows_are_evaluated_once_with_existing_fallbacks(case, expected, read_counts):
    from collections import Counter

    import dask
    import dask.array as da

    from frameit.tracking.PressureWind_Tracker import pressure_wind_tracker

    pressure = np.full((2, 7, 7), 101000.)
    u, v = np.full_like(pressure, 10.), np.zeros_like(pressure)
    pressure[:, 1, 1], u[:, 1, 1] = 98000., 0.
    if case == "pressure_fallback":
        pressure[1] = np.nan
        pressure[1, 5, 5], u[1, 5, 5] = 97000., -1.
        u[1, 1, 1] = 10.
    elif case == "wind_fallback":
        u[0, :3, :3] = np.nan
        u[:, 5, 5], pressure[1, 5, 5] = 0., 97000.
    reads = Counter()

    def load(name, values):
        reads[name] += 1
        return values

    fields = [xr.DataArray(da.stack([da.from_delayed(dask.delayed(load)(name, row),
                                                    shape=(7, 7), dtype=float) for row in values]),
                           dims=("time", "y", "x"), coords={"time": [0, 1]})
              for name, values in (("p", pressure), ("u", u), ("v", v))]
    with dask.config.set(scheduler="synchronous"):
        cy, cx = pressure_wind_tracker(*fields, half_search=1, half_refine=1)
    np.testing.assert_array_equal(cy, expected)
    np.testing.assert_array_equal(cx, expected)
    assert reads == read_counts


def test_all_missing_global_pressure_still_fails():
    from frameit.tracking.PressureWind_Tracker import pressure_wind_tracker

    field = xr.DataArray(np.full((1, 3, 3), np.nan), dims=("time", "y", "x"),
                         coords={"time": [0]}).chunk({"time": 1})
    with pytest.raises(ValueError, match="All.NaN"):
        pressure_wind_tracker(field, field, field, half_search=1, half_refine=1)
