Configuration file (YAML)
=========================

FrameIt is configured through a YAML file that defines

i. the simulation metadata and input file naming convention,
ii. tracking and subdomain options, 
iii. the list of requested variables and their vertical selections, 
iv. output paths 
v. polar projection settings.

The configuration is typically passed to the main entry point (e.g., ``scripts/main.py``) and read by the simulation class.

General syntax
--------------

- The file must be valid YAML (indentation is significant).
- Lists use ``[a, b, c]`` or dash items.
- Strings should be quoted when they contain special characters (e.g., ``+``).

Simulation identification and input files
-----------------------------------------

``simulation_name``
   Human-readable name of the case (used for logging and outputs).

``atm_model``, ``ocean_model``, ``wave_model``
   Identifiers of the model components. Use the string ``"None"`` if the component is not used except for ``atm_model`` which is mandatory.

``resolution``
   Horizontal grid spacing (in meters) of the atmospheric model output, used by FrameIt for diagnostics and gridding assumptions.

``comment``
   Free text field, intended for bookkeeping.

File naming convention
~~~~~~~~~~~~~~~~~~~~~~
FrameIt expects input files to follow a strict naming pattern with a 3-digit timestep
counter (``NNN``, e.g., ``001``, ``002``, ..., ``999``) inserted in the filename:

.. code-block:: text

   <file_name_prefix><file_name><NNN><file_name_suffix>.<file_type>

.. note::
   ``NNN`` is not a configuration parameter — it represents the 3-digit timestep counter
   that FrameIt automatically matches using a wildcard. You only need to configure the
   four parameters below so that the pattern correctly describes your files.

Breaking down the example ``arome_BATSIRAI_20220201+0010P.grib``:

.. list-table::
   :header-rows: 1
   :widths: 25 30 45

   * - Parameter
     - Value
     - Note
   * - ``file_name_prefix``
     - *(empty)*
     - Optional, can be left empty
   * - ``file_name``
     - ``arome_BATSIRAI_20220201+``
     - Core name; quote strings containing special characters such as ``+``
   * - ``file_name_suffix``
     - ``0P.``
     - Optional, placed after the timestep counter and before the extension
   * - ``file_type``
     - ``grib``
     - File extension without leading dot (e.g., ``grib``, ``nc``)

The full sequence of files would then look like:

.. code-block:: text

   arome_BATSIRAI_20220201+0010P.grib
   arome_BATSIRAI_20220201+0020P.grib
   arome_BATSIRAI_20220201+0030P.grib
   ...


Debug flag
----------

``DEBUG``
   Boolean flag controlling verbosity and extra checks.


Minimal example
---------------

.. code-block:: yaml

   simulation_name: "BASTSIRAI"
   file_name_prefix: ""
   file_name: "arome_BATSIRAI_20220201+"
   file_name_suffix: "0P."
   file_type: "grib"
   atm_model: "AROME"
   ocean_model: "None"
   wave_model: "None"
   resolution: 2500
   comment: "TEST_GRIB - OPER-E"
   DEBUG: true

Tracking options
----------------

FrameIt supports multiple tracking approaches. The selected method is specified by:

``tracking_method``
   One of:

   - ``"fixed_box"``: use a fixed analysis box, centered on a given location define by ``fix_subdomain_center`` (see :doc:`/tracker/fixed_box`).
   - ``"prescribed_track"``: use an external track file created beforehand by the user (see :doc:`/tracker/prescribed_track`).
   - ``"wind_pressure"``: track based on wind and pressure extrema (see :doc:`/tracker/pressure_wind_tracker`).
   - ``"pressure_centroid"``: adaptive, storm-motion-relative 2-km pressure centroid (see :doc:`/tracker/pressure_centroid`).
   - ``"u-track"``: AI based tracker (see :doc:`/tracker/utrack`).

Prescribed track case
~~~~~~~~~~~~~~~~~~~~~

If ``tracking_method`` is set to ``"prescribed_track"``, you need to provide:

``prescribed_track_file``
   Absolute path to a NetCDF file containing the prescribed cyclone trajectory.

.. code-block:: yaml

   tracking_method: "prescribed_track"
   prescribed_track_file: "/path/to/track_file.nc"

More detail in the dedicated part : 

Fixed subdomain case
~~~~~~~~~~~~~~~~~~~~

FrameIt can restrict computations to a moving or fixed subdomain (analysis box). \
For a fixed-center box, specify:

``fix_subdomain_center``
   Center of the subdomain as ``[lat, lon]`` (in degrees).

All cases
~~~~~~~~~

Whatever the track method you choose, you need to specify the horizontal dimension of the box you want to extract by filling 

``x_boxsize_km``, ``y_boxsize_km``
   Sides box size along zonal and meridional directions (in kilometers).

Example :
.. code-block:: yaml

   fix_subdomain_center: [-17.5, 60]
   x_boxsize_km: 200.0
   y_boxsize_km: 200.0

Requested variables (user)
--------------------------

This part deals with the variables requested by the user.
The variables are  stored into a dictionnary by vertical coordinate as follow:

- ``heightAboveGround``
- ``level``
- ``isobaricInhPa``
- ``surface``

Each group defines:

- ``variables``: list of variable names to extract.
- a vertical coodinate selection strategy when relevant.

Vertical selection keys
~~~~~~~~~~~~~~~~~~~~~~~

``level_selection``
   Controls which vertical levels are extracted. Supported values:

   - ``"all"``: extract all available levels.
   - ``"indices"``: extract levels by index positions.
   - ``"values"``: extract levels by physical values (e.g., pressure in hPa).

``level_indices``
   List of indices (0-based). Use only when ``level_selection: "indices"``.

``level_values``
   List of physical values. Use only when ``level_selection: "values"``.

Example: variables on height above ground (selected by indices)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   requested_variables_user:
     heightAboveGround:
       variables: ["u", "v", "t", "r", "tke"]
       level_selection: "indices"
       level_values: []
       level_indices: [0, 2, 5]

Example: isobaric variables (selected by pressure values)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   requested_variables_user:
     isobaricInhPa:
       variables: ["u", "v"]
       level_selection: "values"
       level_values: [1000, 850, 400]
       level_indices: []

Example: surface or horizontal 2D variables (no vertical selection)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   requested_variables_user:
     surface:
       variables: ["u10", "v10", "prmsl", "sshf", "slhf"]

Output directories
------------------

``simulation_output_dir``
   Path where the raw model files are located.

``frameit_output_dir``
   Run root. FrameIt writes NetCDF outputs in ``products/``, logs in ``logs/``,
   and GRIB index caches in ``cache/`` beneath this directory.

.. code-block:: yaml

   simulation_output_dir: "/path/to/simulation/files"
   frameit_output_dir: "/path/to/FRAMEIT/outputs"

Polar projection diagnostics (optional)
---------------------------------------

FrameIt can project the selected variable in a polar coordinate system around the cyclone center. \ Enable this feature with:

``compute_polar_proj``
   Boolean switch to activate polar projection computations.

``radial_resolution``
   Radial sampling step (in meters) used in the polar grid.

``azimuthal_resolution``
   Maximum angular step in degrees, at most 120. The effective count is
   ``ceil(360 / azimuthal_resolution)`` and spacing is exactly ``360/count``.
   Omit it for an explicit count or automatic outer-ring spacing.

``polar_n_theta``
   Optional integer angular count of at least 3. Conflicting count and step
   requests are rejected. With neither set, the count is
   ``max(3, ceil(2*pi*rmax_km/dr_km))``; there is no implicit 10-degree default.

``polar_max_points``
   Maximum target geometry points across all times (default 2,000,000), checked
   before allocation. Larger grids require an explicit increase.

``polar_missing_data_policy``
   ``strict`` (default) requires every contributing source value to be finite.
   ``renormalize`` enables interpolation over valid weights with the support
   threshold below; it does not extrapolate or reconstruct missing sectors.

``polar_min_valid_weight_fraction``
   Minimum support fraction for renormalized values, in [0, 1], default 0.5.
   All-missing stencils remain invalid even with a zero threshold.

``polar_weight_zero_tolerance``
   Absolute numerical zero coefficient tolerance, default 1.0e-14, in
   [0, 1.0e-6). Removed coefficients do not contribute to weighting or validity.

``polar_source_halo_points``
   Native points added to each actual extraction half-width for polar input,
   default 1, at least 1. This does not enlarge Cartesian output products.

``polar_ellipsoid``
   Ellipsoid identifier accepted by pyproj Geod, default ``WGS84``. It defines
   target geodesics; ESMF interpolation geometry is spherical longitude/latitude.

``polar_regrid_cache_size`` / ``polar_regrid_cache_max_bytes``
   In-memory plan LRU limits: default eight entries and 134217728 estimated
   geometry/weight-array bytes. Zero disables retention. The key includes real
   geometry/options, not just shape; dynamic masks are applied separately.

``polar_output_chunks``
   Optional dimension-to-size mapping for lazy output arrays, for example
   ``{rr: 32, theta: -1, time: 1, level: 4}``. Sizes are positive or -1 for a
   whole axis. Without overrides, backend blocks contain at most 32 whole rings.

``polar_profile``
   Optional graph-size and process RSS high-water observations, default false.
   Plan counts and construction/application timings are always reported.

``polar_variables``
   List of variables to project on the polar grid.

.. code-block:: yaml

   compute_polar_proj: true
   radial_resolution: 2500
   polar_n_theta: 64
   polar_max_points: 2000000
   polar_missing_data_policy: strict
   polar_source_halo_points: 1
   polar_variables:
      heightAboveGround:
         variables: [u, v, t]
      surface:
         variables: [u10, v10, prmsl]

Analytical outputs contain one uniform cycle without a duplicate angular
endpoint. See :doc:`/polar_projection/xESMF_proj` for plotting closure,
azimuthal means, Fourier conventions and sampling diagnostics.

Additional simulation parameters (optional)
-------------------------------------------

``simulation_parameter``
   Free-form mapping to pass extra parameters not explicitly represented by the schema. Keep empty if not used.

.. code-block:: yaml

   simulation_parameter: {}

Common pitfalls
---------------

- **Case sensitivity**: variable group names and variable names may be case-sensitive depending on the backend reader.
- **Indentation**: YAML indentation must be consistent (spaces only).
- **Empty lists**: keep ``[]`` for unused keys to avoid ambiguity.
- **Paths**: prefer absolute paths for ``prescribed_track_file`` and output directories in HPC environments.
