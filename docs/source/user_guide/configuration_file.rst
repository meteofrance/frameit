Configuration file (YAML schema version 3)
==========================================

A YAML file selects source data, fields, regions and products. Source-specific
choices belong under ``sources``. Shared geographical and output choices belong
at the top level. Paths in the YAML are relative to that file's directory,
including auxiliary files and the output directory.

Minimal example
---------------

This complete request extracts a scalar on its original model grid. Replace
the example path and field name with those in your data.

.. code-block:: yaml

   schema_version: 3
   run:
     name: scalar
   sources:
     atmosphere:
       model: arome
       files: ./data/first-run.nc
       variables:
         2d: [instructional_scalar]
   output:
     directory: ./results

Omitted ``products`` requests only model-grid output. Omitted ``region`` keeps
the full domain without calculating a track. The output directory must be fresh
unless you explicitly request replacement.

Read the validation report
--------------------------

Check the same request before running it:

.. code-block:: bash

   frameit validate frameit.yaml
   frameit validate frameit.yaml --json
   frameit validate frameit.yaml --schema-only --json

Schema-only checks the controls without opening inputs. Ordinary validation
inspects metadata, needed coordinates and required dependencies; it does not
validate scientific field values. Execution-dependent checks remain deferred.

The JSON report has ``report_version: 1``, ``command``, ``status``, ``data``,
``warnings``, ``errors`` and ``deferred_checks``. Standard output contains one
document; logs go to standard error. An error report exits nonzero.
``data`` separates effective ``configuration``, ``origins``, ``inputs``, ``plan``
and ``pending`` facts. Pending metadata is not a completed configuration choice.

Errors identify affected keys/files, YAML locations, expected and observed facts,
and possible repairs. Independent errors are collected together; checks blocked
by another error are not reported as passed. A successful schema or metadata
check is not proof of scientific validity. See :doc:`../troubleshooting`.

.. _starter-catalogue:

Starter catalogue
------------------

``frameit init`` writes ``frameit.yaml`` unless ``--output`` selects another
file. It refuses an existing file unless ``--force`` is supplied.

.. list-table:: Named starters and equivalent compositions
   :header-rows: 1
   :class: config-table

   * - Named starter
     - Equivalent command
   * - ``arome-pressure-wind``
     - ``frameit init arome``
   * - ``mesonh-pressure-wind``
     - ``frameit init mesonh``
   * - ``arome-fixed-scalar``
     - ``frameit init arome --tracking fixed_box``
   * - ``nemo-native``
     - ``frameit init nemo``
   * - ``croco-native``
     - ``frameit init croco``
   * - ``arome-nemo``
     - ``frameit init arome --coupling nemo``
   * - ``mesonh-croco``
     - ``frameit init mesonh --coupling croco``

Use a model selector to compose ``--tracking`` and ``--coupling``. A named
starter rejects those flags. Coupling starters support AROME+NEMO or
Meso-NH+CROCO, with fixed geometry by default. They also accept
``prescribed_track``, ``pressure_wind`` and ``pressure_centroid``. Inspect
the files and replace instructional paths, positions and scientific declarations
before running a starter.

Identity and input
------------------

Supply integer ``schema_version: 3``. A boolean, quoted string or other version
is not valid. ``run.name`` defaults to ``analysis`` and controls product names.
``run.description`` is optional.

``sources`` maps user-chosen names to source declarations. The names do not
identify a model or physical type. Each source accepts:

* ``model``: ``arome``, ``mesonh``, ``nemo`` or ``croco``.
* ``format``: ``netcdf``, ``grib`` or the admitted native ``fa`` format.
* ``files``: a path, glob, or list of paths and globs.
* ``exclude``: explicit path/glob exclusions.
* ``time``, ``variables``, scientific declarations and reader settings below.

Omitted model/format declarations need unambiguous input evidence. Explicit
declarations must agree with reliable metadata. File names and selected fields
alone do not establish scientific meaning.

Allow one source of each physical type: atmosphere, ocean and surface. Admitted
model/file profiles determine that type; there is no ``type`` override.
AROME-produced SURFEX and atmospheric AROME have different profiles.
Embedded Meso-NH SURFEX fields remain part of the atmospheric source.
Independent extraction preserves each source's own times, cycles, grids and
masks. A source does not inherit another source's fields or level selection.

Only the selected inventory may supply requested fields or calculation inputs.
Competing providers of the same field, level, time and cycle fail. Resolve
them with ``files``, ``exclude`` or an exact cycle selection; there is no
first/last-provider choice. See :doc:`input_files` for input handling.

Time selection
~~~~~~~~~~~~~~

Omit source ``time`` to keep all available times. A window uses inclusive
``start`` and ``end`` bounds. Alternatively, ``values`` lists exact existing
timestamps; every requested value must exist. Times are processed chronologically.

``stride`` is a positive integer. It keeps every Nth available record after the
window, starting at its first record. It does not interpolate or make a regular
time series. Empty selections fail. The source calendar is preserved.

If several forecast cycles exist, supply ``time.cycle`` as the exact reference
time. Equal valid timestamps do not prove that cycles are equivalent.
Selections restrict scientific reads for extraction and internal calculations,
including tracking. A method needing unavailable times fails rather than
expanding the selection.

Variables and vertical levels
-----------------------------

Inside each source, ``variables.2d`` lists fields without a selectable vertical
axis. ``variables.3d`` lists fields with one. Time does not count as a spatial
axis. Use source field names, not native group names or qualified selectors.
An ambiguous name or wrong category fails with the affected source and field.

One optional ``variables.levels`` applies to all requested 3D fields and results
in that source, separately on each product's representation. It does not affect
2D fields. Omission keeps every level on each field's own grid.

Choose exactly one selection strategy:

* ``indices``: original zero-based, nonnegative positions. Use a list or an
  inclusive ``{start, end, step}`` range.
* ``values``: existing coordinate labels. Use a list or an inclusive
  ``{min, max}`` interval. Interval bounds need not be stored labels.
* ``domain: physical``: exclude only adapter-verified extra/boundary levels.
  An unknown physical range fails.

Explicit lists keep their order. Intervals and all-level selections keep grid
order. Duplicate or unavailable levels fail, including a level absent from only
one requested field. One selected 3D level retains a length-one vertical axis.
Selection alone never interpolates vertically.

Optional ``units`` describes requested labels and exported vertical coordinates.
It can accompany a selection or convert all coordinates by itself. Compatible
conversions change coordinate values and metadata together, not the physical
field values. For example, ``850 hPa`` can select a stored ``85000 Pa`` label.
Value selection across axes with different known units needs explicit units.
Matching permits only storage/conversion roundoff; see
:ref:`vertical-level-roundoff` for the limit and ambiguous-match errors.

If source units are missing, requested units declare an assumption: the stored
numbers already use them, without rescaling. Missing units with or without a
declaration produce a warning and are recorded. Other physical checks may still
require units. See :doc:`../task_guides/field_selection`.

Source meaning and reader settings
-----------------------------------

``field_metadata.<field>`` fills gaps in scientific metadata. Keys include
``units``, ``kind: continuous | categorical`` and ``temporal_kind``. These describe
stored values; they do not convert them. Contradictions with reliable metadata
fail. Metadata records distinguish observed facts from user declarations.
Different known units cannot be replaced by a new label; any numerical conversion
needs an explicit transform. Unit symbols retain their case; unknown spellings
do not establish equivalence. A declaration alone does not select a field.
Method-specific eligibility still applies.

``interpretation: mesonh_surfex_sea`` explicitly selects the admitted SEA rules
for eligible fields and their support data. Omission keeps ordinary native
access. This does not apply sentinel handling to unrelated fields.
See :doc:`ocean_netcdf` for producer, quantity and missing-value limits.

Put native FA ``profile`` and ``native_cubes`` beside ``model`` and ``format``.
A cube declares ``records``, ``vertical_position`` and ``sampling``; admitted
wind cubes also declare ``vector_basis`` and ``component_scaling``.
``field_metadata.<cube-name>`` supplies its scientific declarations.
FA-specific ``subdomain``, ``earth_radius_m`` and ``expected_source`` stay under
``fa``. No record-name convention establishes vertical meaning.
The existing producer, encoding, scaling and spectral limits still apply.
See :doc:`fa_inputs`, :doc:`fa_contracts` and :doc:`fa_atmosphere`.

Technical settings belong under source ``reader``:

* ``engine`` selects a supported NetCDF reader: ``h5netcdf``, ``netcdf4`` or
  ``scipy`` for compatible encodings.
* ``chunks`` uses input dimension names and element counts.
* ``python_executable``, ``timeout_seconds`` and ``max_points`` are FA-only:
  the helper interpreter, transaction timeout and decode-size guard.

A small crop may still require decoding a full native FA record.
A point guard or estimate is not a peak-memory ceiling.

Transforms and derived fields
-----------------------------

Native copying preserves stored samples, units, grids and masks. Copying one
wind component does not require its unselected companion or a basis declaration.
Selecting U/V does not automatically calculate speed or radial/tangential wind.
Native multi-file copies require consistent stored units; they do not silently
normalize later files to the first file's label.

When an operation needs a wind pair, reliable metadata takes precedence.
``wind_pairs`` can declare ``u``, ``v`` and ``basis: grid | earth``.
Supported ``rotation.method`` choices are ``coordinate``, ``geolocation`` and
``mesonh_projection``. ``coordinate`` names its angle through ``coordinate``;
the Meso-NH method uses the applicable ``BETA``, ``RPK`` and ``LON0``.
Missing geometry or conflicting evidence fails. A declaration alone does not
rotate exported values. See :ref:`wind-grid-contract` for numerical conventions.

Source ``transforms`` target explicit ``fields``. Select ``sampling: native |
mass``, ``basis: native | earth`` and/or compatible ``units`` conversions.
Mass points are model cell centres, not fixed physical heights.
Control W separately from U/V. Remapping changes sample locations, not the
physical quantity; pressure vertical velocity remains pressure vertical velocity.
These transforms govern model-grid exports, not tracking or polar preparation.

Source ``derived`` maps an output name to an admitted ``method`` and explicit
``inputs``. The current method is ``wind_speed`` with named ``u`` and ``v``
inputs; selecting U/V alone does not request it.
Required inputs are loaded internally and exported only if requested.
Output-name collisions fail. Only results needed by requested products or another
requested operation are calculated. Each method retains its own preparation,
vertical grid and documented limits.

Regions and tracks
-------------------

One top-level ``region`` applies independently to every source. Omission means
full-domain model-grid extraction without a centre provider.
Choose at most one of:

* ``center: {latitude, longitude}``, in degrees north/east.
* ``track: {file: ./track.nc}``, an unambiguous one-dimensional NetCDF trajectory.
* ``tracker: {method: ...}``, a calculated atmospheric track, with method settings
  directly under ``tracker``.

``region.width_km: {x, y}`` gives full crop widths along each native grid's x/y
directions, not necessarily an east/north rectangle. Native samples are retained.
Partially covered crops are padded with missing values. A centre outside a
required source footprint fails rather than moving.

Calculated tracking uses the atmospheric source whatever its name.
``pressure_wind`` uses full ``search_width_km`` and ``refine_width_km`` values,
defaulting to 200 and 100 km. ``on_incomplete`` defaults to ``error``;
explicit ``keep_prefix`` is allowed only where supported and marks incomplete
results. Tracker dependencies are separate from exported fields.

Supplied tracks need unique decoded times, finite positions and consistent
coordinate identification, units and dimensions. Extra times are allowed;
missing centres at required source times fail by default. FrameIt does not
interpolate them silently.

``region.sources_coupling_time_association`` defaults to ``exact``: each selected
source sample needs a centre, but independent source timelines may differ.
``common`` explicitly selects common times for the operation needing association
and reports exclusions. ``preceding_hour`` retains the narrow admitted AROME/NEMO
instantaneous/hourly-mean contract; it is not nearest-time matching.
See :doc:`../concepts/time_support` and :doc:`../task_guides/moving_region`.

Products and polar sampling
---------------------------

``products`` requests ``model_grid``, ``polar`` and/or ``track``. Omission means
model-grid output only; an explicit empty mapping is invalid. List only requested
products. ``model_grid: true`` and ``track: true`` are complete requests.
A centre provider alone does not request an exported trajectory.

Field products reuse source ``variables`` and ``derived``. Optional product
``fields`` maps source names to exact subsets of those requests. Unlisted sources
and fields are excluded. Unknown references fail; internal inputs need not be
exported.

``products.polar`` requires ``radius_km`` and a region centre provider, not a
model-grid crop or model-grid export. Its input support is resolved separately.
Changing only the crop must not change polar sampling.
See :doc:`../task_guides/polar_sampling` for a complete instructional request.

Optional ``radial_step_km`` defaults to native source spacing and cannot be finer.
``azimuth_count`` is the only angular control. Omission chooses a count from
outer-ring native spacing. Rings run clockwise from north without a duplicate
endpoint. The exact outer radius is included; the final interval may be shorter.
These are point samples, not area averages or conservative remapping.

``shared_grid: true`` opts into common target coordinates. Automatic shared
spacing uses the coarsest participating source. Source masks, vertical axes,
quantities and time-association choices remain distinct.

Proven continuous fields default to bilinear interpolation; proven categorical
fields use nearest-neighbour. Unresolved kind fails rather than being guessed
from a field name. ``missing_data_policy`` defaults to ``strict``.
Explicit ``renormalize`` requires ``min_valid_weight_fraction``. All-missing and
unmapped points stay missing; real zeroes stay zero.

Per-field options live under
``products.polar.field_options.<source>.<field>``. They accept
``interpolation: bilinear | nearest``, the missing-data controls above and
admitted ``sampling: native | mass``. They may target needed internal inputs,
but do not request exports. Unused or inapplicable options fail.
Nearest-neighbour does not use partial-stencil renormalization.
Wind speed is the magnitude of U/V sampled at polar points, not an interpolation
of speed calculated earlier. Polar W stays native unless its own option requests
supported mass-point remapping.

Advanced polar ``processing`` keys are ``chunks``, ``max_target_points``,
``plan_cache.entries``, ``plan_cache.max_bytes``, ``source_halo_points``,
``weight_zero_tolerance`` and ``profile``. Insufficient support fails.
``profile`` enables performance measurements, not extra scientific diagnostics.
When false, optional polar timings and graph/RSS measurements are unmeasured;
cache activity and retention counters remain available.

Output, resources and metadata
-------------------------------

``output.directory`` defaults to ``./output``. ``output.overwrite`` defaults to
false in runtime and starters. Replacement never authorizes source-data
replacement or concurrent writers. Use a fresh directory for each attempt.

``output.format`` is ``netcdf`` by default or ``zarr`` for field products.
Trajectories always use NetCDF. Each source/product writes one dataset:
``<run.name>.<source>.model_grid.nc`` or ``<run.name>.<source>.polar.nc``,
with ``.zarr`` for Zarr fields. Requested tracks use ``<run.name>.track.nc``.
Products, logs and caches live in their respective run subdirectories.

Under ``output.writer``, ``engine`` and ``unlimited_time`` are NetCDF-only;
``shards`` is Zarr-only. NetCDF engines are ``netcdf4`` and ``h5netcdf``.
``compression.level`` defaults to 1 and ``compression.coordinates`` to false.
``chunks`` and ``shards`` use exported dimension names and element counts.
Explicit inapplicable settings fail, even if a Zarr field run also requests a
NetCDF track. Unlimited time does not promise append/resume support.
Precision and missing values are preserved. See :doc:`output_files`.
Storage keys use the :ref:`exported coordinate names <model-grid-coordinate-names>`,
not source reader dimension names. Naming preserves distinct sampling grids;
it is not a numerical remap.

Optional ``resources.cpus`` sets the CPU budget; omission uses detected
allocation/affinity limits. Requests above that limit fail.
Advanced controls are ``scheduler: threads | synchronous``, ``compute_workers``,
``export_workers``, ``native_threads`` and ``synchronous_export``.
Defaults are threads, one native thread, asynchronous export and automatic workers.
Input chunks belong under source ``reader``; computation chunks under each
product's ``processing``; storage chunks under ``output.writer``.
An explicit dimension must match an applicable target, not every product.
Product chunks use public product axes, including qualified vertical names;
native input names are not silent aliases. Run provenance records effective
origins and actual chunk applications. Unresolved layout/decoder estimates are
reported as pending, not as memory limits.

``logging.level`` accepts ``DEBUG``, ``INFO``, ``WARNING`` or ``ERROR`` and
defaults to ``INFO``. Optional ``metadata.institution`` has no institutional
default. ``metadata.extra`` holds annotations; these cannot replace generated
scientific provenance.

Defaults and omissions
----------------------

Omit an optional control to use its default. Explicit ``null`` is invalid:
remove the key instead. Empty mappings are allowed only where no required entry
is missing. Arbitrary annotation values in ``metadata.extra`` are exempt.
Booleans do not count as numeric sizes or integer versions.

Operational precedence is CLI, then YAML, then defaults. CLI paths are relative
to the launch directory; YAML paths remain relative to the YAML directory.
Scientific selections stay in the YAML. Defaults, input evidence, automatic
choices and overrides must remain distinguishable in the effective settings and
run records.
