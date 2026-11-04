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

    source = {'model': 'arome', 'input': {'format': 'netcdf', 'files': list(map(str, paths)),
                                        'wind_reference_frame': 'earth',
                                        'netcdf': {'file_layout': 'variables'}},
              'variables': {'surface': {'names': ['prmsl', 'u10']}}}
    raw = {'schema_version': 2, **source,
           'tracking': {'method': 'fixed_box', 'fixed_box': {'center': {'latitude': -19.99,
                                                                       'longitude': 60.01}}},
           'output': {'directory': str(tmp_path / 'out'), 'overwrite': False}}
    if coupled:
        raw['input'] = {'sources': {'atmosphere': source, 'other': source}}
        raw.pop('variables')
        raw['tracking']['source'] = 'atmosphere'
    return SimulationConfig.from_mapping_with_model_preset(raw)


def test_variable_shards_preflight_companion_inventory_and_replay(tmp_path):
    from frameit.core.configuration import resolved_configuration
    from frameit.core.coupled import _inventory
    from frameit.core.preflight import preflight

    paths = write_shards(tmp_path, [shard('prmsl', 100000.), shard('u10', 0.), shard('v10', 3.)])
    conf = configuration(tmp_path, paths)
    assert conf.netcdf_file_layout == 'variables'
    preflight(conf)
    inventory = _inventory(conf)
    assert len(inventory) == 3
    for entry in inventory:
        assert entry['times'] == [str(t) for t in TIMES]
        assert entry['reference_times'] == [str(REFERENCE)]
    replay = type(conf).from_mapping_with_model_preset(resolved_configuration(conf))
    assert replay.netcdf_file_layout == 'variables'
    coupled = configuration(tmp_path, paths, coupled=True)
    assert all(s['input']['netcdf']['file_layout'] == 'variables'
               for s in coupled.input_sources.values())


@pytest.mark.parametrize('value', ['mixed', 1, None])
def test_netcdf_layout_rejects_invalid_configuration(tmp_path, value):
    from frameit.core.configuration import resolve_schema

    with pytest.raises(ValueError, match='file_layout'):
        resolve_schema({'schema_version': 2, 'model': 'arome',
                        'input': {'pattern': '*.nc', 'netcdf': {'file_layout': value}}})


def test_variable_shard_wind_companion_can_live_in_another_file(tmp_path):
    paths = write_shards(tmp_path, [shard('prmsl', 100000.), shard('u10', 0.), shard('v10', 3.)])
    conf = configuration(tmp_path, paths)
    result = load(paths, ['u10'], wind_conf=conf)
    try:
        np.testing.assert_array_equal(result.u10, np.zeros((2, 3, 3)))
        assert result.u10.attrs['standard_name'] == 'eastward_wind'
    finally:
        result.close()


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

    from frameit.core.runner import FrameitRunner
    from frameit.core.settings_class import SimulationConfig

    from .test_configuration_v2 import dataset, document
    from .test_croco_netcdf import croco_document, croco_scene
    from .test_nemo_netcdf import nemo_document, nemo_scene

    paths = [tmp_path / f'part{i}.nc' for i in range(2)]
    if model == 'mesonh':
        scene = dataset(tmp_path)
        raw = document(tmp_path, variables={'surface': {'names': ['MSLP']}})
        field, group, clock = 'MSLP', 'surface', 'time'
    elif model == 'arome':
        scene = shard('prmsl', 100000.)
        raw = configuration(tmp_path, paths).yaml_config
        raw['variables'] = {'surface': {'names': ['prmsl']}}
        field, group, clock = 'prmsl', 'surface', 'valid_time'
    elif model == 'nemo':
        scene = nemo_scene().isel(time_counter=slice(0, 2))
        raw = nemo_document(tmp_path, paths, variables={
            'deptht': {'names': ['votemper'], 'levels': 'all'}})
        field, group, clock = 'votemper', 'deptht', 'time_counter'
    else:
        scene = croco_scene()
        raw = croco_document(tmp_path, paths, variables={
            's_rho': {'names': ['temp'], 'levels': 'all'}})
        field, group, clock = 'temp', 's_rho', 'time'
    scene['unrequested'] = xr.ones_like(scene[field])
    for i, path in enumerate(paths):
        part = scene.isel({clock: [i]})
        chunks = tuple(min(2, n) for n in part[field].shape)
        part.to_netcdf(path, engine='h5netcdf', encoding={field: {'chunksizes': chunks}})
    raw['input'].pop('directory', None)
    raw['input'].pop('pattern', None)
    raw['input']['files'] = list(map(str, paths))
    raw['input']['netcdf'] = {'engine': engine, 'file_layout': 'time_series'}
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
            groups, _, files = runner.load_dataset()
        assert Counter(opened) == Counter(paths)
        assert files == paths
        result = groups[group][field]
        assert hasattr(result.data, 'dask')
        assert all(n <= 2 for chunks in result.chunks for n in chunks)
        np.testing.assert_array_equal(result, scene[field])
        assert 'unrequested' not in groups[group]
        assert not closed
    assert set(closed) == set(range(len(opened)))


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
    assert preflight(conf)['track_time_count'] == 2
    assert Counter(opened) == Counter(paths)
    assert set(closed) == set(range(len(opened)))


@pytest.mark.parametrize('representation', ['native', 'mass_earth'])
def test_runner_only_prepares_selected_cartesian_branch(tmp_path, representation):
    from frameit.core.runner import FrameitRunner
    from frameit.core.settings_class import SimulationConfig

    from .test_configuration_v2 import document
    from .test_wind_collocation import native

    source = native()
    path = tmp_path / 'native.nc'
    source.to_netcdf(path, engine='h5netcdf')
    raw = document(tmp_path,
        input={'files': [str(path)], 'wind_pairs': [
            {'group': 'level', 'u': 'UT', 'v': 'VT', 'reference_frame': 'earth'}]},
        variables={'level': {'names': ['UT', 'VT'], 'levels': 'all'},
                   'level_w': {'names': ['WT'], 'levels': 'all'}},
        output={'directory': str(tmp_path / 'out'),
                'cartesian': {'horizontal_winds': representation}})
    with FrameitRunner(SimulationConfig.from_mapping_with_model_preset(raw)) as runner:
        groups, _, _ = runner.load_dataset()
        assert bool(runner._native_cartesian_groups) == (representation == 'native')
        np.testing.assert_array_equal(groups['level'].UT[0, :, 1], [[0., 2., 4.]] * 3)
        np.testing.assert_array_equal(groups['level_w']._frameit_mass_w[0, :, 0, 0], [.5, 2.5, 6.])
        if representation == 'native':
            np.testing.assert_array_equal(runner._native_cartesian_groups['level'].UT, source.UT)
            np.testing.assert_array_equal(runner._native_cartesian_groups['level_w'].WT, source.WT)
