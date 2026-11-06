Configuration file (YAML schema version 2.1)
============================================

Use this reference to select inputs, fields, levels, methods and products.
For a task route, start with :doc:`../task_guides/field_selection`,
:doc:`../task_guides/moving_region` or :doc:`../task_guides/coupled_inputs`.
For an annotated view of every available key and its alternatives, use
:doc:`../reference/all_keys`.

Create a model-specific, annotated configuration:

.. code-block:: bash

   frameit init arome
   frameit init mesonh --output chido.yaml
   frameit init arome --tracking prescribed_track
   frameit init arome --coupling nemo

Use ``frameit config show`` for complete defaults or
``config show --resolved`` for metadata-dependent settings. ``--force`` replaces
an existing configuration. Without it, generation refuses an existing destination.

.. _starter-catalogue:

Starter catalogue
------------------

Each command below writes ``frameit.yaml``. Adapt the inspected inputs and the
illustrative centres and widths to your data.
All explicitly disable polar sampling and refuse product overwrites.

.. list-table:: Named starters and equivalent compositions
   :header-rows: 1
   :class: config-table

   * - Named command
     - Equivalent command and selected quantities
   * - ``frameit init arome-pressure-wind``
     - ``frameit init arome``: GRIB u10/v10/prmsl with declared Earth winds
   * - ``frameit init mesonh-pressure-wind``
     - ``frameit init mesonh``: NetCDF UM10/VM10/MSLP with declared Earth winds
   * - ``frameit init arome-fixed-scalar``
     - ``frameit init arome --tracking fixed_box``: instructional scalar, 4 km full widths
   * - ``frameit init nemo-native``
     - ``frameit init nemo``: native T-grid votemper at stored index 0
   * - ``frameit init croco-native``
     - ``frameit init croco``: native temp/salt at sigma index 0 and surface zeta
   * - ``frameit init arome-nemo``
     - ``frameit init arome --coupling nemo``: independent prmsl/votemper, exact common labels
   * - ``frameit init mesonh-croco``
     - ``frameit init mesonh --coupling croco``: explicit SEA SST/SSS and native temp/salt

A named selector rejects **any** tracking/coupling flag. To compose, use a model
selector. Single models admit ``fixed_box/prescribed_track``; AROME/Meso-NH also
admit ``pressure_wind/pressure_centroid``. Coupling admits only AROME+NEMO and
Meso-NH+CROCO: fixed-box by default, prescribed-track for either, pressure-wind
additionally for Meso-NH+CROCO. Reverse/other starter combinations are rejected.

For example, ``frameit init mesonh --tracking fixed_box`` selects only MSLP;
``frameit init nemo --tracking prescribed_track`` selects the same native ocean
scalar with an explicit track file. Prescribed matching stays exact; replacing
instructional data for real use also requires a suitable real track.
``frameit init mesonh --coupling croco --tracking pressure_wind`` adds only the
atmospheric tracker's declared UM10/VM10/MSLP, not ocean current processing.
``init`` does not furnish guessed UTrack checkpoints or experimental multi-field
seeds: those methods remain runnable through explicit reviewed YAML.

The fixed-scalar resource is the same commented source used by the generator:

.. literalinclude:: ../../../src/frameit/templates/arome-fixed-scalar.yaml
   :language: yaml

Minimal example
---------------

.. literalinclude:: ../../../example/config_file/conf_example.yml
   :language: yaml

Paths are relative to the YAML file, including explicit input inventories and
tracker auxiliary files. Model names are ``arome``, ``mesonh``, ``nemo`` and ``croco``.
Ocean references admit NetCDF and fixed/prescribed centres only. Unknown keys,
duplicate keys, invalid types, and conflicting selections are rejected.

Identity and input
------------------

Set ``schema_version: "2.1"``. The value is a quoted string, not a number.
``run.name`` names the analysis and exported
products; ``run.description`` is optional. ``metadata.extra`` holds user
annotations, not algorithm options. Optional ocean/wave identifiers belong in
``metadata.ocean_model`` / ``metadata.wave_model``.
Defaults are ``run.name: analysis``, empty description/model-annotation strings and
``metadata.extra: {}``. ``model`` and ``schema_version`` must be explicitly supplied.

``input.directory`` contains model files. Supply exactly one of:

* ``input.pattern``: a standard relative glob, or an exact filename;
* ``input.files``: explicit file paths, retaining their declared order.

``input.exclude`` lists glob exclusions. For MesoNH, exclude the exact
000 timeseries filename where applicable rather than every filename containing
``000``. ``exclude`` must be a list, not null; an explicit ``files`` list must be
nonempty, even beside a pattern. Explicit inventories also apply explicit exclusions. Missing inventory
entries fail rather than disappear. Discovery ordering is deterministic.

GRIB/NetCDF format is detected from file content; optional ``input.format`` can
declare ``grib`` or ``netcdf``. Native FA requires explicit ``format: fa`` and
its profile/declarations below. Mixed ordinary inventories and conflicting
declarations fail; unlike grids/streams belong in separate named sources.
NetCDF defaults are
``input.netcdf.engine: h5netcdf`` and ``input.netcdf.chunks: {}`` (backend-preferred
lazy chunks). ``input.duplicate_time_policy`` is ``first`` or ``last``, default
``first``. GRIB retains its existing backend time ordering.

``input.netcdf.file_layout`` defaults to ``time_series``: prepare each snapshot
independently, then concatenate times. Every requested NetCDF field (including
required wind companions) must exist in each file. Missing later fields fail
rather than disappearing or being broadcast from an earlier file.
Choose ``variables`` explicitly for complementary variable files on the same
grid, times and forecast cycle. It merges selected fields and their coordinate
dependencies with exact alignment, without time concatenation or deduplication.
Duplicate selected field providers, inconsistent coordinates/depths/clocks and
mixed time-block/variable-shard inventories fail. See :doc:`input_files`.

``input.netcdf.engine`` accepts ``h5netcdf``, ``netcdf4`` or ``scipy``; the last
requires input compatible with SciPy's NetCDF reader. It does not select the
output writer. ``input.netcdf.chunks`` maps native dimensions to positive integers
or ``-1`` for a whole axis. ``input.netcdf.surfex_fields`` defaults to ``[]``;
only explicit supported Meso-NH SEA fields receive the producer-specific
interpretation in :doc:`ocean_netcdf`.

Named sources and exact times
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``input.sources`` maps source IDs to their own ``model``, ``input``, ``variables``
and optional ``polar`` settings. ``tracking.source`` names the reference source;
top-level ``model`` must match it. Variables belong inside each source, not a
shared top-level block. Source grids, vertical groups, masks and units remain
independent. See :doc:`fa_inputs` and ``example/config_file/coupled_fa.yaml``.
Parent input contains only ``sources`` and ``time_alignment``. Neither key is
allowed inside a source input, even if empty. Source input defaults are
independent; source polar settings inherit parent polar settings and then override
them, except that ``shared_target`` must agree globally. Source variable maps do
not inherit top-level selections.

``input.time_alignment: common`` is the coupled default: select the exact
intersection of valid times, warn for each source losing times and retain every
exclusion in provenance/status. A prescribed track restricts the plan to its
exact matching times too. ``strict`` requires identical source times and track
coverage. No nearest-time interpolation or implicit interval conversion occurs;
ambiguous cycles and conflicting clocks fail.

``preceding_hour`` is a separate, explicit AROME/NEMO NetCDF association with
required instantaneous/mean metadata and one-hour bounds. It is not a general
time-matching fallback; see :doc:`../concepts/time_support` and
:doc:`ocean_netcdf` for eligibility and changed time-label semantics.

``polar.shared_target: true`` selects common target coordinates for participating
sources; it defaults to false. Participating sources inherit the reference target
and must agree on explicitly selected target geometry. Native geometry is checked
before common sampling/budgets. The coarsest participating spacing supplies the
default shared radial step; an explicit step must not be finer than any participant.
Sampling methods and physical masks remain source-specific. See
:doc:`Coupled atmosphere/surface sampling <fa_surface>`.

Native FA settings
~~~~~~~~~~~~~~~~~~

FA sources require ``model: arome`` and ``input.format: fa``. The supported
profiles are ``arome_history`` and ``surfex_history``; these do not admit arbitrary
producers or layouts. The full input, source/type/time, geometry and scaling
contracts are in :doc:`fa_inputs`.

* ``input.fa.backend`` is ``epygram``. Inventories and provenance record the reader.
* ``input.fa.python_executable`` defaults to null: FA workers use the active
  Python in fresh isolated processes.
  An explicit nonempty path selects a runtime containing FrameIt and the coherent
  FA stack. Paths are YAML-relative without dereferencing interpreter symlinks,
  including inside named sources. There is no automatic fallback interpreter.
  See :doc:`FA environment and troubleshooting <fa_environment>` for setup.
* ``subdomain`` is ``CI`` (default) or ``C``; the spectral extension is excluded.
  Projected FA requires explicit positive ``earth_radius_m`` based on producer
  evidence, not a fitted/default Earth model.
* ``expected_source`` defaults to ``{}`` and accepts exact native assertions for
  ``PROGRAM``, ``VERSION``, ``BUG``, ``MASDEV`` and ``BUGFIX``. Missing or conflicting
  native facts fail; assertions do not supply or overwrite source identity.
* ``field_metadata`` declares source ``units``, ``kind: continuous|categorical``
  and ``temporal_kind: instantaneous`` for each selected record or logical cube
  variable. These are not requested unit conversions. Native facts precede user
  completion of unresolved meaning. ``allow_unscaled`` defaults to false; a
  missing-native-scaling warning fails unless an explicit justified identity
  fallback is permitted. Permission/observed fallback and warnings are recorded;
  see :doc:`fa_contracts` for scaling observations and limits.
  Optional ``long_name`` and ``standard_name`` are strings; use a standard name
  only when its definition matches the actual quantity.
* ``native_cubes`` defaults to ``{}``. It associates exact native records with
  declared full/interface positions and centre sampling, retaining original
  labels/indices and checked A/B/reference-pressure metadata. It does not infer
  pressure/height, staggering, vector basis or scientific field identity. See
  :doc:`Native atmospheric levels and cubes <fa_atmosphere>`.
* ``max_points`` defaults to 20,000,000 stored points and ``timeout_seconds`` to
  120 per transaction. Even a tiny crop may require a full native horizontal
  record. These are point/time bounds, not an exact peak-memory guarantee.

Accumulated/averaged FA, implicit deaccumulation/rates, spectral execution,
packed support-map reconstruction and unqualified physical/vertical operations
remain unsupported. Header readability is not decode eligibility.

Native grid geometry
--------------------

Grid spacing is inferred before tracker construction. Explicit length units on
native projected coordinates take precedence; otherwise WGS84 geodesic distances
are sampled across both geographic axes. The report retains separate X/Y median
spacings, variability, sources, and the scalar effective spacing.

Current scalar-spacing algorithms reject X/Y differences greater than 10% and
within-axis spacing variation greater than 20%; these are implementation support
limits, not claims about arbitrary curvilinear-grid accuracy. Within a source's
time sequence, selected inputs must have compatible geographic grids; separate
named sources retain independent grids. The resolved spacing determines search
windows and polar sampling defaults.

Advanced ``input.grid_spacing_m`` supplies a nominal scalar override in metres.
It does not bypass incompatible/anisotropic/nonuniform geometry checks. The
effective value and its source are retained in run provenance.

Tracking and extraction
-----------------------

For an optional first-time geographic search with ``pressure_wind``, set
``tracking.pressure_wind.initial_guess`` to a mapping of ``latitude``,
``longitude`` and ``search_radius_km``. See
:doc:`../tracker/pressure_wind_tracker` for scope, validation and failure policy.

``tracking.method`` defaults to ``pressure_wind``. Supported alternatives are
``fixed_box``, ``prescribed_track``, ``pressure_centroid`` (AROME and Meso-NH), and
``utrack``. An experimental ``multifield_vortex`` native-grid adaptation of
Marchok's ALL_NO_THICK configuration supports both models; see
:doc:`/tracker/multifield_vortex` for its required seed, initial motion,
500/700/850-hPa inputs, MNH height convention and qualification limits.
Method-specific controls belong under the matching section:

.. code-block:: yaml

   tracking:
     method: fixed_box
     fixed_box:
       center: {latitude: -18.0, longitude: 58.0}

Geographic centres use degrees north/east. Pressure-wind controls
``search_half_width_km`` and ``refine_half_width_km`` default to 100 and 50 km:
they describe square half-widths, not circular radii.

``tracking.prescribed_track.file`` is required for prescribed tracking. Optional
``time_name``, ``latitude_name``, and ``longitude_name`` default to ``time``,
``latitude``, and ``longitude``. Matching uses exact timestamp intersection.

``tracking.utrack.weights_file`` is required for UTrack; ``use_gpu`` defaults to
false and ``batch_size`` to 16. The pressure-centroid convergence, motion, and
sampling controls are nested under ``tracking.pressure_centroid``; see
:doc:`/tracker/pressure_centroid` and ``frameit init arome --tracking pressure_centroid``.
For native-level Meso-NH input use ``frameit init mesonh --tracking pressure_centroid``;
the tracker documentation lists required fields and version-specific DIAG settings.

``domain.width_km: {x: 500, y: 500}`` gives full box widths in kilometres. Omit
``width_km`` for full-domain extraction. ``domain.edge_policy: pad_nan`` retains
centred geometry and pads outside the source domain; other policies are not
currently supported.

Variables and vertical levels
-----------------------------

Requests use native group/variable names:

``fields_2d`` groups fields with no selectable vertical axis. They need not be
at the ground: sea-level pressure and 10-m winds can both belong here. Vertical
groups such as ``isobaricInhPa`` or ``level`` use their source coordinate names.
The public group selects the existing ``surface`` product group; output filenames
and scientific definitions are unchanged.

.. code-block:: yaml

   variables:
     fields_2d:
       names: [u10, v10, prmsl]
     isobaricInhPa:
       names: [u, v]
       levels: {values: [850, 700]}

``levels`` is ``stored`` (the omission default), ``physical``,
``{indices: [...]}``, or ``{values: [...]}``. Select exactly one strategy.
Indices are zero-based, nonnegative integers. Values and matching tolerances
use the native vertical
coordinate units, displayed by inspection. For a verified ``isobaricInhPa``
coordinate, 850 means hPa even though pressure calculations normalize to Pa.
Native selection precedes computational normalization. Contradictory pressure
group/unit metadata is rejected.

The ``stored`` and ``physical`` strategies, original stored-index semantics,
and W-to-mass target mapping are described in :ref:`wind-grid-contract`.
``physical`` selects an evidenced non-halo index range; it does not diagnose
pressure, altitude or ocean depth. An omitted group selects no fields from it.

Polar computation
-----------------

``polar.enabled`` defaults to false; enabling requires a finite extraction box
and selected polar variables. ``polar.variables: extracted`` (default) means every variable
selected for extraction, not every variable in source files. Alternatively use
a native group mapping with ``names`` lists that are subsets of extraction
requests. Polar processing inherits extracted levels.

``polar.radial_step_m`` is metres and defaults to resolved native spacing.
``polar.azimuth_step_deg`` is degrees; alternatively use integer
``polar.azimuth_count``. The two are mutually exclusive; omit both for automatic
outer-ring spacing. The radial step cannot be finer than native spacing; angular
steps must be in (0,120] degrees and counts at least 3. Analytical angles are
endpoint-exclusive. The actual radii include half the shorter full box width;
the last radial interval can be shorter than the requested step.

The remaining keys are under ``polar``:

.. list-table:: Sampling, support and execution controls
   :header-rows: 1
   :class: config-table

   * - Key / default
     - Meaning and constraint
   * - ``interpolation_method: bilinear``
     - ``bilinear`` or explicit ``nearest_s2d`` point sampling.
   * - ``missing_data_policy: strict``
     - All contributors finite; ``renormalize`` instead uses declared valid-weight support.
   * - ``min_valid_weight_fraction: 0.5``
     - Fraction in [0,1] for renormalization. Unmapped/all-missing points stay NaN.
   * - ``weight_zero_tolerance: 1.0e-14``
     - Remove negligible absolute stencil weights; range [0,1e-6), not a field-value cutoff.
   * - ``source_halo_points: 1``
     - Positive integer native neighbours beyond the crop; no extrapolation.
   * - ``ellipsoid: WGS84``
     - Target geodesic ellipsoid accepted by ``pyproj.Geod``; source geometry is checked separately.
   * - ``max_points: 2000000``
     - Positive integer time × radius × angle geometry budget, not a peak-memory quota.
   * - ``plan_cache: {entries: 8, max_bytes: 134217728}``
     - Nonnegative retained-plan count/estimated bytes. Zero disables retention.
   * - ``chunks: {}``
     - Polar output dimensions → positive integer or ``-1``. Internal ``x_box/y_box/locations/dummy/theta_deg`` names are not valid overrides.
   * - ``profile: false``
     - Boolean timing instrumentation, not extra scientific diagnostics.

Input chunks, polar computation chunks and output storage chunks are separate;
see :doc:`../task_guides/storage_and_resources`. Full equations, quality flags
and effective angular spacing are in :doc:`../polar_projection/xESMF_proj`.

Bilinear is the production default for continuous point samples, without an
area-budget conservation guarantee. Categorical fields require an explicit
appropriate method; experimental conservative/patch/vector-transport methods
are not chosen automatically. Missing values and physical zeroes remain distinct.

Units and scientific contracts
------------------------------

Unit-bearing keys accept numbers in the named units, not strings such as
``"2.5 km"``. Conversions change values and metadata together. Scientific wind
inputs normalize to ``m s-1``, calculation angles to radians, and pressure to Pa.
Geopotential (``m2 s-2``) is distinct from height in metres. Polar output ``rr`` /
``rr_km`` remain kilometres, ``theta`` radians, and ``theta_deg`` degrees.
Cartesian distance offsets explicitly carry kilometre units; grid indices are
dimensionless.

Missing geographic/wind units follow documented AROME/MesoNH adapter contracts
and are recorded. Unsupported or incompatible declarations fail. Geographic
coordinates are normalized before tracking as well as polar projection.
Use ``input.wind_pairs`` for each selected horizontal pair, including mixed
model-level grid winds and Earth-relative surface winds.
Pass-through scalar fields preserve their source units; computationally prepared
winds and derived products carry normalized units.

Explicit wind pairs and output representation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See :ref:`wind-grid-contract` for diagrams, defaults and scientific meaning.
This Meso-NH declaration distinguishes model-level grid winds from
Earth-relative surface winds:

.. code-block:: yaml

   input:
     wind_pairs:
       - group: level
         u: UT
         v: VT
         reference_frame: grid
         rotation: {method: mesonh_projection}
       - group: fields_2d
         u: UM10
         v: VM10
         reference_frame: earth
   output:
     cartesian:
       horizontal_vectors: earth_centered  # native | earth_centered
       vertical_velocity: interfaces  # interfaces | mass
     polar:
       vertical_velocity: mass  # interfaces | mass

``input.wind_pairs`` is a list of explicit pairs scoped by native ``group``.
It defaults to ``[]``; no declared basis or rotation is selected by that empty list.
Choose ``reference_frame: earth`` or ``grid`` based on the actual source.
Grid-relative pairs require one declared rotation method:

* ``mesonh_projection``: use the angle
  ``BETA - RPK * wrap(longitude - LON0)`` in degrees, with the longitude
  difference wrapped to [-180, 180). This requires finite projection metadata
  and excludes Meso-NH Cartesian geometry;
* ``geolocation``: derive the grid basis from the geographic grid geometry;
* ``coordinate``: use a named angle, for example
  ``rotation: {method: coordinate, coordinate: grid_rotation}``.
  The angle measures counterclockwise rotation from geographic east to grid x;
  its units must be declared and convertible to radians.

There is no ``auto`` frame or method. Validate the declaration against available
GRIB component flags and CF wind metadata (including standard names). A conflict,
inconsistent pair, missing angle, unsupported projection or unusable geometry
must fail with the affected pair identified. Do not silently change reference
frame or fall back from one rotation method to another. Earth-relative pairs
need no grid-to-Earth rotation.
See :ref:`wind-preparation-method` for equations, axis checks and limitations.

Output, logging, and precedence
----------------------------------

``output.directory`` sets the run root (default ``./output``). ``output.export.enabled``, ``.cartesian``,
and ``.polar`` default to true; writing still requires an available product.
Polar computation is independent of polar export. Compression defaults to level
1 with coordinate compression disabled. Other supported controls are ``backend``,
``netcdf_format``, ``unlimited_time``, ``overwrite``, ``max_workers``,
``synchronous_export`` (default false), and ``institution``.
``unlimited_time`` defaults to true. Compression levels are integers from 0 to 9.

``output.backend`` selects ``netcdf4`` (default), ``h5netcdf``, or ``zarr``.
The first two write NetCDF files; ``zarr`` writes sharded Zarr v3 directory
stores with the same products and ``.zarr`` instead of ``.nc``.
``output.netcdf_format`` accepts only ``NETCDF4`` (the default), including when
the selected backend is Zarr; it does not control Zarr encoding.
``output.unlimited_time`` is unused for Zarr. Zarr export does not support append/resume.

``output.overwrite`` defaults to **true** in the runtime; all shipped starters
explicitly set it to **false**. It never authorizes source-data replacement.
Use a fresh output directory for each attempt. ``output.institution`` defaults
to ``LACy, Université de La Réunion, CNRS, Météo-France``; set appropriate product
attribution for your run.

For Zarr only, ``output.zarr_chunk_size`` and ``output.zarr_shard_size`` are
optional mappings from dimension names to positive integer element counts.
Both default to ``{}``, meaning the documented automatic layout. For example::

    output:
      backend: zarr
      zarr_chunk_size: {time: 1, y_box: 128, x_box: 128}
      zarr_shard_size: {time: 8, y_box: 512, x_box: 512}

Use the actual output dimension names; polar axes are ``rr`` and ``theta``.
Dimensions absent from a particular product are ignored. Explicit shard sizes
must be multiples of explicit chunk sizes. See :ref:`sharded-zarr-output` for
the difference between chunks and shards, defaults and override rules.

``output.export.enabled`` and the CLI ``--no-export`` are the overall
product-export gate for **either** backend. ``--no-export-cartesian`` and
``--no-export-polar`` control the respective product families. Compression level 1 is
lossless gzip for Zarr (0 disables compression); coordinate compression remains
opt-in.

``execution.dask_scheduler`` is ``threads`` (default) or ``synchronous``.
``execution.dask_workers`` defaults to one effective worker;
``execution.native_threads`` defaults to one. ``output.max_workers: null``
resolves to the CPU budget divided by Dask/native thread counts. The strictest
machine, affinity and ``SLURM_CPUS_PER_TASK`` limit wins. Explicit requests that
exceed this budget fail; when a Slurm job omits CPUs per task, the budget uses
the conservative Slurm default of one CPU. Group export additionally caps
process count to group count and uses spawn. Synchronous export creates no pool.
See :doc:`/getting_started/hpc` for batch resource checks.

``execution.require_complete_tracking`` defaults to false, allowing an accepted
track prefix. When true, an incomplete tracker result fails before
export. The CLI exposes ``--require-complete-tracking``, ``--synchronous-export``,
``--max-workers``, ``--no-overwrite`` and ``--output-directory``. The output
override is relative to the launch directory; YAML paths remain YAML-relative.

``logging.level`` accepts ``DEBUG/INFO/WARNING/ERROR`` and defaults to ``INFO``.
Explicit CLI overrides take precedence
over YAML, which takes precedence over defaults. Omitted CLI flags do not reset
YAML values. Products go under ``products/``, indexes under ``cache/``, and logs
under the run root's logging layout. Each run saves a reloadable
``resolved-config.yaml`` and ``run-provenance.yaml`` containing geometry, inputs,
unit conversions/assumptions, and effective execution options.
Exclusive run-directory ownership rejects concurrent writers even with overwrite
enabled. ``--no-overwrite`` rejects prior artifacts before computation.
``run-status.yaml`` records completion separately from provenance.

Inspection and validation
----------------------------------------

.. code-block:: bash

   frameit validate                     # Defaults to frameit.yaml
   frameit validate chido.yaml --schema-only
   frameit inspect ./data --model mesonh
   frameit config show --resolved
   frameit run --dry-run
   frameit run

Dataset preflight checks files, required variables/levels, units, geometry,
geometry-dependent defaults, and output accessibility without computing scientific
fields. It can read metadata/coordinates but does not decode scientific payloads,
verify decode-time scaling or run a tracker. Dry runs print effective settings,
resource/sampling information and planned products without writing products;
they are not exact runtime/memory predictions or scientific approval.
Schema-only validation does not open data. ``config show`` displays resolved
schema settings; ``config show --resolved`` also performs metadata preflight.

Defaults and omissions
----------------------

Omitted keys receive schema defaults; explicit YAML values override them, then
explicit CLI options override YAML. ``null`` means automatic/unset only for keys
that admit it (for example grid spacing and worker caps). It is not zero, an
empty variable list or a substitute for a required centre, path or scientific
declaration. Booleans do not count as numeric sizes/counts.

Model presets supply the selected tracker's required internal inputs. User
extraction selections remain separate. Method-specific defaults and constraints
are canonical in :doc:`../tracker/pressure_centroid`,
:doc:`../tracker/multifield_vortex` and :doc:`../tracker/utrack`; those numerical
controls do not enable optional polar exports. Named source inputs use independent
defaults, while source polar settings inherit and override the parent as described
above. Use ``config show --resolved`` and the saved effective configuration to
inspect the resulting choices and their origins.
