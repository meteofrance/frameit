Configuration file (YAML schema version 3)
==========================================

A YAML file selects source data, fields, regions and products. Source-specific
choices belong under ``sources``. Shared geographical and output choices belong
at the top level. Paths in the YAML are relative to that file's directory,
including auxiliary files and the output directory.

Start with the example below. For every public key and its alternatives, use the
:doc:`annotated all-options reference <../reference/all_keys>`.

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

``--schema-only`` checks controls without opening inputs. Ordinary validation
checks metadata, coordinates, dependencies and declared static analysis support.
It does not check requested scientific field values; execution-dependent checks
remain deferred.

The JSON report has ``report_version: 1``, ``command``, ``status``, ``data``,
``warnings``, ``errors`` and ``deferred_checks``. Standard output contains one
document; logs go to standard error. An error report exits nonzero.
``data`` separates effective ``configuration``, ``origins``, ``inputs``, ``plan``
and ``pending`` facts. Pending metadata is not a completed configuration choice.

Errors identify keys/files, YAML locations, expected/observed facts and possible
repairs. Each error has a ``code`` and a ``help`` path relative to the docs for
that FrameIt version. Warnings remain strings and start with a code in brackets.
Find a code in :doc:`../troubleshooting/codes`.
For failed or blocked checks, see :doc:`../troubleshooting`.

Resolve missing field metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Full validation and execution can fill missing ``units``, ``long_name`` and
``standard_name`` on selected fields. It matches the exact producer release,
case-sensitive native name and the writer or group evidence available in the
input. It does not infer a version from a filename, or use a model's published
mnemonic as a native variable name. Missing optional labels do not fail
validation.

For Meso-NH NetCDF, the current reader checks root variables, using the native
``MNH_VERSION`` or an exact ``MNH_VERSION_STR`` release. A vertical-group
selector is not a NetCDF group path.

Native metadata and consistent ``sources.<id>.field_metadata`` declarations
take precedence. A :ref:`w1306` warning identifies each value FrameIt obtained
from the catalogue. No YAML changes are needed for these values; ``frameit run``
resolves them on its own. Input files and YAML are not rewritten.

FrameIt does not combine catalogue values for one field across different
producer releases. It also withholds values that conflict with the input or
that the selected operation cannot use. For example, a grid-relative CF name
cannot label an Earth-relative wind. If the selected method requires native
headers, correct those upstream. An unlisted tracer or custom diagnostic is
not an error by itself.

The installed offline catalogue is release 0.2.1. The :ref:`Meso-NH ZTOP policy
<mesonh-ztop>` is reference metadata, not a catalogue value supplied to a run.
``data.plan.metadata_catalogue`` records its content SHA-256, matched
assertions, applied values, and missing or conflicting evidence. The catalogue
covers the audited sources in its bundled manifest, not every configuration,
writer, or runtime field. FrameIt checks the SQLite index against the bundled
release before using it and rebuilds a damaged index. The disposable index is
stored under ``$XDG_CACHE_HOME/frameit/metadata-catalogue`` (default
``~/.cache/frameit/metadata-catalogue``). Schema-only validation and inspection
do not open the catalogue or create that index.

If full validation can bind the workload, **Overview** and the text report
show a RAM recommendation. In JSON, see ``data.plan.memory_estimate``.
See :ref:`estimate-run-ram` for how to use it.

Terminal view
~~~~~~~~~~~~~

The terminal view is installed with FrameIt:

.. code-block:: bash

   frameit validate frameit.yaml

In an interactive terminal, validation opens **Overview**, **Findings**, and
**Details**. Press ``1``, ``2``, or ``3`` to switch tabs. After saving edits in
another terminal, press ``r`` to recheck the same file. The activity screen
returns while the new check runs. Cancelling a recheck restores the previous
report, not a result for the edited file. If you cancel the first check, use
``r`` to retry. Press ``q`` to quit when idle. Quitting after a cancelled check
returns status 130 unless another check produces a new report. Press ``?`` for
shortcuts or ``p`` to send the configuration path to the terminal clipboard.
Paste to verify delivery.

The logo shows that a check is active. The progress bar counts files checked
in the current source, not overall validation progress. Some stages have no
known total. The ETA estimates only the current source's metadata scan.
``Ctrl+C`` requests cancellation. A native
read may need to finish before cancellation takes effect.

**Overview** summarizes the checked inputs, selection, time, region and planned
outputs. It shows the run command when input checks pass and the first fix
when validation fails. Preflight checks metadata and can check required
static support, such as an ocean mask. Other value and mask checks are
deferred to execution.

In **Findings**, press Enter to open the selected finding and Esc to return to
the list. The problem and any reported repair appear before **Technical
evidence**, where the original message, full paths and evidence remain
available. Press ``y`` in a finding to copy its evidence. Warnings logged
while reading metadata appear here too. Press ``n`` to filter to field
discovery notes when available. Items under **During run** are not counted
as validation issues. On a wide terminal, press ``b`` to hide or show the list.

For a live validation error, press ``e`` to open the active YAML in the editor
set by ``VISUAL`` or ``EDITOR``. Some editors accept the reported line number;
otherwise FrameIt opens the file normally. Press ``l`` to copy the recorded
location when available. It may point to an enclosing key or become stale after
edits. Returning from the editor does not recheck the file. Save your edits,
return to FrameIt and press ``r``.

In **Details**, press ``Tab`` to focus a section and ``Enter`` to expand or
collapse it. Use Page Up and Page Down for long panels, and left and right
arrows for long lines. The title of the expanded section stays visible above
its contents as you scroll. Click that title to collapse the section. The
processing plan lists reported products by source. Move through the table
to see the selected product's fields, full destination and layout. These
are planned products, not completed publications. Output paths from a
failed check are unconfirmed. Expand **Raw report** for the original facts.

Press ``g`` where **Related** is offered to follow recorded prerequisites,
settings, sources or bound fields. Esc returns to the previous item.
After revalidation, press ``u`` to compare with the last completed check.
A finding that is no longer reported was not necessarily resolved; some checks
may not have run. Cancelled checks do not become comparison baselines.

.. _terminal-report-archives:

In either terminal report, press ``w`` and enter a new path to export the
completed report as JSON. Existing files are not replaced. The export contains
metadata and may include private paths and configuration values. Reopen the
archive with the command that produced it, for example:

.. code-block:: bash

   frameit validate --saved-report validated.json
   frameit inspect --saved-report inspected.json

Saved reports show recorded evidence without opening the original YAML or
datasets. Do not pass a YAML path with ``--saved-report``. Refresh and editing
are unavailable. Use a separate live command to check current inputs.

Use ``frameit validate frameit.yaml --cli`` for the text report even in a
terminal. ``--json`` writes one JSON report. Redirected commands do not open
the terminal view.

.. _terminal-motion:

For less motion in Inspect or Validate, set ``TEXTUAL_ANIMATIONS=basic`` for
a static activity mark and a non-animated sidebar. To disable animations and
smooth scrolling, run for example:

.. code-block:: bash

   TEXTUAL_ANIMATIONS=none TEXTUAL_SMOOTH_SCROLL=0 frameit validate frameit.yaml

If the terminal cannot display Braille, set ``NO_COLOR=1`` to use text
activity feedback. These settings do not change the check or its report.

Authored and effective views
----------------------------

Use the same file for inspection, validation and execution:

.. code-block:: bash

   frameit inspect frameit.yaml
   frameit config show frameit.yaml
   frameit config show frameit.yaml --json
   frameit config show frameit.yaml --effective --json

``config show`` shows the parsed request without defaults. Its YAML view keeps
parsed values. The JSON view uses ISO strings for dates/timestamps, arrays for
sets, string keys, ``{"hex": "..."}`` for binary values and
``{"nonfinite": "nan"}`` (or ``"inf"``/``"-inf"``) for nonfinite numbers.

``--effective`` adds metadata checks, resolved settings, origins, observed inputs,
the plan and pending checks. Neither view rewrites the file. ``inspect`` accepts
unfinished field selections and reports available selectors. The
:ref:`terminal explorer <inspect-sample>` samples one file per source;
``inspect --cli`` and ``inspect --json`` report the full inventory.

``validate``, ``run`` and ``config show --effective`` accept
``--output-directory``, ``--cpus``, ``--overwrite`` or ``--no-overwrite``, and
``--log-level``. Command-line values override YAML values, which override defaults.
Command-line paths start at the launch directory; YAML paths remain relative to
the YAML file. Overwrite flags are mutually exclusive. For example:

.. code-block:: bash

   frameit validate frameit.yaml --cpus 1 --no-overwrite --log-level INFO

Keep fields, times, methods and other scientific selections in the YAML.

Capabilities and editor assistance
----------------------------------

.. code-block:: bash

   frameit capabilities
   frameit capabilities --json
   python -c "from importlib.resources import files; print(files('frameit').joinpath('schemas/config-v3.schema.json'))"

Use ``capabilities`` to check support, dependencies and method limits. Point your
editor's schema setting at the displayed JSON Schema file to check structure;
do not add it as a YAML control. Field names, units, geometry and scientific
eligibility still require input inspection and validation.

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

Missing required records fail by default. To retain a wholly absent field at the
first selected time, explicitly list ``allow_initial_gaps: [field_name]`` on its
GRIB/NetCDF source. The timestamp remains and the values stay missing. This needs:

* later records proving the same field identity, units and grid;
* that grid independently present at the initial time, including the vertical
  grid and sample-axis contexts for layered fields. A 2-D GRIB field needs
  horizontal geometry evidence, not an assumed equivalence of level types.

Later gaps, missing levels, ambiguous providers and absent tracker/derived support
still fail. The plan records permitted absences; it invents neither physical
records nor accumulation intervals. A field without a native time axis gains one
over its real samples before the missing initial value is added.

Temporal evidence remains field-owned. Model-grid GRIB coordinates use prefixes
such as ``u_GRIB_startStep``; interval fields use their own auxiliary time and
bounds. Missing interval evidence stays missing. Multi-field polar output does
not attach one field's bounds to shared ``time``; single-field output keeps its
native time-bounds link.

Variables and vertical levels
-----------------------------

Inside each source, ``variables.2d`` lists fields without a selectable vertical
axis. ``variables.3d`` lists fields with one. Time does not count as a spatial
axis. A flat list uses source names that identify one actual field.
A wrong category or unresolved identity fails with the affected source and field.

One optional ``variables.levels`` applies to all requested 3D fields and results
in that source, separately on each product's representation. It does not affect
2D fields. Omission keeps every level on each field's own grid.

Alternatively, use ``variables.3d.<group>: {names: [...], levels: {...}}``.
Each group has its own optional selector; source-wide ``variables.levels`` is
then forbidden. Use this form for distinct fields sharing a name, even if you
want only one, or for independent selections on different axes. References in
operations, metadata and products use ``<group>.<field>``. Grouped exports
keep that name. Groups must identify fields unambiguously; they do not choose
between providers. Pressure groups use ``isobaric``; coordinate metadata and
``levels.units`` carry the units, not the group name. See
:ref:`explicit-vertical-groups` for an example and
:doc:`../reference/vertical_levels` for selection and shared-axis limits.

Grouped and flat selectors both apply to each product's actual representation.
With ``sampling: mass``, values match mass labels, not native interface labels.
Use explicit indices for corresponding positions, or separate requests for
different physical-value selections.

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
``fa``. Supported AROME and SURFEX tangent Lambert FA use 6,371,229 m when
``earth_radius_m`` is omitted; declare the producer's radius for a nonstandard
grid. See :doc:`fa_geometry` for the checks and provenance.
No record-name convention establishes vertical meaning.
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

Native copying preserves stored samples, scientific definitions, units, grids,
masks and vector basis. Across files, stored definitions and units must remain
consistent, including file-wide wind-basis evidence inherited by the fields.
Conflicting files must be excluded or regenerated as a consistent sequence;
an unused wind-pair declaration cannot resolve that conflict.
Method-specific unit conversion does not relax the source requirement.
Copying one wind component needs neither its unselected companion
nor a basis declaration. An unused ``wind_pairs`` declaration does not rotate or
relabel native fields; selecting U/V does not request speed or radial/tangential wind.

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

Use source ``derived`` to map an output name to an admitted ``method`` and explicit
``inputs: {u: <source reference>, v: <source reference>}``. Inputs must be distinct
actual source fields; use qualified references for ambiguous native groups.
``wind_speed`` calculates horizontal speed. The experimental ``radial_wind``
and ``tangential_wind`` methods calculate outward and clockwise components,
respectively, on polar targets only.
Required inputs are loaded internally and exported only if requested.
Output-name collisions fail. Only results needed by requested products or another
requested operation are calculated. Each method retains its own preparation,
vertical grid and documented limits.

Radial/tangential requests admit AROME GRIB/NetCDF and Meso-NH NetCDF atmospheric
winds, not FA or ocean currents. Both inputs must be continuous, share a prepared
grid and have matching effective interpolation, sampling and strict missing-data
settings. Set preparation options on the inputs, not the result alias.
Renormalization is rejected, not replaced with strict sampling.
``model_grid: true`` includes every declared result, so combined runs must filter
model-grid fields explicitly and select these methods only in
``products.polar.fields``. Excluded definitions remain inactive.
Active component aliases must not collide with polar coordinates or selected
fields' quality variables, including ``radial_bearing`` and ``geometry_mapped``.
Choose another alias if metadata validation reports a generated-name collision.
See :doc:`../task_guides/scalars_and_vectors` for base-component declarations and
:ref:`explicit-polar-wind-methods` for signs, reference frame, origin and validation
limits.

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

For full-domain native copies only, a fixed centre and its time-association
setting are reported as unused. Each copy keeps its own selected times.
A crop, polar product or requested track still uses the centre and its
applicable checks.

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

Without a product ``fields`` map, field products use source ``variables`` and
``derived``. With a map, list exact input fields or defined derived results by
source. An input field does not need to be repeated in ``variables``. Validation
with input files rejects missing or ambiguous fields. Use a qualified name to keep
the levels declared for its group. A product-only dotted name fails if it
matches both a literal input name and a qualified group field. Unlisted fields
are not exported; required internal inputs can still be read.

Polar geometry
~~~~~~~~~~~~~~~

``products.polar`` requires ``radius_km`` and a region centre provider, not a
model-grid crop or model-grid export. Its input support is resolved separately.
Changing only the crop must not change polar sampling.
See :doc:`../task_guides/polar_sampling` for a complete instructional request.

Optional ``radial_step_km`` defaults to native source spacing and cannot be finer.
``frameit validate`` rejects a smaller step and reports the minimum
for the selected files. Use at least that value, or omit the setting. Schema-only
validation cannot determine it. A shared target uses the coarsest participating grid.
``azimuth_count`` is the only angular control. Omission chooses a count from
outer-ring native spacing. Rings run clockwise from north without a duplicate
endpoint. The exact outer radius is included; the final interval may be shorter.
These are point samples, not area averages or conservative remapping.

``shared_grid: true`` opts into common target coordinates. Automatic shared
spacing uses the coarsest participating source. Source masks, vertical axes,
quantities and time-association choices remain distinct.

Interpolation and field options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Polar sampling does not require or fill in ``kind``. Numeric fields default to
bilinear interpolation unless the input metadata, categorical flags or a field
declaration identifies them as categorical. Known categories require
nearest-neighbour. For unlabeled category codes, select ``interpolation: nearest``
explicitly to avoid blending categories. The selected method is recorded even
when ``kind`` is absent. A ``kind`` attribute, if present, must be
``continuous`` or ``categorical``. Native FA still has its own
:doc:`input contract <fa_inputs>`.

Sampled NetCDF fields and any wind companions used to prepare them must use
32- or 64-bit floating-point or integer types up to 32 bits, in storage and
after decoding. Wider integers can lose precision even in nearest-neighbour
sampling. Bilinear evaluates integer fields in float64 to retain fractional
results; it does not change model-grid values.

``missing_data_policy`` defaults to ``strict``.
Explicit ``renormalize`` requires ``min_valid_weight_fraction``. All-missing and
unmapped points stay missing; real zeroes stay zero.

Per-field options live under
``products.polar.field_options.<source>.<field>``. They accept
``interpolation: bilinear | nearest``, the missing-data controls above and
admitted ``sampling: native | mass``. They may target needed internal inputs,
but do not request exports. Unused or inapplicable options fail.
Nearest-neighbour does not use partial-stencil renormalization.
For an exported base field, optional ``units`` converts compatible stored values
before sampling, for example ``UM10: {units: "m s-1"}``. Omission preserves native
units. This does not inherit model-grid transforms or change sampling, vector
basis, masks or another product. Missing or incompatible source units fail.
Derived winds retain their method-defined m/s units; their inputs cannot use
this base-output override.
Optional base-field ``basis: earth`` uses the declared wind pair and rotation
method. Both components must have compatible real support and be collocated,
using explicit ``sampling: mass`` where needed. Only the requested component is
exported; compatible native units remain unchanged unless ``units`` is also set.
Omitted ``basis`` remains ``native``. This rotates physical vectors; it does not
subtract the centre's motion.

Scale conversions update ``valid_min``, ``valid_max``, ``valid_range`` and
``actual_range`` with the values. Packed fields carrying these limits require
explicitly unpacked, unambiguous metadata before conversion; FrameIt does not
guess whether those limits describe packed integers or decoded values.
Wind speed is the magnitude of U/V sampled at polar points, not an interpolation
of speed calculated earlier. Polar W stays native unless its own option requests
supported mass-point remapping.

Polar processing controls
~~~~~~~~~~~~~~~~~~~~~~~~~

Advanced polar ``processing`` keys are ``chunks``, ``max_target_points``,
``plan_cache.entries``, ``plan_cache.max_bytes``, ``source_halo_points``,
``weight_zero_tolerance`` and ``profile``. Insufficient support fails.
``profile`` enables performance measurements, not extra scientific diagnostics.
When false, optional polar timings and graph/RSS measurements are unmeasured;
cache activity and retention counters remain available.

Post-run diagnostics
--------------------

Omit ``diagnostics`` or set ``diagnostics: {}`` to leave post-run diagnostics
off. Extraction validates this block but does not read its selected fields or
compute its metrics. Adding it does not change the extraction request.
See :doc:`../task_guides/best_track_comparison` for exact selectors and an
optional local reference. The default diagnostic working-buffer budget is
256 MiB, not a process RSS cap. The default handle limit is four; the current
reader uses at most one input file at a time.

.. _output-resources-and-metadata:

Output
-------

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

Resources and metadata
-----------------------

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

Effective settings and run records distinguish defaults, input evidence,
automatic choices and overrides. Operational precedence and path bases are
defined under `Authored and effective views`_.
