Native ocean NetCDF
===================

NEMO regional native scalars
----------------------------

``model: nemo`` admits the tested regional NetCDF family with ``nav_lat`` and
``nav_lon`` on its own ``(y, x)`` grid, decoded Gregorian ``time_counter``, and
native ``deptht/depthu/depthv/depthw`` coordinates. It is not qualification of
every NEMO release, arbitrary global/folded grids or companion mesh files.
The existing regional geometry limits still apply: at most 10% difference
between X/Y spacing and 20% within-axis variability. A spacing override cannot
bypass them. NetCDF is the base path; FA, GRIB, polar and Zarr dependencies are
not needed for native scalar extraction.

Use ``frameit init nemo`` for a fixed-box starting configuration and
``frameit inspect ./data --model nemo --format netcdf --pattern '*.nc'`` for
metadata inspection. Set actual paths, fields and geographical centres before
running. Fixed and prescribed centres are supported; atmospheric tracking
methods on an ocean reference source fail. A secondary ocean source uses its
own geographical lookup with the continuous centres from the reference source.

Complementary T-grid scalar files require ``input.netcdf.file_layout: variables``;
see :doc:`input_files`. Do not merge shifted U/V geography into a T-grid source
merely because dimensions have the same names/shapes. Instantiate only requested
native contexts. The current implementation preserves data meaning rather than
converting between similarly named quantities:

* potential temperature is not relabelled as in-situ or sea-surface temperature;
* practical salinity is not converted to absolute salinity;
* sigma-theta density anomaly is not relabelled as absolute density.

Native level value selection is **exact**, with no atmospheric matching tolerance;
index selection explicitly addresses stored positions. Retained depth labels,
units, positive direction, bounds and zero-based ``<depth>_source_native_index``
coordinates describe the native axis, not a newly diagnosed physical-depth
coordinate. Separate depth axes remain separate. Native ``x/y`` coordinates are
preserved; when absent, zero-based dimensionless source indices are supplied.
Cropped coordinates identify native source samples, not a new common ocean grid.

When both ``time_counter`` and ``time_centered`` are present, they and their
bounds must agree. The sample clock becomes canonical ``time`` while original
interval bounds and per-field ``cell_methods`` remain visible. An hourly bound
is not the same fact as an internal averaging annotation such as
``time: mean (interval: 240 s)``. Exact coupled time matching remains the default:
half-hour interval centres have no exact match to whole-hour atmosphere snapshots.
No shifting, nearest matching, filling, interpolation or mean-to-instantaneous
equivalence is implied.

Decoded fill values establish **field-specific missingness**, not an ocean mask,
wet fraction, angle or mesh metric. Valid zeros remain valid; no dataset-wide
sentinel replacement or coastal filling is applied. Unrequested physical fields
remain uncomputed. Exported NetCDF products reopen in ordinary readers without
FrameIt; format compatibility does not promise an unchanged downstream schema.

Verification uses compact synthetic time/depth/crop, independent source-window
and ordinary-reader checks. Passing these engineering tests is not scientific
qualification across all real regimes, nor human scientific sign-off. Native
ocean vectors and any analysed representation have separate requirements; do not
interpret scalar admission as evidence of qualified current rotation or stresses.
