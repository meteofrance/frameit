"""Lazy/eager equivalence, output ring chunks and changing per-level source masks."""

import numpy as np
import pytest
import xarray as xr

from frameit.processing.polar.polar_proj import polar_project
from frameit.testing.numerical.test_polar_contracts import polar_settings, source_scene


@pytest.mark.parametrize("chunks", [
    {"time": 1, "level": 1, "y_box": 2, "x_box": 3},
    {"time": 2, "level": 2, "y_box": -1, "x_box": -1},
    {"time": 1, "level": 2, "y_box": -1, "x_box": 2},
])
@pytest.mark.parametrize("dtype,tolerance", [("float64", 1e-12), ("float32", 1e-6)])
def test_lazy_eager_values_masks_and_output_chunks(chunks, dtype, tolerance):
    source = source_scene().expand_dims(level=[1, 2])
    source["q"] = source.q.astype(dtype)
    source.q[1, 0, 2, 3] = np.nan
    source.q[0, 1, 1, 2] = np.inf
    config = polar_settings(polar_missing_data_policy="renormalize", polar_profile=True,
                            polar_output_chunks={"time": 1, "level": 1, "rr": 2, "theta": 8})
    eager, _ = polar_project({"surface": source}, conf=config)
    lazy, report = polar_project({"surface": source.chunk(chunks)}, conf=config)
    result = lazy["surface"]
    assert hasattr(result.q.data, "__dask_graph__")
    assert report["regrid_performance"]["graph_tasks"] > 0
    assert report["regrid_performance"]["source_geometry_cache"]["hits"] > 0
    assert result.q.chunksizes["rr"] == (2, 1)
    assert result.q.chunksizes["theta"] == (8, 8)
    assert max(result.q.chunksizes["time"]) == 1
    assert max(result.q.chunksizes["level"]) == 1
    xr.testing.assert_allclose(result.compute(), eager["surface"], rtol=tolerance, atol=tolerance)
    np.testing.assert_array_equal(np.isnan(result.q.compute()), np.isnan(eager["surface"].q))


def test_default_angular_chunks_are_whole_rings_without_field_computation():
    from dask.callbacks import Callback

    source = source_scene().chunk({"time": 1, "y_box": 2, "x_box": 3})
    config = polar_settings(x_boxsize_km=200, y_boxsize_km=200, radial_resolution=3000)
    # Keep geography eager to isolate laziness of the physical fields.
    source = source.assign_coords(
        longitude=source.longitude.compute(), latitude=source.latitude.compute()
    )
    tasks = []
    with Callback(pretask=lambda key, *args: tasks.append(key)):
        result, report = polar_project({"surface": source}, conf=config)
    assert not tasks
    assert hasattr(result["surface"].q.data, "__dask_graph__")
    assert result["surface"].q.chunksizes["rr"] == (32, 3)
    assert result["surface"].q.chunksizes["theta"] == (16,)
    assert report["regrid_performance"]["graph_tasks"] is None


def test_unknown_output_dimension_is_rejected():
    with pytest.raises(ValueError, match="Unknown polar_output_chunks"):
        polar_project({"surface": source_scene()},
                      conf=polar_settings(polar_output_chunks={"not_a_dimension": 3}))
