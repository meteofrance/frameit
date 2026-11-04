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

For successive native NEMO files, selected field and coordinate scientific
metadata must remain consistent, including units, quantity identity, averaging
annotations and positive direction. Conflicting declarations fail in preflight
and loading; no automatic Celsius/Kelvin or other ocean quantity conversion is
introduced. Native clocks are checked before selecting variables, including
``time_centered`` stored as an auxiliary data variable rather than a coordinate.

Verification uses compact synthetic time/depth/crop, independent source-window
and ordinary-reader checks. Passing these engineering tests is not scientific
qualification across all real regimes, nor human scientific sign-off. Native
ocean components are supported only as the native copies described below; do not
interpret scalar admission as evidence of qualified current rotation or stresses.

Separate native components
--------------------------

Native ``vozocrtx``/``vomecrty`` on independent U/V grids and ``vovecrtz`` on
``depthw`` retain source values, geography, zeros, missingness, units and names.
Native barotropic and stress components can also be selected without loading
unrequested companions or interpreting their basis, sign or scaling. Separate
contexts preserve shifted native sampling even when every file uses ``x/y``.
``depthw`` is not relabelled as ``deptht`` merely because their lengths agree.

For any native component selection explicitly declare the existing legacy-named
selector ``output.cartesian.horizontal_winds: native``. Its name is retained for
configuration compatibility; it does not turn currents/stresses into winds.
The native ocean path never derives wind speed, radial/tangential winds or
atmospheric reference-frame metadata. The default ``mass_earth`` selection fails
for NEMO components rather than silently returning a different representation.
For W, retain ``output.cartesian.vertical_velocity: interfaces`` (the default):
it preserves the native ``depthw`` axis, not a diagnosed mass-level velocity.
An explicitly requested ``mass`` transformation fails.

Analysed NEMO components, including explicit polar component requests, remain
unsupported: the admitted files do not establish a qualified angle, mesh,
support and collocation contract. A wind declaration is not such evidence.
This does not block independent scalar copies or eligible scalar polar samples.
No current rotation, stress reconciliation, coastal filling, speed diagnostic or
track-motion subtraction is performed. Native copied samples are checked for
exact decoded numerical agreement; no conservation or all-regime validation is
claimed.

Coupled extraction and optional scalar targets
----------------------------------------------

``example/config_file/nemo_arome.yaml`` demonstrates separate T/U/V/W sources
with one fixed geographical centre. Its files and centres must be adapted to
the selected data. It explicitly selects ``input.time_alignment: preceding_hour``
as its pairing default, not a claim of mean/snapshot temporal equivalence.
A prescribed track uses
the same continuous centres at every source, with independent native index lookup.
``common`` records exact-time exclusions; ``strict`` also requires equal source
times and track coverage. A centre outside any selected source fails rather
than substituting an edge point or silently dropping that time.

Preceding-hour association (no interpolation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The additive ``preceding_hour`` policy requires named NetCDF sources with an
AROME tracking/reference source and at least one NEMO secondary source. Selected
AROME fields must explicitly declare instantaneous sampling (``GRIB_stepType:
instant`` or ``cell_methods: 'time: point'``); selected NEMO fields must declare
``time: mean`` and provide decoded one-hour bounds. Contradictory declarations,
invalid bounds and multiple distinct native samples for one requested interval
fail rather than selecting an arbitrary candidate. All participants must have
unique physical records. Repeated timestamps within a file or
overlapping providers of a selected physical field across files fail, even if
``duplicate_time_policy`` would normally keep one. Complementary variable shards
may repeat matching clock/bounds metadata. Additional AROME participants
still match reference timestamps exactly. The global default remains ``common``;
existing exact ``common`` and ``strict`` runs are unchanged.

At reference time T, the policy selects the unique native NEMO sample whose
averaging interval is exactly **[T-1 hour, T]**, using the preceding interval
convention (T-1 hour, T]. For example, an AROME snapshot at 06:00 is paired with
the NEMO mean over 05:00–06:00, typically labelled 05:30. It does not select the
following hour or compute an interpolated instantaneous ocean value. Native
values, zeros, field-local missing cells, depth axes and spatial grids are
unchanged. This is an explicit comparison convention, not reconstruction of an
instantaneous state, producer endorsement or general scientific validation.

If any source lacks a temporal partner, the entire reference-time pairing is
omitted for all sources with a warning. All omissions and selected source times,
intervals and offsets are recorded in ``time_alignment`` in run provenance and
status. Prescribed-track coverage first restricts the reference timeline and its
exclusions are recorded separately. No remaining pairings is an actionable error.
Malformed required metadata is an error, not an excuse to omit a pairing. This
policy never fills missing individual grid cells or substitutes another quantity.

Product ``time`` is the reference/coupling timestamp, also the end label of the
NEMO mean. Ocean ``source_time(time)`` preserves the original native sampling
labels and their calendar/bounds; ``time_centered`` and original bound arrays are
retained where supplied. ``source_time`` is reserved and must not already exist
in the ocean input. Both ``time`` and ``source_time`` reference the unchanged
averaging bounds, and fields retain ``cell_methods: time: mean``. Downstream
scripts needing native centre labels must use ``source_time`` rather than
assuming product ``time`` is a native centre. Ordinary NetCDF/Zarr readers can
interpret these coordinates without FrameIt. This explicit mode changes the
time-label contract; it does not change the values or enable temporal
interpolation, extrapolation, averaging of means or nearest-time fallback.

Optional spatial scalar targets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Eligible scalar sources can opt into the existing shared polar target. Target
time/radius/azimuth/geography and target identity agree exactly, while native
depths, source mean bounds, forecast identity and field-local support remain
different. Component requests remain gated as described above. Continuous
bilinear point sampling is not area-conservative or a physical-depth section.
Polar processing stays optional and is not enabled by the native example.

CROCO native history scalars
----------------------------

``model: croco`` admits the tested regional ``CROCO history file`` family with
decoded Gregorian ``time``, optional agreeing ``scrum_time``, native rho geography
``lat_rho/lon_rho`` on ``(eta_rho, xi_rho)`` and explicit consistent
``Vtransform=2`` declarations. Use ``frameit init croco`` or ``frameit inspect
./data --model croco --format netcdf --pattern '*.nc'``. Adapt the generated paths,
fields, native level indices and geographical centre to the data. Fixed and
prescribed centres are supported independently or in named-source exact-time runs.
This does not admit every CROCO release, restart/averaged products, other vertical
transforms or a producer-specific coupling convention. The NEMO-only
``preceding_hour`` profile does not apply to CROCO.

Native ``temp/salt`` are selected on ``s_rho``; ``zeta`` belongs to ``surface``.
Fields genuinely stored on ``s_w`` use a separate group. Do not infer the stored
location of ``w`` or substitute ``omega`` from their names. Fractional sigma values
are **dimensionless, not metres**; value selection is exact in both preflight and
loading. Sparse/reordered selections retain
``s_rho_source_native_index/s_w_source_native_index``. Native rho geography, source
axis labels and source dynamic-range metadata survive crops; the output is not
collocated with an atmospheric grid merely because array sizes agree.

Selected scientific definitions must agree across successive files, including
quantity/units, coordinate formula metadata, sigma labels, stretching curves and
critical depth. Different declarations fail rather than inheriting the first
file's interpretation. State such as ``zeta`` remains time-dependent. The source
clock's encoded epoch/calendar is authoritative; ``scrum_time.time_origin`` does
not override it. No temperature, salinity or density conversion is performed.
Decoded missing cells and valid zeroes retain their native meaning; native copies
do not yet interpret wet-mask polarity or finite land placeholders.

The retained formula metadata uses `CF ocean s-coordinate, generic form 2
<https://cfconventions.org/Data/cf-conventions/cf-conventions-1.12/cf-conventions.html#_ocean_s_coordinate_generic_form_2>`_:

.. math::

   S = \frac{h_c s + h C}{h_c+h}, \qquad z = \eta + (\eta+h)S.

The adapter checks explicit formula dependencies and their native dimensions,
dimensionless sigma/stretching ranges, positive-up orientation and positive
metre-valued critical depth. It preserves selected ``s``, its referenced ``C``
curve, ``hc``, cropped bathymetry ``h`` and selected-time ``zeta`` without computing
a physical-depth cube. The producer spelling
``ocean_s_coordinate_g2_at_w_location`` on ``s_w`` is retained as
``source_standard_name``; the standard name becomes ``ocean_s_coordinate_g2``
because the declared equation is the same at that sampling location. Other source
definitions are not guessed or silently completed.

Verification includes an independent formula-dependency anchor
(``h=20, hc=5, s=-0.5, C=-0.25, eta=1`` gives ``z=-5.3 m``), exact native decoded
value/mask/coordinate round trips in an ordinary reader, changing-state snapshots,
invalid metadata and lazy selected loading without optional model/polar stacks.
This is engineering verification of copied data and metadata, not scientific
validation of every real regime or a new stable depth diagnostic.

Current scope is native **rho scalars**. Staggered face/current analysis, stress
interpretation, wet-mask application and polar sigma/physical-depth products are
not yet qualified and are rejected where requested, rather than silently invoking
atmospheric wind processing. Native exports attach no wind representation or
wind-speed diagnostic. These limitations do not require installing optional
diagnostic, FA, GRIB, Zarr or polar dependencies for ordinary scalar NetCDF copies.
