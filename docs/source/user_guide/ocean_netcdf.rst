Native ocean NetCDF
===================

For the workflow, use :doc:`../task_guides/coupled_inputs` and
:doc:`../task_guides/scalars_and_vectors`. This page specifies native quantities,
grids, vertical coordinates, temporal support and admitted transformations.

NEMO regional native scalars
----------------------------

``model: nemo`` admits the tested regional NetCDF family with ``nav_lat`` and
``nav_lon`` on its own ``(y, x)`` grid, decoded Gregorian ``time_counter``, and
native ``deptht/depthu/depthv/depthw`` coordinates. It is not qualification of
every NEMO release, arbitrary global/folded grids or companion mesh files.
The regional geometry limits are at most 10% difference
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
native contexts. Extraction preserves data meaning rather than
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
and ordinary-reader checks. Broader real-data qualification remains open. Native
components have the separate limits below.

Separate native components
--------------------------

Native ``vozocrtx``/``vomecrty`` on independent U/V grids and ``vovecrtz`` on
``depthw`` retain source values, geography, zeros, missingness, units and names.
Native barotropic and stress components can also be selected without loading
unrequested companions or interpreting their basis, sign or scaling. Separate
contexts preserve shifted native sampling even when every file uses ``x/y``.
``depthw`` is not relabelled as ``deptht`` merely because their lengths agree.

For any native component selection explicitly declare
``output.cartesian.horizontal_vectors: native``. This does not turn
currents/stresses into winds.
The native ocean path never derives wind speed, radial/tangential winds or
atmospheric reference-frame metadata. The default ``earth_centered`` selection fails
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
still match reference timestamps exactly. The global default is ``common``.

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

Eligible scalar sources can opt into a shared polar target. Target
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

Native ``temp/salt`` are selected on ``s_rho``; ``zeta`` belongs to ``fields_2d``.
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

Native CROCO faces and current analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Regional history fields on ``xi_u/eta_v`` retain their actual N-1 midpoint
locations and ``lat_u/lon_u`` or ``lat_v/lon_v`` geography. With
``output.cartesian.horizontal_vectors: native`` selector, values, source units and
vector basis are copied unchanged; no wet-mask interpretation, companion current
or angle is required. Local face dimensions are ``x_u_box`` and ``y_v_box``;
unavailable bounding faces are missing, not fabricated or extrapolated. Source
coordinate labels remain available. Rho dimensions use ``x_box/y_box``. This
selector applies to ocean currents without making them winds.

Explicit ``earth_centered`` selects rho/Earth analysis for ``u/v`` on ``s_rho`` and
``ubar/vbar`` on ``fields_2d``. Selecting either component loads its companion.
The method requires regular labelled N-1 midpoint faces, declared velocity units,
finite rho-point ``angle`` with angular units, and static ``mask_rho`` with
explicit ``option_0=land`` and ``option_1=water``. These options, not the supplied
contradictory ``land_binary_mask`` standard name, establish the mask polarity;
the source declaration is retained in provenance. ``CPP-options`` must contain
``MASKING`` and must not contain ``WET_DRY``. No wetting/drying support is claimed.

Absent face masks are derived from the product of the two neighbouring binary
rho masks. Explicit binary ``mask_u/mask_v`` additionally restrict support where
present. Each rho component requires both native brackets to be finite and wet:
there is no single-neighbour replacement. After midpoint interpolation,

.. math::

   u_E = u_\rho\cos\alpha-v_\rho\sin\alpha,\qquad
   v_N = u_\rho\sin\alpha+v_\rho\cos\alpha.

Both outputs share the wet-rho/finite-vector mask, including at missing outer
brackets; legitimate zero currents remain zero. Preparation precedes spatial
cropping and sparse level selection. It operates at the same native sigma index,
not at a common physical depth, and performs no temporal interpolation, transport
conservation, smoothing or track-motion subtraction. Declared velocity and angle
units are converted explicitly to m/s and radians; native exports are not converted.
Different static angle/mask arrays or scientific companion definitions across
snapshots fail instead of inheriting the first file's interpretation.

The producer reference is the official `CROCO v2.1.0 source release
<https://doi.org/10.5281/zenodo.15064113>`_: ``OCEAN/setup_grid1.F`` defines the
static face-mask products and ``OCEAN/cpl_prism_put.F`` defines midpoint averaging
followed by this east/north rotation. The rotation applies geometrically at each
native level; the producer routine's coupling example is at the surface. This is
a bounded coordinate-transformation implementation, not a new stable diagnostic
or proof of an unmodified producer build. Independent constant/linear-field,
90-degree/varying-angle and reversed/permuted-axis tests use float64 analytic
references with absolute/relative tolerances of 1e-12; support, zeros, sparse sigma
dependencies, exports, laziness and invalid inputs are also tested. Synthetic
agreement does not validate every real coastline or flow regime.

Analysed fields retain their names but now have rho dimensions and east/north
current definitions in m/s; downstream scripts must use the selected representation
rather than assume native staggering from ``u/v`` names. Ordinary-reader attributes
identify the current frame, method and support; ``current_provenance`` records the
source units, static-mask authority, method and boundary policy, inside the named
source for coupled runs. Native and analysis branches remain separate and attach
no wind-speed, radial/tangential-wind or wind-representation metadata. Stress
analysis remains separately gated; native stress copies do not establish its sign,
basis or physical definition. No optional FA/GRIB/polar stack is needed for
Cartesian copies or current analysis.

Optional shared point sampling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``example/config_file/croco_mesonh.yaml`` demonstrates exact-time named sources,
different native vertical groups, opt-in SURFEX interpretation and selected
CROCO rho/Earth currents. Adapt its paths, native indices and illustrative centre
to the inspected inputs. Set ``horizontal_vectors: native`` for unchanged native
Cartesian faces. Polar processing is off by default; enabling it uses a
shared target, separately selected fields, and ordinary optional polar dependencies.
The fixed or prescribed continuous geographical centres are shared, but each source
performs its own grid lookup. Common time labels do not imply that ocean and
atmospheric grids, masks, temperatures or flux definitions are interchangeable.

CROCO polar scalar fields use the declared static water mask, without requiring
current companions or angle. Selected currents are prepared with the method above
before spatial sampling, even when Cartesian output remains native. Unselected
native faces do not enter a scalar-only polar crop. No ocean wind diagnostics or
automatic storm-motion subtraction run. Shared targets have identical time,
radius, azimuth, longitude, latitude and target identity, but field-local missing
support remains different. Missing brackets/land remain missing under the declared
polar coverage policy; this is not conservative area or transport remapping.
Native binary water masks are used before interpolation, but are not automatically
sampled into polar auxiliaries: bilinear fractions must not be advertised as binary
masks. Explicit polar requests for CROCO binary masks fail; use native masks or the
per-field interpolation support/quality variables instead.

Polar CROCO outputs retain selected ``s_rho/s_w`` labels and original native
indices, but archive ``formula_terms`` and the native vertical standard name as
``source_formula_terms/source_standard_name``. Interpolating bathymetry and sea
level does not commute with the nonlinear native depth formula. Sampled auxiliaries
therefore must not be used to claim that these fields lie on a constant-depth
section or that a reconstructed depth equals sampled native depth. The product
records ``vertical_sampling: native_sigma_indices_not_constant_physical_depth``.
Native Cartesian products retain their valid original formula metadata unchanged.

Compact paired tests cover fixed/moving shifted grids, exact common/strict time
policies, shared scalar/current targets, legitimate SURFEX zeros, sigma metadata,
diagnostics-disabled processing, synchronous/spawned exports, NetCDF and Zarr
ordinary-reader reopening, failed mid-write publication and overwrite protection.
These tests establish bounded implementation behavior, not scientific equivalence
of unlike source quantities or validity of every real configuration.

Embedded SURFEX sea fields in Meso-NH
----------------------------------------

The ``model: mesonh`` NetCDF time-series reader also handles embedded SURFEX
snapshots. To interpret SEA-field missing values, support and unit comments:

.. code-block:: yaml

   model: mesonh
   input:
     format: netcdf
     netcdf:
       surfex_fields: [SST, SSS, H_SEA, LE_SEA, FMU_SEA, FMV_SEA]
   variables:
     fields_2d:
       names: [SST, SSS, H_SEA, LE_SEA, FMU_SEA, FMV_SEA, FRAC_SEA]

This fragment supplements the ordinary paths, tracking, domain and output
configuration; ``FRAC_SEA`` is retained as an ancillary even when not explicitly
selected for export. The finite supported list is the six named fields above plus
``FRAC_SEA`` itself. Only requested, explicitly listed fields are interpreted;
unlisted quantities retain their original values and metadata. Variable-shard,
other-model and non-NetCDF interpretations fail rather than guessing a source.

For this supported family, exact ``999`` is invalid in these SURFEX fields and
unit comments supply missing unit labels.
The selected fields replace this sentinel with missing values, preserving existing
NaNs and legitimate zeroes. This is **not** a dataset-wide Meso-NH sentinel rule:
an unrelated ``PRES=999 hPa`` remains valid. Unselected raw access is still
available by leaving ``surfex_fields`` empty (the default).

``FRAC_SEA`` must have native ``nj/ni`` support and declared physical
``c_grid_dynamic_range`` on both axes. Its physical interior must be finite and
within [0,1]; invalid/missing required support fails. Known outer-halo ``999``
values become missing. Selected SEA quantities are supported where the fraction
is strictly positive. Fractional coastal coverage stays fractional and separate
from Boolean support; values are neither multiplied nor divided by that fraction.
Changing 2-D states are prepared per snapshot before time-series concatenation.
Validation reads the 2-D support field; it does not decode thermal/flux cubes.

Explicit ``units`` take precedence. If absent, the terminal parenthesized unit in
the comment supplies the label, with ``(fraction)`` represented as ``1``. Missing
or ambiguous required comments fail. Actual contradictions with explicit units
fail; known equivalent spellings such as ``kelvin/K`` and ``W m-2/W/m2`` do not.
Original comments are preserved, and ``surfex_units_source`` identifies the
metadata origin. This labels the supplied values; it performs no unit conversion.
Across successive interpreted snapshots, quantity, support and statistical
metadata must agree. Equivalent unit spellings are allowed; incompatible units
such as K versus degC fail instead of combining values under the first label.
Neither preflight nor direct loading silently converts those snapshots.
No CF standard names, flux signs, stress basis, instantaneous/averaged sampling or
new ``cell_methods`` are inferred from field names or diagnostic flags.

Run provenance includes ``surfex_provenance`` (inside each named source for a
coupled run) with source basename, field, units origin, invalid sentinel and support
rule. Resolved configurations retain the opt-in list. Ordinary-reader output
attributes identify the interpreted fields and the absence of additional value
weighting or inferred flux timing/sign/basis. Optional scalar polar sampling uses
the same missing support; its interpolated fractional coverage is not a binary
wet mask or a conservative area average.

Producer evidence was checked in the official `Meso-NH 5.7.2 archive
<https://doi.org/10.5281/zenodo.15698760>`_: ``src/MNH/modd_parameters.f90`` defines
Meso-NH's undefined value as 999; ``write_surf_mnh.f90`` and
``unpack_1d_2d.f90`` scatter native SURFEX values onto the atmospheric array and
replace the SURFEX undefined marker with the Meso-NH marker. The SURFEX-side
undefined constants are different; 999 is not asserted as universal across all
SURFEX containers. ``writesurf_seafluxn.F90`` emits the SST/SSS unit comments;
``write_diag_seb_seafluxn.F90`` emits the heat/stress comments.
``write_diag_surf_atmn.F90`` writes the sea fraction, and ``get_1d_mask.F90`` uses
positive fraction support. This verifies writer conventions, not the actual run's
DIAG averaging/reset configuration or an unmodified producer build. Those facts
remain unresolved where an operation would require them; this native path does
not silently complete them.
