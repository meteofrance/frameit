"""Selected lazy assembly: variable shards are not successive snapshots."""

from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from frameit.io.loader import DatasetResources
from frameit.io.netcdf_utils import concat_nc2ds, concat_nc2ds_by_vert_coord

TIMES = np.array(['2024-12-11T00', '2024-12-11T06'], dtype='datetime64[ns]')
REFERENCE = np.datetime64('2024-12-11T00', 'ns')


def shard(name, value, *, forecast=True):
    coords = {'valid_time': TIMES,
              'latitude': ('latitude', [-20., -19.99, -19.98], {'units': 'degrees_north'}),
              'longitude': ('longitude', [60., 60.01, 60.02], {'units': 'degrees_east'})}
    if forecast:
        coords['time'] = xr.DataArray(REFERENCE, attrs={'standard_name': 'forecast_reference_time'})
    return xr.Dataset({name: (('valid_time', 'latitude', 'longitude'),
                             np.full((2, 3, 3), value), {'units': 'Pa' if name == 'prmsl' else 'm s-1'})},
                      coords=coords)


def write_shards(tmp_path, datasets):
    paths = []
    for i, ds in enumerate(datasets):
        path = tmp_path / f'part{i}.nc'
        ds.to_netcdf(path)
        paths.append(path)
    return paths


def load(paths, names, **kwargs):
    return concat_nc2ds_by_vert_coord(
        paths, {'surface': {'variables': names}}, {}, concat_dimension='valid_time',
        file_layout='variables', **kwargs)[0]['surface']


@pytest.mark.parametrize('reverse', [False, True])
def test_variable_shards_merge_without_duplicate_times(tmp_path, reverse):
    paths = write_shards(tmp_path, [shard('prmsl', 100000.), shard('u10', 0.), shard('v10', 3.)])
    with DatasetResources() as resources:
        ds = load(paths[::-1] if reverse else paths, ['prmsl', 'u10', 'v10'], resources=resources)
        np.testing.assert_array_equal(ds.time, TIMES)
        assert set(ds.data_vars) == {'prmsl', 'u10', 'v10'}
        for name, value in [('prmsl', 100000.), ('u10', 0.), ('v10', 3.)]:
            assert hasattr(ds[name].data, 'dask')
            np.testing.assert_array_equal(ds[name], np.full((2, 3, 3), value))
        assert ds.forecast_reference_time.values == REFERENCE


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'grid', 'clock', 'cycle', 'depth', 'mixed'])
def test_variable_shards_reject_unsafe_assembly(tmp_path, problem):
    a, b = shard('prmsl', 100000.), shard('u10', 1.)
    names = ['prmsl', 'u10']
    if problem == 'missing':
        names.append('v10')
    elif problem == 'duplicate':
        b['prmsl'] = b.u10
    elif problem == 'grid':
        b = b.assign_coords(longitude=b.longitude + .005)
    elif problem in {'clock', 'mixed'}:
        b = b.assign_coords(valid_time=TIMES + np.timedelta64(1, 'h'))
    elif problem == 'cycle':
        b = b.assign_coords(time=b.time + np.timedelta64(1, 'h'))
    elif problem == 'depth':
        a = a.assign_coords(deptht=[1., 2.])
        b = b.assign_coords(deptht=[1., 3.])
    paths = write_shards(tmp_path, [a, b])
    with pytest.raises(ValueError, match='missing|provider|coordinate|clock|time|depth|grid'):
        load(paths, names)


def test_arome_reference_time_survives_normalization():
    from frameit.io.netcdf_utils import normalize_netcdf_time

    ds = shard('prmsl', 1.)
    ds.prmsl.encoding['coordinates'] = 'time valid_time'
    result = normalize_netcdf_time(ds, SimpleNamespace(name_time_dim='valid_time', atm_model='AROME'))
    np.testing.assert_array_equal(result.time, TIMES)
    assert result.forecast_reference_time.values == REFERENCE
    assert result.prmsl.encoding['coordinates'] == 'forecast_reference_time time'
    assert ds.time.ndim == 0  # normalization must not mutate its input


@pytest.mark.parametrize('collision', ['unidentified', 'conflicting', 'vector'])
def test_arome_reference_time_rejects_ambiguous_collisions(collision):
    from frameit.io.netcdf_utils import normalize_netcdf_time

    ds = shard('prmsl', 1.)
    if collision == 'unidentified':
        ds.time.attrs.clear()
    elif collision == 'conflicting':
        ds = ds.assign_coords(forecast_reference_time=REFERENCE + np.timedelta64(1, 'h'))
    else:
        ds = ds.drop_vars('time').assign_coords(time=('valid_time', TIMES))
    with pytest.raises(ValueError, match='time|clock|forecast'):
        normalize_netcdf_time(ds, SimpleNamespace(name_time_dim='valid_time', atm_model='AROME'))


def test_time_series_requires_field_at_each_selected_time(tmp_path):
    a = shard('prmsl', 1., forecast=False).isel(valid_time=[0])
    b = shard('u10', 2., forecast=False).isel(valid_time=[1])
    paths = write_shards(tmp_path, [a, b])
    with pytest.raises(ValueError, match='missing|prmsl'):
        concat_nc2ds_by_vert_coord(paths, {'surface': {'variables': ['prmsl']}}, {},
                                  concat_dimension='valid_time')
    with pytest.raises(ValueError, match='missing|prmsl'):
        concat_nc2ds(paths, ['prmsl'], concat_dimension='valid_time')


def test_time_series_expands_changing_timeless_snapshots(tmp_path):
    datasets = []
    for index, value in enumerate([4., 9.]):
        ds = shard('prmsl', value, forecast=False).isel(valid_time=index, drop=True)
        datasets.append(ds.assign_coords(time=TIMES[index]))
    paths = write_shards(tmp_path, datasets)
    groups, _ = concat_nc2ds_by_vert_coord(paths, {'surface': {'variables': ['prmsl']}}, {})
    try:
        np.testing.assert_array_equal(groups['surface'].prmsl[:, 0, 0], [4., 9.])
    finally:
        groups['surface'].close()


@pytest.mark.parametrize('policy, expected', [('first', 4.), ('last', 9.)])
def test_time_series_retains_declared_duplicate_precedence(tmp_path, policy, expected):
    paths = write_shards(tmp_path, [shard('prmsl', value, forecast=False).isel(valid_time=[0])
                                    for value in (4., 9.)])
    groups, _ = concat_nc2ds_by_vert_coord(
        paths, {'surface': {'variables': ['prmsl']}}, {}, concat_dimension='valid_time',
        duplicate_time_policy=policy)
    try:
        assert groups['surface'].sizes['time'] == 1
        np.testing.assert_array_equal(groups['surface'].prmsl, np.full((1, 3, 3), expected))
    finally:
        groups['surface'].close()


@pytest.mark.parametrize('fail', [False, True])
def test_variable_shard_original_handles_close(tmp_path, monkeypatch, fail):
    paths = write_shards(tmp_path, [shard('prmsl', 1.), shard('u10', 2.)])
    opened, closed = [], []
    original = xr.open_dataset

    def tracked(*args, **kwargs):
        ds = original(*args, **kwargs)
        close = ds._close
        token = len(opened)
        opened.append(token)

        def closing():
            closed.append(token)
            close()

        ds.set_close(closing)
        return ds

    monkeypatch.setattr(xr, 'open_dataset', tracked)
    if fail:
        with pytest.raises(ValueError):
            load(paths, ['prmsl', 'absent'])
    else:
        result = load(paths, ['prmsl', 'u10'])
        assert set(closed) != set(opened)
        result.close()
    assert set(closed) == set(opened)


def test_variable_shards_selected_only_payload_stays_lazy(tmp_path):
    from dask.callbacks import Callback

    ds = shard('prmsl', 1.)
    ds['unrequested'] = ds.prmsl * 5
    paths = write_shards(tmp_path, [ds, shard('u10', 2.)])
    tasks = []
    with Callback(pretask=lambda key, *args: tasks.append(str(key))):
        result = concat_nc2ds(paths, ['prmsl', 'u10'], concat_dimension='valid_time', file_layout='variables')
    try:
        assert not any(name in task for name in ('prmsl', 'u10', 'unrequested') for task in tasks)
        assert 'unrequested' not in result
        assert hasattr(result.prmsl.data, 'dask')
    finally:
        result.close()


def configuration(tmp_path, paths, *, coupled=False):
    from frameit.core.settings_class import SimulationConfig

    source = {'model': 'arome', 'format': 'netcdf', 'files': list(map(str, paths)),
              'wind_pairs': [{'u': 'u10', 'v': 'v10', 'basis': 'earth'}],
              'variables': {'2d': ['prmsl', 'u10']},
              'transforms': [{'fields': ['u10'], 'sampling': 'native', 'basis': 'earth'}]}
    raw = {'schema_version': 3, 'sources': {'atmosphere': source},
           'region': {'center': {'latitude': -19.99, 'longitude': 60.01}},
           'output': {'directory': str(tmp_path / 'out'), 'overwrite': False}}
    if coupled:
        raw['sources']['surface'] = source
    return SimulationConfig.from_mapping_with_model_preset(raw)


def test_variable_shards_preflight_companion_inventory_and_replay(tmp_path):
    from frameit.core.configuration import resolved_configuration
    from frameit.core.coupled import bind_sources

    paths = write_shards(tmp_path, [shard('prmsl', 100000.), shard('u10', 0.), shard('v10', 3.)])
    conf = configuration(tmp_path, paths)
    source = bind_sources(conf)[0]['sources']['atmosphere']
    assert len(source['files']) == 3
    for path in source['files']:
        records = [record for record in source['records'] if record['locator']['path'] == path]
        assert sorted({str(record['time']) for record in records}) == [str(t) for t in TIMES]
        assert sorted({str(record['cycle']) for record in records}) == [str(REFERENCE)]
    replay = type(conf).from_mapping_with_model_preset(resolved_configuration(conf))
    assert replay.sources == conf.sources
    assert 'file_layout' not in replay.sources['atmosphere']['reader']
    coupled = configuration(tmp_path, paths, coupled=True)
    assert all(source['files'] == list(map(str, paths)) for source in coupled.sources.values())
    assert all('file_layout' not in source['reader'] for source in coupled.sources.values())


@pytest.mark.parametrize('value', ['mixed', 1, None])
def test_netcdf_layout_rejects_invalid_configuration(tmp_path, value):
    from frameit.core.configuration import resolve_schema

    with pytest.raises(ValueError, match='file_layout'):
        resolve_schema({'schema_version': 3, 'sources': {'atmosphere': {
            'model': 'arome', 'files': '*.nc', 'reader': {'file_layout': value}}}})


def test_variable_shard_wind_companion_can_live_in_another_file(tmp_path):
    from frameit.core.coupled import bind_sources
    from frameit.core.runner import FrameitRunner

    paths = write_shards(tmp_path, [shard('prmsl', 100000.), shard('u10', 0.), shard('v10', 3.)])
    conf = configuration(tmp_path, paths)
    raw = conf.yaml_config
    raw['sources']['atmosphere']['variables'] = {'2d': ['u10']}
    conf = type(conf).from_mapping_with_model_preset(raw)
    with FrameitRunner(conf) as runner:
        bind_sources(conf, resources=runner.resources)
        groups, _, _ = runner.load_dataset()
        result, = groups.values()
        np.testing.assert_array_equal(result.u10, np.zeros((2, 3, 3)))
        assert result.u10.attrs['standard_name'] == 'eastward_wind'
        assert 'v10' not in result


@pytest.mark.parametrize('problem', [None, 'shift', 'missing'])
def test_variable_shards_validate_repeated_curvilinear_geography(tmp_path, problem):
    datasets = []
    for name in ['temperature', 'salinity']:
        ds = xr.Dataset({name: (('time', 'y', 'x'), np.ones((2, 3, 3)))},
                        coords={'time': TIMES, 'y': [0, 1, 2], 'x': [0, 1, 2]})
        ds['nav_lat'] = (('y', 'x'), np.broadcast_to([-20., -19.99, -19.98], (3, 3)),
                         {'standard_name': 'latitude', 'units': 'degrees_north'})
        ds['nav_lon'] = (('y', 'x'), np.broadcast_to([60., 60.01, 60.02], (3, 3)),
                         {'standard_name': 'longitude', 'units': 'degrees_east'})
        datasets.append(ds)
    if problem == 'shift':
        datasets[1].nav_lon.values = datasets[1].nav_lon.values + .005
    elif problem == 'missing':
        datasets[1] = datasets[1].drop_vars('nav_lon')
    paths = write_shards(tmp_path, datasets)
    if problem:
        with pytest.raises(ValueError, match='coordinate|geography'):
            concat_nc2ds(paths, ['temperature', 'salinity', 'nav_lat', 'nav_lon'], file_layout='variables')
    else:
        ds = concat_nc2ds(paths, ['temperature', 'salinity', 'nav_lat', 'nav_lon'], file_layout='variables')
        try:
            np.testing.assert_array_equal(ds.nav_lon[0], [60., 60.01, 60.02])
        finally:
            ds.close()


def test_variable_shards_follow_auxiliary_dependencies_across_files(tmp_path):
    first = shard('prmsl', 1.)
    first.prmsl.attrs['ancillary_variables'] = 'quality'
    second = shard('u10', 2.)
    second['quality'] = (('latitude', 'longitude'), np.arange(9).reshape(3, 3))
    paths = write_shards(tmp_path, [first, second])
    ds = load(paths, ['prmsl'])
    try:
        np.testing.assert_array_equal(ds.quality, np.arange(9).reshape(3, 3))
        assert 'u10' not in ds
    finally:
        ds.close()


def test_variable_shards_sample_clock_ignores_unrelated_scalar_coordinates(tmp_path):
    pressure = shard('prmsl', 100000.).assign_coords(meanSea=0.)
    wind = shard('u10', 3.).assign_coords(heightAboveGround=10.)
    paths = write_shards(tmp_path, [pressure, wind])
    ds = load(paths, ['prmsl', 'u10'])
    try:
        np.testing.assert_array_equal(ds.time, TIMES)
        assert ds.meanSea == 0.
        assert ds.heightAboveGround == 10.
    finally:
        ds.close()


@pytest.mark.parametrize('conflict', [False, True])
def test_variable_shards_preserve_and_validate_interval_bounds(tmp_path, conflict):
    datasets = [shard('prmsl', 1.), shard('u10', 2.)]
    bounds = np.array([['2024-12-10T23:30', '2024-12-11T00:30'],
                       ['2024-12-11T05:30', '2024-12-11T06:30']], dtype='datetime64[ns]')
    for ds in datasets:
        ds['valid_time_bounds'] = (('valid_time', 'nv'), bounds.copy())
        ds.valid_time.encoding['units'] = 'seconds since 2024-12-11'
        ds.valid_time_bounds.encoding['units'] = 'seconds since 2024-12-11'
        ds.valid_time.attrs['bounds'] = 'valid_time_bounds'
        for name in ['prmsl', 'u10']:
            if name in ds:
                ds[name].attrs['cell_methods'] = 'valid_time: mean (interval: 240 s)'
    if conflict:
        datasets[1]['valid_time_bounds'] = datasets[1].valid_time_bounds + np.timedelta64(1, 'm')
    paths = write_shards(tmp_path, datasets)
    if conflict:
        with pytest.raises(ValueError, match='coordinate|auxiliary'):
            load(paths, ['prmsl', 'u10'])
    else:
        ds = load(paths, ['prmsl', 'u10'])
        try:
            assert ds.time.attrs['bounds'] == 'valid_time_bounds'
            np.testing.assert_array_equal(ds.valid_time_bounds, bounds)
            assert ds.prmsl.attrs['cell_methods'] == 'time: mean (interval: 240 s)'
        finally:
            ds.close()


def track_netcdf_opens(monkeypatch):
    opened, closed = [], []
    original = xr.open_dataset

    def tracked(*args, **kwargs):
        ds = original(*args, **kwargs)
        close = ds._close
        token = len(opened)
        opened.append(args[0])

        def closing():
            closed.append(token)
            close()

        ds.set_close(closing)
        return ds

    monkeypatch.setattr(xr, 'open_dataset', tracked)
    return opened, closed


@pytest.mark.parametrize('engine', ['h5netcdf', 'netcdf4'])
@pytest.mark.parametrize('model', ['mesonh', 'arome', 'nemo', 'croco'])
def test_runner_reuses_netcdf_metadata_without_reading_fields(tmp_path, monkeypatch, engine, model):
    from xarray.backends.h5netcdf_ import H5NetCDFArrayWrapper
    from xarray.backends.netCDF4_ import NetCDF4ArrayWrapper

    from frameit.core.coupled import bind_sources
    from frameit.core.runner import FrameitRunner
    from frameit.core.settings_class import SimulationConfig

    from .test_configuration_v2_1 import dataset, document
    from .test_croco_netcdf import croco_scene
    from .test_nemo_netcdf import nemo_scene

    paths = [tmp_path / f'part{i}.nc' for i in range(2)]
    if model == 'mesonh':
        scene = dataset(tmp_path)
        raw = document(tmp_path)
        raw['sources']['atmosphere']['variables'] = {'2d': ['MSLP']}
        field, clock = 'MSLP', 'time'
    elif model == 'arome':
        scene = shard('prmsl', 100000.)
        raw = configuration(tmp_path, paths).yaml_config
        raw['sources']['atmosphere']['variables'] = {'2d': ['prmsl']}
        raw['sources']['atmosphere']['transforms'] = []
        field, clock = 'prmsl', 'valid_time'
    elif model == 'nemo':
        scene = nemo_scene().isel(time_counter=slice(0, 2))
        raw = {'schema_version': 3, 'sources': {'ocean': {
            'model': 'nemo', 'variables': {'3d': ['votemper']}}}}
        field, clock = 'votemper', 'time_counter'
    else:
        scene = croco_scene()
        raw = {'schema_version': 3, 'sources': {'ocean': {
            'model': 'croco', 'variables': {'3d': ['temp']}}}}
        field, clock = 'temp', 'time'
    scene['unrequested'] = xr.ones_like(scene[field])
    for i, path in enumerate(paths):
        part = scene.isel({clock: [i]})
        chunks = tuple(min(2, n) for n in part[field].shape)
        part.to_netcdf(path, engine='h5netcdf', encoding={field: {'chunksizes': chunks}})
    source, = raw['sources'].values()
    source['files'] = list(map(str, paths))
    source['reader'] = {'engine': engine, 'chunks': {dim: 2 for dim in scene[field].dims}}
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    opened, closed = track_netcdf_opens(monkeypatch)
    wrapper = H5NetCDFArrayWrapper if engine == 'h5netcdf' else NetCDF4ArrayWrapper
    original_read = wrapper._getitem

    def no_physical_read(array, key):
        assert array.variable_name not in {field, 'unrequested'}
        return original_read(array, key)

    with FrameitRunner(conf) as runner:
        with monkeypatch.context() as guarded:
            guarded.setattr(wrapper, '_getitem', no_physical_read)
            bind_sources(conf, resources=runner.resources)
            groups, _, files = runner.load_dataset()
        assert Counter(opened) == Counter(paths)
        assert files == paths
        result, = [ds[field] for ds in groups.values() if field in ds]
        assert hasattr(result.data, 'dask')
        assert all(n <= 2 for chunks in result.chunks for n in chunks)
        np.testing.assert_array_equal(result, scene[field])
        assert all('unrequested' not in ds for ds in groups.values())
        assert not closed
    assert set(closed) == set(range(len(opened)))


def test_resource_close_attempts_every_callback_and_surfaces_failure():
    closed = []
    resources = DatasetResources()
    for index in range(3):
        data = xr.Dataset()

        def close(index=index):
            closed.append(index)
            if index == 1:
                raise OSError("registered close failed")

        data.set_close(close)
        resources.add(data)
    with pytest.raises(OSError, match="registered close failed"):
        resources.close()
    assert closed == [2, 1, 0]


@pytest.mark.parametrize("context_manager", [False, True])
def test_failed_loading_retains_primary_error_and_reports_cleanup(context_manager):
    from frameit.io.loader import managed_loading

    data = xr.Dataset()

    def close():
        raise OSError("registered close failed")

    data.set_close(close)

    @managed_loading
    def load(*, resources):
        resources.add(data)
        raise ValueError("primary load failure")

    with pytest.raises(ValueError, match="primary load failure") as caught:
        if context_manager:
            with DatasetResources() as resources:
                resources.add(data)
                raise ValueError("primary load failure")
        else:
            load()
    assert any("registered close failed" in note for note in getattr(caught.value, "__notes__", []))


@pytest.mark.parametrize("body_failure", [False, True])
def test_runner_context_preserves_primary_error_during_failed_cleanup(tmp_path, body_failure):
    from frameit.core.runner import FrameitRunner

    data = xr.Dataset()
    closed = []

    def close():
        closed.append(True)
        raise OSError("secondary backend close failure")

    data.set_close(close)
    conf = configuration(tmp_path, [tmp_path / "unused.nc"])
    error = ValueError if body_failure else OSError
    message = "primary processing" if body_failure else "secondary"
    with pytest.raises(error, match=message) as caught:
        with FrameitRunner(conf) as runner:
            runner.resources.add(data)
            if body_failure:
                raise ValueError("primary processing failure")
    assert closed == [True]
    if body_failure:
        assert any("secondary backend close failure" in note for note in caught.value.__notes__)
    assert not conf.output_dir.exists()


def test_netcdf_reuse_expires_on_close(tmp_path, monkeypatch):
    path = write_shards(tmp_path, [shard('prmsl', 1.)])[0]
    opened, closed = track_netcdf_opens(monkeypatch)
    with DatasetResources() as resources:
        for _ in range(2):
            ds = concat_nc2ds([path], ['prmsl'], resources=resources)
            assert float(ds.prmsl[0, 0, 0]) == 1.
        assert len(opened) == 1
        resources.close()
        assert set(closed) == {0}
        shard('prmsl', 9.).to_netcdf(path)
        ds = concat_nc2ds([path], ['prmsl'], resources=resources)
        assert float(ds.prmsl[0, 0, 0]) == 9.
        assert len(opened) == 2
    assert set(closed) == {0, 1}


def test_netcdf_reuse_respects_engine_and_chunks(tmp_path, monkeypatch):
    paths = write_shards(tmp_path, [shard('prmsl', 1.)])
    opened, _ = track_netcdf_opens(monkeypatch)
    with DatasetResources() as resources:
        for chunks in ({'latitude': 1, 'longitude': 2}, {'longitude': 2, 'latitude': 1}):
            first = concat_nc2ds(paths, ['prmsl'], resources=resources, chunks=chunks)
        second = concat_nc2ds(paths, ['prmsl'], resources=resources, chunks={'latitude': 3})
        other_engine = concat_nc2ds(paths, ['prmsl'], resources=resources,
                                   chunks={'latitude': 3}, engine='netcdf4')
        assert len(opened) == 3
        assert first.prmsl.chunksizes['latitude'] == (1, 1, 1)
        assert second.prmsl.chunksizes['latitude'] == (3,)
        xr.testing.assert_equal(second, other_engine)


def test_netcdf_failed_load_closes_and_allows_retry(tmp_path, monkeypatch):
    paths = write_shards(tmp_path, [shard('prmsl', 1.)])
    opened, closed = track_netcdf_opens(monkeypatch)
    with DatasetResources() as resources:
        with pytest.raises(ValueError, match='missing'):
            concat_nc2ds(paths, ['missing'], resources=resources)
        assert closed == [0]
        result = concat_nc2ds(paths, ['prmsl'], resources=resources)
        assert float(result.prmsl[0, 0, 0]) == 1.
        assert len(opened) == 2
    assert set(closed) == {0, 1}


def test_standalone_preflight_closes_netcdf(tmp_path, monkeypatch):
    from frameit.core.preflight import preflight

    paths = write_shards(tmp_path, [shard('prmsl', 100000.), shard('u10', 0.), shard('v10', 3.)])
    conf = configuration(tmp_path, paths)
    opened, closed = track_netcdf_opens(monkeypatch)
    assert len(preflight(conf)['sources']['atmosphere']['selected_times']) == 2
    assert Counter(opened) == Counter(paths)
    assert set(closed) == set(range(len(opened)))


@pytest.mark.parametrize('representation', ['native', 'mass_earth'])
def test_runner_only_prepares_selected_cartesian_branch(tmp_path, representation):
    from frameit.core.coupled import bind_sources
    from frameit.core.runner import FrameitRunner
    from frameit.core.settings_class import SimulationConfig
    from frameit.processing.wind_collocation import collocate_mnh_component

    from .test_configuration_v2_1 import document
    from .test_wind_collocation import native

    source = native()
    path = tmp_path / 'native.nc'
    source.to_netcdf(path, engine='h5netcdf')
    raw = document(tmp_path, region={}, products={'model_grid': True})
    raw['sources']['atmosphere'].update(
        files=[str(path)], wind_pairs=[{'u': 'UT', 'v': 'VT', 'basis': 'earth'}],
        variables={'3d': ['UT', 'VT', 'WT']})
    if representation == 'mass_earth':
        raw['sources']['atmosphere']['transforms'] = [
            {'fields': ['UT', 'VT'], 'sampling': 'mass', 'basis': 'earth'}]
    conf = SimulationConfig.from_mapping_with_model_preset(raw)
    with FrameitRunner(conf) as runner:
        bind_sources(conf, resources=runner.resources)
        groups, _, _ = runner.load_dataset()
        wind, = [ds for ds in groups.values() if 'UT' in ds]
        vertical, = [ds for ds in groups.values() if 'WT' in ds]
        # Explicit downstream collocation does not replace native exports or add hidden W.
        u = collocate_mnh_component(wind.UT, source, conf)
        w = collocate_mnh_component(vertical.WT, source, conf, vertical=True)
        np.testing.assert_array_equal(u[0, :, 1], [[0., 2., 4.]] * 3)
        np.testing.assert_array_equal(w[0, :, 0, 0], [.5, 2.5, 6.])
        np.testing.assert_array_equal(vertical.WT, source.WT)
        assert all('_frameit_mass_w' not in ds for ds in groups.values())
        if representation == 'native':
            np.testing.assert_array_equal(wind.UT, source.UT)
        else:
            np.testing.assert_array_equal(wind.UT, u)


@pytest.mark.parametrize("engine", ["h5netcdf", "netcdf4", "scipy"])
def test_v3_inventory_retained_multitime_file_reads_only_coordinates_and_closes(
    tmp_path, monkeypatch, engine,
):
    from frameit.core.preflight import preflight

    from .test_inspect_metadata import guard_netcdf_payloads, v3_config, v3_scene

    scene = v3_scene(names=("u", "unrequested"))
    path = tmp_path / "multi.nc"
    scene.to_netcdf(path, engine=engine)
    opened, closed = track_netcdf_opens(monkeypatch)
    reads = guard_netcdf_payloads(monkeypatch, {"u", "unrequested"})
    conf = v3_config(tmp_path, [path], names=("u",), reader={"engine": engine},
                     time={"values": ["2026-01-01T01:00:00", "2026-01-01T03:00:00"]})
    source = preflight(conf, check_output=False)["sources"]["weather"]
    assert [(r["name"], r["locator"]["indexers"]) for r in source["records"]] == [
        ("u", {"time": 1}), ("u", {"time": 3}),
    ]
    assert len(opened) == 1 and closed == [0]
    assert reads and {n for n, _ in reads} <= {"x", "y", "time", "latitude", "longitude"}


@pytest.mark.parametrize("names", [("temperature",), ("other",), ("other", "temperature"),
                                 ("temperature", "other")])
def test_v3_native_grid_ids_precede_field_filtering(tmp_path, monkeypatch, names):
    from frameit.core.preflight import preflight

    from .test_inspect_metadata import guard_netcdf_payloads, v3_config, v3_scene

    scene = v3_scene()
    scene["other"] = (("time", "depth", "y", "x_u"), np.ones((4, 2, 2, 4)), {"units": "K"})
    scene = scene.assign_coords(
        x_u=[-.5, .5, 1.5, 2.5],
        depth=("depth", [1., 3.], {"units": "m", "positive": "down", "axis": "Z"}))
    path = tmp_path / "grids.nc"
    scene.to_netcdf(path)
    guard_netcdf_payloads(monkeypatch, {"temperature", "other"})
    baseline = preflight(v3_config(tmp_path, [path], names=("temperature",)),
                         check_output=False)["sources"]["weather"]
    variables = {category: [name] for category, name in (
        ("2d", "temperature"), ("3d", "other")) if name in names}
    actual = preflight(v3_config(tmp_path, [path], names=names, variables=variables),
                       check_output=False)["sources"]["weather"]
    assert len(actual["native_grids"]) == 2
    assert actual["native_grids"].keys() == baseline["native_grids"].keys()
    mapping = {f["name"]: f["grid_id"] for f in actual["fields"].values()}
    assert mapping["temperature"] != mapping["other"]
    assert mapping == {f["name"]: f["grid_id"] for f in baseline["fields"].values()}
    for record in actual["records"]:
        assert record["grid_id"] == mapping[record["name"]]


@pytest.mark.parametrize("moving", [False, True])
def test_v3_grid_identity_separates_sample_clocks_from_moving_geography(
    tmp_path, monkeypatch, moving,
):
    from frameit.core.preflight import preflight

    from .test_inspect_metadata import guard_netcdf_payloads, v3_config, v3_scene

    scene = v3_scene()
    if moving:
        lat = np.broadcast_to([[-20.], [-19.99]], (2, 3))
        lon = np.broadcast_to([[60., 60.01, 60.02]], (2, 3))
        scene = scene.assign_coords(
            latitude=(("time", "y", "x"), lat[None, ...] + np.arange(4)[:, None, None] * .01,
                      {"units": "degrees_north", "standard_name": "latitude"}),
            longitude=(("time", "y", "x"), np.broadcast_to(lon, (4, 2, 3)),
                       {"units": "degrees_east", "standard_name": "longitude"}))
    values = scene.time.values
    scene = scene.rename(time="sample").drop_vars("sample").assign_coords(
        valid_time=("sample", values, {"standard_name": "time"}),
        forecast_reference_time=np.datetime64("2025-12-31"))
    paths = []
    for i, positions in enumerate(([0], [1, 2, 3])):
        path = tmp_path / f"part{i}.nc"
        scene.isel(sample=positions).to_netcdf(path)
        paths.append(path)
    guard_netcdf_payloads(monkeypatch, {"temperature"})
    source = preflight(v3_config(tmp_path, paths), check_output=False)["sources"]["weather"]
    assert len(source["native_grids"]) == (2 if moving else 1)
    assert len(source["fields"]) == 1
    field = next(iter(source["fields"].values()))
    assert set(field["grid_ids"]) == set(source["native_grids"])
    assert len({r["field_id"] for r in source["records"]}) == 1
    for grid in source["native_grids"].values():
        assert not {"valid_time", "forecast_reference_time"} & grid["coordinates"].keys()


@pytest.mark.parametrize("static", [True, False])
def test_v3_moving_grid_keeps_coordinate_indexers_separate_from_payload(
    tmp_path, monkeypatch, static,
):
    from frameit.core.preflight import preflight

    from .test_inspect_metadata import guard_netcdf_payloads, v3_config, v3_scene

    scene = v3_scene()
    latitude = np.broadcast_to([[-20.], [-19.99]], (2, 3))
    scene = scene.assign_coords(
        latitude=(("time", "y", "x"), latitude[None] + np.arange(4)[:, None, None] * .01,
                  {"standard_name": "latitude", "units": "degrees_north"}))
    if static:
        scene["temperature"] = scene.temperature.isel(time=0, drop=True)
    times = scene.time.values
    scene = scene.rename(time="sample").drop_vars("sample").assign_coords(
        valid_time=("sample", times, {"standard_name": "time"}),
        forecast_reference_time=np.datetime64("2025-12-31"))
    path = tmp_path / "moving.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    guard_netcdf_payloads(monkeypatch, {"temperature"})
    source = preflight(v3_config(tmp_path, [path], time={"values": [
        "2026-01-01T01:00:00", "2026-01-01T03:00:00",
    ]}), check_output=False)["sources"]["weather"]
    assert len(source["records"]) == 2
    for record, position in zip(source["records"], (1, 3), strict=True):
        assert record["time"] == np.datetime64(f"2026-01-01T0{position}:00:00")
        assert record["clock"] == "valid_time"
        assert record["locator"]["coordinate_indexers"] == {"sample": position}
        assert record["locator"]["indexers"] == ({} if static else {"sample": position})
        grid = source["native_grids"][record["grid_id"]]
        geography = grid["coordinates"]["latitude"]
        assert geography["dimensions"] == ["sample", "y", "x"]
        np.testing.assert_array_equal(geography["values"][position], latitude + position * .01)
        assert source["fields"][record["field_id"]]["time_varying"] is not static


@pytest.mark.parametrize("change", ["identical", "labels", "bounds", "units"])
def test_v3_cf_auxiliary_pressure_and_bounds_define_the_owning_grid(tmp_path, monkeypatch, change):
    from frameit.core.preflight import preflight

    from .test_inspect_metadata import guard_netcdf_payloads, v3_config, v3_scene

    shape = (4, 2, 2, 3)
    scene = v3_scene()
    scene["temperature"] = (("time", "level", "y", "x"), np.ones(shape), {
        "units": "K", "ancillary_variables": "quality"})
    scene = scene.assign_coords(
        level=[0, 1],
        pressure=("level", [850., 700.], {
            "standard_name": "air_pressure", "axis": "Z", "units": "hPa",
            "bounds": "pressure_bounds"}),
        quality=(("time", "level", "y", "x"), np.zeros(shape), {"flag_values": [0, 1]}))
    scene["pressure_bounds"] = (("level", "nv"), [[900., 800.], [750., 650.]], {"units": "hPa"})
    altered = scene.copy(deep=True)
    if change == "labels":
        altered.pressure.data = np.array([850., 600.])
    elif change == "bounds":
        altered.pressure_bounds.data = np.array([[910., 800.], [750., 640.]])
    elif change == "units":
        altered.pressure.attrs["units"] = "Pa"
        altered.pressure_bounds.attrs["units"] = "Pa"
        altered.pressure.data *= 100
        altered.pressure_bounds.data *= 100
    paths = [tmp_path / "base.nc", tmp_path / "altered.nc"]
    for data, path in zip((scene, altered), paths, strict=True):
        data.to_netcdf(path, engine="h5netcdf")
    guard_netcdf_payloads(monkeypatch, {"temperature", "quality"})
    ids = []
    for data, path in zip((scene, altered), paths, strict=True):
        source = preflight(v3_config(
            tmp_path, [path], variables={"3d": ["temperature"]},
            time={"values": ["2026-01-01T01:00:00", "2026-01-01T03:00:00"]}),
            check_output=False)["sources"]["weather"]
        record = next(r for r in source["records"] if r["name"] == "temperature")
        grid = source["native_grids"][record["grid_id"]]
        for name in ("pressure", "pressure_bounds"):
            coordinate = grid["coordinates"][name]
            assert coordinate["role"] == "coordinate_metadata"
            assert coordinate["dimensions"] == list(data[name].dims)
            np.testing.assert_array_equal(coordinate["values"], data[name].values)
            providers = grid["coordinate_providers"][name]
            assert len(providers) == 1
            assert providers[0]["path"] == str(path) and providers[0]["variable"] == name
            assert [s["coordinate_indexers"] for s in providers[0]["samples"]] == [
                {"time": 1}, {"time": 3}]
        assert grid["coordinates"]["pressure"]["attributes"]["units"] == data.pressure.units
        assert "quality" not in grid["coordinates"]
        assert not any(f["name"] == "pressure" and f["role"] == "array"
                       for f in source["fields"].values())
        ids.append(record["grid_id"])
    assert (ids[0] == ids[1]) is (change == "identical")


@pytest.mark.parametrize("geometry", ["rectilinear", "curvilinear"])
def test_v3_geographic_bounds_keep_native_vertex_axes(tmp_path, monkeypatch, geometry):
    from frameit.core.preflight import preflight

    from .test_inspect_metadata import guard_netcdf_payloads, v3_config, v3_scene

    scene = v3_scene(hours=(0, 1))
    if geometry == "curvilinear":
        scene = scene.assign_coords(
            latitude=(("y", "x"), np.broadcast_to([[-20.], [-19.99]], (2, 3)),
                      {"standard_name": "latitude", "units": "degrees_north"}),
            longitude=(("y", "x"), np.broadcast_to([[60., 60.01, 60.02]], (2, 3)),
                       {"standard_name": "longitude", "units": "degrees_east"}))
    for name in ("latitude", "longitude"):
        coordinate = scene[name]
        if geometry == "curvilinear":
            offsets = ([-.005, -.005, .005, .005] if name == "latitude"
                       else [-.005, .005, .005, -.005])
        else:
            offsets = [-.005, .005]
        bounds = name + "_bounds"
        scene[bounds] = ((*coordinate.dims, "nv"), coordinate.values[..., None] + offsets,
                         {"units": coordinate.attrs["units"]})
        scene[name].attrs["bounds"] = bounds
    path = tmp_path / "geographic-bounds.nc"
    scene.to_netcdf(path, engine="h5netcdf")
    guard_netcdf_payloads(monkeypatch, {"temperature"})
    source = preflight(v3_config(tmp_path, [path], time={"values": ["2026-01-01T01:00:00"]}),
                       check_output=False)["sources"]["weather"]
    assert len(source["records"]) == 1
    grid = source["native_grids"][source["records"][0]["grid_id"]]
    for name in ("latitude_bounds", "longitude_bounds"):
        assert grid["coordinates"][name]["dimensions"] == list(scene[name].dims)
        np.testing.assert_array_equal(grid["coordinates"][name]["values"], scene[name].values)
        provider, = grid["coordinate_providers"][name]
        assert [sample["coordinate_indexers"] for sample in provider["samples"]] == [{"time": 1}]
