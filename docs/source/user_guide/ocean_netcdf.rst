Native ocean NetCDF
===================

Use ``model: nemo`` or ``model: croco`` to copy supported regional ocean fields
on their native grids. Select current analysis or polar sampling separately.
For worked runs, use :doc:`../task_guides/coupled_inputs` and
:doc:`../task_guides/scalars_and_vectors`.

NEMO regional native scalars
----------------------------

NEMO support requires regional NetCDF with ``nav_lat`` and
``nav_lon`` on its own ``(y, x)`` grid, decoded Gregorian ``time_counter``, and
native ``deptht/depthu/depthv/depthw`` coordinates. Other releases/layouts,
global/folded grids and companion mesh files are not generally qualified.
The regional geometry limits are at most 10% difference
between X/Y spacing and 20% within-axis variability. A spacing override cannot
bypass them. NetCDF is the base path; FA, GRIB, polar and Zarr dependencies are
not needed for native scalar extraction.

Use ``frameit init nemo`` for a fixed-box starting configuration and
``frameit inspect frameit.yaml`` for
metadata inspection. Set actual paths, fields and geographical centres before
running. Fixed and prescribed centres need no reference source. Calculated
tracking requires an atmospheric source. The ocean uses its own geographical
lookup with the supplied continuous centres.

List complementary T-grid scalar files in the named source's ``files``;
their layout is discovered automatically. See :doc:`input_files`.
Do not merge shifted U/V geography into a T-grid source
merely because dimensions have the same names/shapes. Extraction preserves
quantities without automatic conversion:

* potential temperature is not relabelled as in-situ or sea-surface temperature;
* practical salinity is not converted to absolute salinity;
* sigma-theta density anomaly is not relabelled as absolute density.

Native level value selection permits only :ref:`storage/conversion roundoff
<vertical-level-roundoff>`, not a nearest-level fallback;
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
``time: mean (interval: 240 s)``. Exact centre association is the default:
a sample labelled 05:30 needs a centre at 05:30; an atmospheric track containing
only whole hours does not supply it. Independent extraction needs no common
clock. No shifting, nearest matching, filling, interpolation or mean-to-instantaneous
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

For direct native polar sampling, an admitted numeric surface field can use
``kind: continuous`` when its file declares the CF standard name
`sea_surface_height_above_geoid
<https://vocab.nerc.ac.uk/standard_name/sea_surface_height_above_geoid/>`_
and a supported length unit such as ``m`` or ``cm``. The field must sample
native ``time_counter`` on ``(y, x)`` with its own ``nav_lat`` and ``nav_lon``.
Wide integer values are excluded. The name ``zos`` alone is not enough.
:ref:`w1603` identifies the completion in validation. It does not identify the
producer or datum, convert units, infer a wet mask, or establish a time statistic.

Broader real-data qualification remains open. Native components have the separate
limits below.

Separate native components
--------------------------

Native ``vozocrtx``/``vomecrty`` on independent U/V grids and ``vovecrtz`` on
``depthw`` retain source values, geography, zeros, missingness, units and names.
Native barotropic and stress components can also be selected without loading
unrequested companions or interpreting their basis, sign or scaling. Separate
contexts preserve shifted native sampling even when every file uses ``x/y``.
``depthw`` is not relabelled as ``deptht`` merely because their lengths agree.

Copy native components without a transform or wind-pair declaration. They remain
currents/stresses, not winds; no wind diagnostics or atmospheric frame metadata
are added. Native W keeps ``depthw``. NEMO analysis, including
``sampling: mass``, fails rather than returning another representation.

Analysed NEMO components, including explicit polar component requests, remain
unsupported: the admitted files do not establish a qualified angle, mesh,
support and collocation contract. A wind declaration is not such evidence.
This does not block independent scalar copies or eligible scalar polar samples.
No current rotation, stress reconciliation, coastal filling, speed calculation or
track-motion subtraction is performed. Native copying is not a conservation or
all-regime validation claim.

Coupled extraction and optional scalar targets
----------------------------------------------

Use :doc:`../task_guides/coupled_inputs` for a complete named-source request.
One fixed geographical centre covers each source's own selected samples, without
requiring equal clocks. A supplied trajectory instead needs a centre at every
required source time under the default ``exact`` association.
Each source performs its own native index lookup. A centre outside a required
footprint fails rather than substituting an edge point or dropping that time.

``region.sources_coupling_time_association: common`` explicitly reports time
exclusions for the operation needing association. Select ``preceding_hour``
only for the following admitted comparison convention, not to claim that an
ocean mean is an atmospheric snapshot.

Preceding-hour association (no interpolation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``preceding_hour`` method requires selected AROME and NEMO NetCDF sources.
The atmospheric clock supplies the interval-end association times. Selected
AROME fields must explicitly declare instantaneous sampling (``GRIB_stepType:
instant`` or ``cell_methods: 'time: point'``); selected NEMO fields must declare
``time: mean`` and provide decoded one-hour bounds. Contradictory declarations,
invalid bounds and multiple distinct native samples for one requested interval
fail rather than selecting an arbitrary candidate. All participants must have
unique physical records. Repeated timestamps within a file or
overlapping providers of a selected physical field across files fail, even if
another provider has matching values. Complementary variable shards may repeat
matching clock/bounds metadata. Preserve this method's admitted calendar and
selected-cycle rules. It does not apply to CROCO; the default association is
``exact``, not ``preceding_hour``.

At reference time T, select the unique NEMO interval **[T-1 hour, T]** using
the preceding-interval convention (T-1 hour, T]. An AROME snapshot at 06:00
therefore pairs with the 05:00–06:00 NEMO mean, typically labelled 05:30.
Values, masks, depths and grids do not change. This is a comparison convention,
not an instantaneous ocean reconstruction or scientific validation.

If any source lacks a temporal partner, the entire reference-time pairing is
omitted for all sources with a warning. All omissions and selected source times,
intervals and offsets are recorded in ``time_alignment`` in run provenance and
status. Prescribed-track coverage first restricts the reference timeline and its
exclusions are recorded separately. No remaining pairings is an actionable error.
Malformed required metadata is an error, not an excuse to omit a pairing. This
policy never fills missing individual grid cells or substitutes another quantity.

The native sampling label and the interval-end centre/coupling time remain
separate facts. Original calendars/bounds and ``cell_methods: time: mean`` retain
their meaning; ``time_centered`` and original bound arrays remain visible where
supplied. ``source_time`` is reserved for the original sampling clock and must
not already exist in the ocean input. Inspect the stored clocks and association
records rather than assuming a coupling label is a native interval centre.
There is no temporal interpolation, extrapolation, averaging of means or
nearest-time fallback.

Optional spatial scalar targets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Eligible scalar sources can opt into a shared spatial polar target. Radius,
azimuth and target geography agree at the same associated centre, while native
depths, source mean bounds, forecast identity and field-local support remain
different. Component requests remain gated as described above. Continuous
bilinear point sampling is not area-conservative or a physical-depth section.
Polar processing stays optional and is not enabled by the native example.

CROCO native history scalars
----------------------------

CROCO support requires regional ``CROCO history file`` inputs with
decoded Gregorian ``time``, optional agreeing ``scrum_time``, native rho geography
``lat_rho/lon_rho`` on ``(eta_rho, xi_rho)`` and explicit consistent
``Vtransform=2`` declarations. Use ``frameit init croco``, edit its source request,
then run ``frameit inspect frameit.yaml``. Adapt the generated paths,
fields, native level indices and geographical centre to the data. Fixed and
prescribed centres are supported independently or in named-source exact-time runs.
This does not admit every CROCO release, restart/averaged products, other vertical
transforms or a producer-specific coupling convention. The NEMO-only
``preceding_hour`` profile does not apply to CROCO.

Select native ``temp/salt`` under source ``variables.3d`` on ``s_rho`` and
``zeta`` under ``variables.2d``.
Fields genuinely stored on ``s_w`` use a separate group. Do not infer the stored
location of ``w`` or substitute ``omega`` from their names. Fractional sigma values
are **dimensionless, not metres**; value selection permits only the documented
storage/conversion roundoff, not a nearest-level fallback. Sparse/reordered selections retain
``s_rho_source_native_index/s_w_source_native_index``. Native rho geography, source
axis labels and source dynamic-range metadata survive crops; the output is not
collocated with an atmospheric grid merely because array sizes agree.

Selected scientific definitions must agree across successive files, including
quantity/units, coordinate formula metadata, sigma labels, stretching curves and
critical depth. Different declarations fail rather than inheriting the first
file's interpretation. Input-aware validation checks selected sigma formula
metadata and compares selected stretching curves and critical depths within
each native field's time-series files. Distinct native grids keep their own
definitions. Current/polar requests also check their required static
mask/angle support; native copies do not acquire these analysis requirements.
These checks read coordinate and declared static-support arrays, not current,
temperature, salinity or sea-level payloads.
State such as ``zeta`` remains time-dependent. The source
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

For example, ``h=20, hc=5, s=-0.5, C=-0.25, eta=1`` gives ``z=-5.3 m``.
Preserving formula dependencies does not compute a depth diagnostic or validate
every real regime.

Native CROCO faces and current analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Regional history fields on ``xi_u/eta_v`` retain their actual N-1 midpoint
locations and ``lat_u/lon_u`` or ``lat_v/lon_v`` geography. Native copying preserves
values, source units and vector basis; no wet-mask interpretation, companion current
or angle is required. Public face dimensions use ``x_u`` and ``y_v``;
unavailable bounding faces are missing, not fabricated or extrapolated. Source
coordinate labels remain available. Rho dimensions use ``y_rho/x_rho``; see
:ref:`model-grid-coordinate-names` for each field's geography and original-index
auxiliaries. Copying ocean currents does not make them winds.

An explicit source transform selects rho/Earth analysis for ``u/v`` on ``s_rho``
or the barotropic ``ubar/vbar`` pair. Declare the stored pair's grid basis and
the ``angle`` rotation coordinate. This fragment shows one selected component:

.. code-block:: yaml

   sources:
     ocean:
       variables:
         3d: [u]
       wind_pairs:
         - u: u
           v: v
           basis: grid
           rotation: {method: coordinate, coordinate: angle}
       transforms:
         - fields: [u]
           sampling: mass
           basis: earth
           units: m s-1

Selecting either analysed component loads its companion without exporting it
unless requested.
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
A proven native-static mask remains static even if assembly adds a singleton time
axis; genuinely time-dependent masks are unsupported. Static support is rechecked
before use. A changed required angle fails with a request to revalidate, not a
silent geometry refresh.

The producer reference is the official `CROCO v2.1.0 source release
<https://doi.org/10.5281/zenodo.15064113>`_: ``OCEAN/setup_grid1.F`` defines the
static face-mask products and ``OCEAN/cpl_prism_put.F`` defines midpoint averaging
followed by this east/north rotation. The rotation applies geometrically at each
native level; the producer routine's coupling example is at the surface. This is
a bounded coordinate-transformation implementation, not a new stable diagnostic
or proof of an unmodified producer build. Constant/linear-field and rotation checks
use float64 analytic references with absolute/relative tolerances of 1e-12.
This numerical agreement does not validate every coastline or flow regime.

Analysed fields retain their names but now have rho dimensions and east/north
current definitions in m/s; downstream scripts must use the selected representation
rather than assume native staggering from ``u/v`` names. Ordinary-reader attributes
identify the current frame, method and support; ``current_provenance`` records the
source units, static-mask authority, method and boundary policy, inside the named
source for named-source runs. Applied current operations also identify their
native component input basenames in ``source_files``. Scalar-only processing
does not create current-analysis records. Native and analysis branches remain separate and attach
no wind-speed, radial/tangential-wind or wind-representation metadata. Stress
analysis remains separately gated; native stress copies do not establish its sign,
basis or physical definition. No optional FA/GRIB/polar stack is needed for
Cartesian copies or current analysis.

If ``mask_rho`` declares ``option_0=land`` and ``option_1=water``, the CF name
``land_binary_mask`` contradicts those codes. FrameIt records that source label
as ``source_standard_name`` instead, for both native and analysis support
exports. Mask values and polarity do not change. Use ``mask_rho`` and its
declared options rather than querying the old CF name.

Optional shared point sampling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``example/config_file/croco_mesonh.yaml`` demonstrates exact-time named sources,
different native vertical groups, opt-in SURFEX interpretation and selected
CROCO rho/Earth currents. Adapt its paths, native indices and illustrative centre
to the inspected inputs. Omit the ocean's model-grid transforms for unchanged
native faces. Polar processing is off by default; enabling it uses a
shared target, separately selected fields, and ordinary optional polar dependencies.
The fixed or prescribed continuous geographical centres are shared, but each source
performs its own grid lookup. Common time labels do not imply that ocean and
atmospheric grids, masks, temperatures or flux definitions are interchangeable.

CROCO rho scalar polar fields use the declared static water mask, without requiring
current companions or angle. Supported current analysis requires explicit
``products.polar.field_options.ocean.<field>: {sampling: mass, basis: earth}``
and the pair/rotation declaration above. Those options prepare the pair before
sampling even when model-grid output remains native. Unsupported native-face
polar requests fail rather than borrowing rho masks or changing representation.
Unselected native faces do not enter a scalar-only polar crop. No ocean wind
diagnostics or automatic storm-motion subtraction run. Shared targets have the
same radius/azimuth and identical geography at the same associated centre. Native sample
times, interval bounds and field-local support remain distinct.
Missing brackets/land remain missing under the declared
polar coverage policy; this is not conservative area or transport remapping.
Native binary water masks are used before interpolation, but are not automatically
sampled into polar auxiliaries: bilinear fractions must not be advertised as binary
masks. Explicit polar requests for CROCO binary masks fail; use native masks or the
per-field interpolation support/quality variables instead.

Direct native polar sampling can use ``kind: continuous`` for the numeric
history field ``zeta(time, eta_rho, xi_rho)`` when kind is unstated. The
selected file must supply rho geography, native ``time(time)``,
``Vtransform=2`` and its own static ``mask_rho``.
If present, the standard name must agree with ``sea_surface_height`` or
``sea_surface_height_above_mean_sea_level``. This matches the `CROCO v2.1.3
history writer
<https://gitlab.inria.fr/croco-ocean/croco/-/blob/ab63b583c9f9e1faceb838e7063b71f1ab9bd56f/OCEAN/def_his.F>`_;
it does not establish a datum, infer units or relax existing mask checks.

Polar CROCO outputs retain selected ``s_rho/s_w`` labels and original native
indices, but archive ``formula_terms`` and the native vertical standard name as
``source_formula_terms/source_standard_name``. Interpolating bathymetry and sea
level does not commute with the nonlinear native depth formula. Sampled auxiliaries
therefore must not be used to claim that these fields lie on a constant-depth
section or that a reconstructed depth equals sampled native depth. The product
records ``vertical_sampling: native_sigma_indices_not_constant_physical_depth``.
Native Cartesian products retain their valid original formula metadata unchanged.

Shared targets do not establish scientific equivalence of source quantities or
validity of every real configuration.

Embedded SURFEX sea fields in Meso-NH
----------------------------------------

Meso-NH NetCDF inputs can contain embedded SURFEX snapshots. These remain part
of the atmospheric source, even when only sea fields are selected.
This complete illustrative request opts into the existing SEA-field missing-value,
support and unit-comment rules:

.. code-block:: yaml

   schema_version: 3
   run:
     name: sea-fields
   sources:
     atmosphere:
       model: mesonh
       format: netcdf
       files: ./data/mnh*.nc
       interpretation: mesonh_surfex_sea
       variables:
         2d: [SST, SSS, H_SEA, LE_SEA, FMU_SEA, FMV_SEA]
   output:
     directory: ./results/sea-fields

Replace paths and selected fields from producer evidence. ``FRAC_SEA`` is
required support even when not selected for export. The finite eligible list is
the six named fields above plus ``FRAC_SEA`` itself. Only selected eligible
quantities and their support are interpreted; unrelated fields retain their
native values and metadata. Other-model and non-NetCDF interpretations fail.
Missing selected support is an error, not permission to search another stream.

For this supported family, exact ``999`` is invalid in these SURFEX fields and
unit comments supply missing unit labels.
The selected fields replace this sentinel with missing values, preserving existing
NaNs and legitimate zeroes. This is **not** a dataset-wide Meso-NH sentinel rule:
an unrelated ``PRES=999 hPa`` remains valid. Omit ``interpretation`` for ordinary
native access, without these sentinel/support rules.

``FRAC_SEA`` must have native ``nj/ni`` support and declared physical
``c_grid_dynamic_range`` on both axes. Its physical interior must be finite and
within [0,1]; invalid/missing required support fails. Known outer-halo ``999``
values become missing. Selected SEA quantities are supported where the fraction
is strictly positive. Fractional coastal coverage stays fractional and separate
from Boolean support; values are neither multiplied nor divided by that fraction.
Source time selection applies to interpreted quantities and required support.
Support-value checks run at execution, not metadata preflight, and do not require
unselected thermal/flux cubes.

Native ``units`` take precedence. If absent, the terminal parenthesized unit in
the comment supplies the label, with ``(fraction)`` represented as ``1``.
Source ``field_metadata.<field>.units`` can fill a genuine gap when both are
absent; it cannot replace either known fact. Missing or ambiguous required units
fail. Contradictions fail; known equivalent spellings such as ``kelvin/K`` and
``W m-2/W/m2`` do not.
Original comments are preserved, and ``surfex_units_source`` identifies the
metadata origin. This labels the supplied values; it performs no unit conversion.
Across successive interpreted snapshots, quantity, support and statistical
metadata must agree. Equivalent unit spellings are allowed; incompatible units
such as K versus degC fail instead of combining values under the first label.
Neither preflight nor direct loading silently converts those snapshots.
No CF standard names, flux signs, stress basis, instantaneous/averaged sampling or
new ``cell_methods`` are inferred from field names or diagnostic flags.

Run provenance records the method, interpreted fields and support checks under
``sources.<id>.interpretation``, and metadata origins under
``sources.<id>.field_metadata``. Resolved configurations retain the explicit
source interpretation. Ordinary-reader field attributes record the sentinel,
support rule and absence of additional value weighting or inferred flux timing/
sign/basis. This interpretation does not request or qualify polar sampling.
For successive snapshots, ``interpretation.metadata_records`` retains each
field's source basename, time/cycle, observed attributes, resolved units and
metadata origins. Combined variable attributes represent the first selected
record; consult these per-record facts for equivalent spellings or unit origins
that differ between snapshots. Values are not rescaled.

Writer conventions are defined in the official `Meso-NH 5.7.2 archive
<https://doi.org/10.5281/zenodo.15698760>`_: ``src/MNH/modd_parameters.f90`` defines
Meso-NH's undefined value as 999; ``write_surf_mnh.f90`` and
``unpack_1d_2d.f90`` scatter native SURFEX values onto the atmospheric array and
replace the SURFEX undefined marker with the Meso-NH marker. The SURFEX-side
undefined constants are different; 999 is not asserted as universal across all
SURFEX containers. ``writesurf_seafluxn.F90`` emits the SST/SSS unit comments;
``write_diag_seb_seafluxn.F90`` emits the heat/stress comments.
``write_diag_surf_atmn.F90`` writes the sea fraction, and ``get_1d_mask.F90`` uses
positive fraction support. These conventions do not establish a run's DIAG
averaging/reset configuration or an unmodified producer build. Operations needing
those facts must resolve them explicitly.
