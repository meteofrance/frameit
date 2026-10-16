Configuration file (YAML schema version 2)
============================================

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

Format is detected from file content. Optional ``input.format`` is ``grib`` or
``netcdf``; mixed inputs and conflicting declarations fail. NetCDF defaults are
``input.netcdf.engine: h5netcdf`` and ``input.netcdf.chunks: {}`` (backend-preferred
lazy chunks). ``input.duplicate_time_policy`` is ``first`` or ``last``, default
``first``. GRIB retains its existing backend time ordering.

Native grid geometry
--------------------

Grid spacing is inferred before tracker construction. Explicit length units on
native projected coordinates take precedence; otherwise WGS84 geodesic distances
are sampled across both geographic axes. The report retains separate X/Y median
spacings, variability, sources, and the scalar effective spacing.

Current scalar-spacing algorithms reject X/Y differences greater than 10% and
within-axis spacing variation greater than 20%; these are implementation support
limits, not claims about arbitrary curvilinear-grid accuracy. All selected inputs
must have compatible geographic grids. Automatic inference can differ from the
old nominal spacing and consequently change search windows and sampling.

Advanced ``input.grid_spacing_m`` supplies a nominal scalar override in metres.
It does not bypass incompatible/anisotropic/nonuniform geometry checks. The
effective value and its source are retained in run provenance.

Tracking and extraction
-----------------------

``tracking.method`` defaults to ``wind_pressure``. Supported alternatives are
``fixed_box``, ``prescribed_track``, ``pressure_centroid`` (AROME and Meso-NH), and
``utrack``. Method-specific controls belong under the matching section:

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

Native group/variable names are preserved:

.. code-block:: yaml

   variables:
     surface:
       names: [u10, v10, prmsl]
     isobaricInhPa:
       names: [u, v]
       levels: {values: [850, 700]}

``levels`` is ``all`` (also the omission default), ``{indices: [...]}``, or
``{values: [...]}``. Select exactly one strategy. Indices are zero-based,
nonnegative integers. Values and matching tolerances use the native vertical
coordinate units, displayed by inspection. For a verified ``isobaricInhPa``
coordinate, 850 means hPa even though pressure calculations normalize to Pa.
Native selection precedes computational normalization. Contradictory pressure
group/unit metadata is rejected.

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
``input.wind_reference_frame`` defaults to earth-relative; explicit source
metadata has precedence. Grid-relative winds require a valid rotation coordinate.
Pass-through scalar fields preserve their source units; computationally prepared
winds and derived products carry normalized units.

Output, logging, and precedence
----------------------------------

``output.directory`` sets the run root. ``output.export.netcdf``, ``.cartesian``,
and ``.polar`` default to true; writing still requires an available product.
Polar computation is independent of polar export. Compression defaults to level
1 with coordinate compression disabled. Other supported controls are ``engine``,
``format``, ``unlimited_time``, ``overwrite``, ``max_workers``, and ``institution``.

``logging.level`` defaults to ``INFO``. Explicit CLI overrides take precedence
over YAML, which takes precedence over defaults. Omitted CLI flags do not reset
YAML values. Products go under ``products/``, indexes under ``cache/``, and logs
under the run root's logging layout. Each run saves a reloadable
``resolved-config.yaml`` and ``run-provenance.yaml`` containing geometry, inputs,
unit conversions/assumptions, and effective execution options.

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
fields. Dry runs do not write products. Schema-only validation does not open data.

Legacy flat YAML is rejected by ordinary loading with a migration instruction.
Migration reconstructs exact filename globs/exclusions, preserves physical values
and selections, resolves old paths against the original launch directory, and
reports removed ineffective fields. It retains the old nominal resolution as an
advanced override; remove that key deliberately to enable fully inferred spacing.
Source-unit validation still requires dataset preflight.

The internal Python ``SimulationConfig`` numerical interface retains flat field
names for existing integrations; those names are not accepted as schema-v2 YAML.
