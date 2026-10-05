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
   - ``"u-track"``: AI based tracker (see :doc:`/tracker/utrack`).

Pressure-wind case
~~~~~~~~~~~~~~~~~~

If ``tracking_method`` is set to ``"wind_pressure"``, you can optionally provide:

``tracking_first_guess``
   First guess of the cyclone centre at the first output time, as ``[lat, lon]``
   (in degrees). Use it when the cyclone is not the deepest MSLP minimum of the domain
   at the first output time. If absent, the global MSLP minimum is used
   (see :doc:`/tracker/pressure_wind_tracker`).

.. code-block:: yaml

   tracking_method: "wind_pressure"
   tracking_first_guess: [-18.0, 56.0]

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
   Path where FrameIt should write its outputs.

.. code-block:: yaml

   simulation_output_dir: "/path/to/simulation/files"
   frameit_output_dir: "/path/to/FRAMEIT/outputs"

Polar projection diagnostics (optional)
---------------------------------------

FrameIt can project the selected variable in a polar coordinate system around the cyclone center. \ Enable this feature with:

``compute_polar_proj``
   Boolean switch to activate polar projection computations.

``radiale_resolution``
   Radial sampling step (in meters) used in the polar grid.

``azimuthal_resolution``
   Azimuthal sampling step (in degrees). Note that if this parameter is left empty, it will be set as ``radiale_resolution``/rmax_km where rmax is the maximum radial distance.

``polar_variables``
   List of variables to project on the polar grid.

.. code-block:: yaml

   compute_polar_proj: true
   radiale_resolution: 2500
   azimuthal_resolution: 10
   polar_variables:
     - "u10"
     - "v10"
     - "u"
     - "v"
     - "prmsl"
     - "pt"

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