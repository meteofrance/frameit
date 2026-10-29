Configuration file (YAML schema version 2)
============================================

After :doc:`installation <../getting_started/installation>`, use this reference
to select inputs, fields/levels, methods and products explicitly. The reference
environment already contains FrameIt and the FA/GRIB/NetCDF/polar stack; installing
an optional dependency does not select its scientific operations.

Create a model-specific, annotated configuration:

.. code-block:: bash

   frameit init arome
   frameit init mesonh --output chido.yaml
   frameit init arome --tracking prescribed_track
   frameit init arome --full --output full.yaml

Short templates show essential settings. ``--full`` renders all supported keys
and defaults from the same schema used by validation. ``--force`` is required to
replace an existing file. Initialization does not open datasets or load AI weights.

Minimal example
---------------

.. literalinclude:: ../../../example/config_file/conf_example.yml
   :language: yaml

Paths are relative to the YAML file, including explicit input inventories and
tracker auxiliary files. Model names are ``arome`` and ``mesonh``. Unknown keys,
duplicate keys, invalid types, and conflicting selections are rejected.

Identity and input
------------------

``schema_version`` must be ``2``. ``run.name`` names the analysis and exported
products; ``run.description`` is optional. ``metadata.extra`` holds user
annotations, not algorithm options. Optional ocean/wave identifiers belong in
``metadata.ocean_model`` / ``metadata.wave_model``.

``input.directory`` contains model files. Supply exactly one of:

* ``input.pattern``: a standard relative glob, or an exact filename;
* ``input.files``: explicit file paths, retaining their declared order.

``*`` matches text and ``?`` matches a single character; no timestep width is
imposed. ``input.exclude`` lists glob exclusions. For MesoNH, exclude the exact
000 timeseries filename where applicable rather than every filename containing
``000``. Explicit inventories also apply explicit exclusions. Missing inventory
entries fail rather than disappear. Discovery ordering is deterministic.

GRIB/NetCDF format is detected from file content; optional ``input.format`` can
declare ``grib`` or ``netcdf``. Native FA requires explicit ``format: fa`` and
its profile/declarations below. Mixed ordinary inventories and conflicting
declarations fail; complementary streams belong in separate named sources.
NetCDF defaults are
``input.netcdf.engine: h5netcdf`` and ``input.netcdf.chunks: {}`` (backend-preferred
lazy chunks). ``input.duplicate_time_policy`` is ``first`` or ``last``, default
``first``. GRIB retains its existing backend time ordering.

Named sources and exact times
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``input.sources`` maps source IDs to their own ``model``, ``input``, ``variables``
and optional ``polar`` settings. ``tracking.source`` names the reference source;
top-level ``model`` must match it. Variables belong inside each source, not a
shared top-level block. Source grids, vertical groups, masks and units remain
independent. See :doc:`fa_inputs` and ``example/config_file/coupled_fa.yaml``.

``input.time_alignment: common`` is the coupled default: select the exact
intersection of valid times, warn for each source losing times and retain every
exclusion in provenance/status. A prescribed track restricts the plan to its
exact matching times too. ``strict`` requires identical source times and track
coverage. No nearest-time interpolation or implicit interval conversion occurs;
ambiguous cycles and conflicting clocks fail.

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

* ``input.fa.backend`` defaults to ``epygram``. Legacy ``native`` is an accepted,
  deprecated alias of that same reader, with migration warnings. It does not
  select another decoder. Resolved YAML preserves an explicit alias for replay;
  inventories and decoder provenance record requested and effective backends.
* ``input.fa.python_executable`` defaults to null: FA workers use the active
  Python in fresh isolated processes. Omit it for the single reference environment.
  An explicit nonempty path selects a runtime containing FrameIt and the coherent
  FA stack. Paths are YAML-relative without dereferencing interpreter symlinks,
  including inside named sources. There is no automatic fallback interpreter.
  See :doc:`FA environment and troubleshooting <fa_environment>` for migration;
  the ``fa`` and compatibility ``fa-epygram`` extras select the same dependencies.
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
  silence is not proof of correct scaling.
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
named sources retain independent grids. Automatic inference can differ from the
old nominal spacing and consequently change search windows and sampling.

Advanced ``input.grid_spacing_m`` supplies a nominal scalar override in metres.
It does not bypass incompatible/anisotropic/nonuniform geometry checks. The
effective value and its source are retained in run provenance.

Tracking and extraction
-----------------------

For an optional first-time geographic search with ``wind_pressure``, set
``tracking.wind_pressure.initial_guess`` to a mapping of ``latitude``,
``longitude`` and ``search_radius_km``. See
:doc:`../tracker/pressure_wind_tracker` for scope, validation and failure policy.

``tracking.method`` defaults to ``wind_pressure``. Supported alternatives are
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

Geographic centres use degrees north/east. Wind-pressure controls
``search_half_width_km`` and ``refine_half_width_km`` default to 100 and 50 km:
they describe square half-widths, not circular radii.

``tracking.prescribed_track.file`` is required for prescribed tracking. Optional
``time_name``, ``latitude_name``, and ``longitude_name`` default to ``time``,
``latitude``, and ``longitude``. Matching is exact timestamp intersection;
nearest/interpolated matching is not introduced by this schema.

``tracking.utrack.weights_file`` is required for UTrack; ``use_gpu`` defaults to
false and ``batch_size`` to 16. The pressure-centroid convergence, motion, and
sampling controls are nested under ``tracking.pressure_centroid``; see
:doc:`/tracker/pressure_centroid` and ``frameit init arome --tracking pressure_centroid --full``.
For native-level Meso-NH input use ``frameit init mesonh --tracking pressure_centroid``;
the tracker documentation lists required fields and version-specific DIAG settings.

``domain.size_km: {x: 500, y: 500}`` gives full box widths in kilometres. Omit
``size_km`` for full-domain extraction. ``domain.edge_policy: pad_nan`` retains
centred geometry and pads outside the source domain; other policies are not
currently supported.

Variables and vertical levels
-----------------------------

Requests use native group/variable names:

.. code-block:: yaml

   variables:
     surface:
       names: [u10, v10, prmsl]
     isobaricInhPa:
       names: [u, v]
       levels: {values: [850, 700]}

``levels`` is ``all`` (also the omission default), ``stored``, ``physical``,
``{indices: [...]}``, or ``{values: [...]}``. Select exactly one strategy.
Indices are zero-based, nonnegative integers. Values and matching tolerances
use the native vertical
coordinate units, displayed by inspection. For a verified ``isobaricInhPa``
coordinate, 850 means hPa even though pressure calculations normalize to Pa.
Native selection precedes computational normalization. Contradictory pressure
group/unit metadata is rejected.

The ``stored`` and ``physical`` strategies, original stored-index semantics,
and W-to-mass target mapping are described in :ref:`wind-grid-contract`.

Polar computation
-----------------

``polar.enabled`` defaults to false; enabling requires a finite extraction box
and selected polar variables. ``polar.variables: all`` means every variable
selected for extraction, not every variable in source files. Alternatively use
a native group mapping with ``names`` lists that are subsets of extraction
requests. Polar processing inherits extracted levels.

``polar.radial_step_m`` is metres and defaults to resolved native spacing.
``polar.azimuth_step_deg`` is degrees; alternatively use integer
``polar.azimuth_count``. The two are mutually exclusive; omit both for automatic
outer-ring spacing. Analytical angles are endpoint-exclusive.

Other controls include ``interpolation_method`` (``bilinear`` or ``nearest_s2d``),
``missing_data_policy`` (``strict`` or ``renormalize``), weight-support thresholds,
source halo, ellipsoid, geometry point budget, plan-cache limits, ``chunks``, and
``profile``. ``--full`` exposes their authoritative defaults. Input chunks and
polar computation chunks are separate; NetCDF storage chunks remain backend-selected.

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
Use pair-specific declarations below to make each scientific choice explicit.
The legacy file-wide ``input.wind_reference_frame`` cannot describe mixed
model-level grid winds and Earth-relative surface winds; replace it with
``input.wind_pairs`` for such inputs.
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
       - group: surface
         u: UM10
         v: VM10
         reference_frame: earth
   output:
     cartesian:
       horizontal_winds: mass_earth  # native | mass_earth
       vertical_velocity: interfaces  # interfaces | mass
     polar:
       vertical_velocity: mass  # interfaces | mass

``input.wind_pairs`` is a list of explicit pairs scoped by native ``group``.
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
need no grid-to-Earth rotation. Generated templates show explicit pair
declarations for their selected winds and the three output defaults above.
See :ref:`wind-preparation-method` for equations, axis checks and limitations.

Output, logging, and precedence
----------------------------------

``output.directory`` sets the run root. ``output.export.netcdf``, ``.cartesian``,
and ``.polar`` default to true; writing still requires an available product.
Polar computation is independent of polar export. Compression defaults to level
1 with coordinate compression disabled. Other supported controls are ``engine``,
``format``, ``unlimited_time``, ``overwrite``, ``max_workers``,
``synchronous_export`` (default false), and ``institution``.

``execution.dask_scheduler`` is ``threads`` (default) or ``synchronous``.
``execution.dask_workers`` defaults to one effective worker;
``execution.native_threads`` defaults to one. ``output.max_workers: null``
resolves to the CPU budget divided by Dask/native thread counts. The strictest
machine, affinity and ``SLURM_CPUS_PER_TASK`` limit wins. Explicit requests that
exceed this budget fail; when a Slurm job omits CPUs per task, the budget uses
the conservative Slurm default of one CPU. Group export additionally caps
process count to group count and uses spawn. Synchronous export creates no pool.
These operational defaults can change performance relative to older releases;
they do not select scientific methods. Other optional backends may have their
own resource controls. See :doc:`/getting_started/hpc` for qualification.

``execution.require_complete_tracking`` defaults to false to retain existing
accepted-prefix behavior. When true, an incomplete tracker result fails before
export. The CLI exposes ``--require-complete-tracking``, ``--synchronous-export``,
``--max-workers``, ``--no-overwrite`` and ``--output-directory``. The output
override is relative to the launch directory; YAML paths remain YAML-relative.

``logging.level`` defaults to ``INFO``. Explicit CLI overrides take precedence
over YAML, which takes precedence over defaults. Omitted CLI flags do not reset
YAML values. Products go under ``products/``, indexes under ``cache/``, and logs
under the run root's logging layout. Each run saves a reloadable
``resolved-config.yaml`` and ``run-provenance.yaml`` containing geometry, inputs,
unit conversions/assumptions, and effective execution options.
Exclusive run-directory ownership rejects concurrent writers even with overwrite
enabled. ``--no-overwrite`` rejects prior artifacts before computation.
``run-status.yaml`` records completion separately from provenance.

Inspection, validation, and migration
----------------------------------------

.. code-block:: bash

   frameit validate                     # Defaults to frameit.yaml
   frameit validate chido.yaml --schema-only
   frameit inspect ./data --model mesonh
   frameit config show --resolved
   frameit run --dry-run
   frameit run
   frameit config migrate old.yml --output frameit.yaml --launch-directory /original/workdir

Dataset preflight checks files, required variables/levels, units, geometry,
geometry-dependent defaults, and output accessibility without computing scientific
fields. It can read metadata/coordinates but does not decode scientific payloads,
verify decode-time scaling or run a tracker. Dry runs print effective settings,
resource/sampling information and planned products without writing products;
they are not exact runtime/memory predictions or scientific approval.
Schema-only validation does not open data. ``config show`` displays resolved
schema settings; ``config show --resolved`` also performs metadata preflight.

Legacy flat YAML is rejected by ordinary loading with a migration instruction.
Migration reconstructs exact filename globs/exclusions, preserves physical values
and selections, resolves old paths against the original launch directory, and
reports removed ineffective fields. It retains the old nominal resolution as an
advanced override; remove that key deliberately to enable fully inferred spacing.
Source-unit validation still requires dataset preflight.

The migration command refuses an existing output configuration unless ``--force``
is explicit. Review the report and generated YAML, then run ``validate
--schema-only`` and metadata preflight on the selected inputs. Environment migration
is separate: use a fresh prefix as described in :doc:`fa_environment`, review any
explicit interpreter override, and retain all scientific declarations/budgets.

The internal Python ``SimulationConfig`` numerical interface retains flat field
names for existing integrations; those names are not accepted as schema-v2 YAML.
