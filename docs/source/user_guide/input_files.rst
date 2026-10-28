Input files
===========

FrameIt accepts NetCDF and GRIB files, plus selected native AROME/SURFEX FA
histories through an optional isolated reader. See :doc:`fa_inputs` for the exact
FA scope, declarations and coupled-source configuration. Other GRIB model
conventions have not been generally qualified. Ordinary inventories include:

- A single NetCDF file containing all time steps.
- A list of files (NetCDF or GRIB), each representing a single time step.

Within each source, variables must share a time-dimension convention, usually
``time`` for Meso-NH and ``valid_time`` for AROME. NetCDF latitude/longitude must
be coordinates associated with the scientific fields. Matching the container
format alone does not establish compatible model/variable/grid conventions.

Selection uses ``input.pattern`` (a standard glob or exact filename) or
``input.files`` (an ordered explicit inventory), with optional ``input.exclude``
globs. Relative paths are resolved from the YAML file. GRIB/NetCDF content-based
format detection rejects mixed inputs; ``input.format`` may explicitly specify
``grib`` or ``netcdf``. FA requires explicit ``format: fa`` and its profile/declarations.
Mixed formats require separate named sources, not a mixed ordinary inventory.
See :doc:`configuration_file` for schema-v2 examples, units,
native-grid inference, and migration from the old filename fragments.

Inspect a deliberately selected stream before choosing quantities and methods:

.. code-block:: bash

   frameit inspect ./data --model arome --format grib --pattern '*.grib'
   frameit inspect ./data --model mesonh --format netcdf --pattern '*.nc'

Review native names, units, time support/cycles, levels and grid coordinates.
Inspection reads metadata/coordinates, not scientific field payloads, and does
not prove decoded scaling or scientific suitability. ``validate --schema-only``
checks configuration without opening inputs; ``validate`` and ``run --dry-run``
perform metadata preflight for the configured selections. See
:doc:`../getting_started/quick_start` for the full workflow.

Sources are read-only. FrameIt keeps GRIB indexes in the designated output
``cache/``, not beside input files. In coupled runs, streams keep their own grids,
masks and products; exact-common/strict time selection is described in
:doc:`fa_inputs`. Available fields do not automatically enable diagnostics,
unit/interval conversions or missing-data filling.

Wind metadata to check
----------------------

Inspect each pair's sampling coordinates, units and vector basis, not only its
names. Meso-NH native ``UT``/``VT`` occupy different horizontal faces and ``WT``
occupies vertical interfaces. DIAG ``UT_ZM``/``VT_ZM`` are zonal/meridional
diagnostics; ``UM10``/``VM10`` are Earth-relative 10-m surface winds. Do not apply
one file-wide grid-relative assumption to all of them.

The explicit declarations are in :doc:`configuration_file`; the single
illustrated explanation of collocation, rotation and level selection is
:ref:`wind-grid-contract`. Declared input must agree
with available GRIB flags and CF metadata. Missing information is not permission
to silently choose another frame, rotation method or physical quantity.

Authoritative preparation references
------------------------------------

Use the documentation for the release that produced your files. The current
Meso-NH 6.0 documentation describes:

* `C-grid locations
  <https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/grids.html>`_:
  mass, U, V and W sampling points.
* `NAM_DIAG general options
  <https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/executables_namelists/namelists/nam_diag_general.html>`_:
  ``LVAR_RS`` writes ``UT``, ``VT`` and ``WT``; adding ``LWIND_ZM`` writes
  ``UT_ZM``/``VT_ZM``. Inspect their actual coordinates and metadata.
* `NAM_DIAG defaults
  <https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/executables_namelists/namelists/nam_diag_default.html>`_:
  ``UM10``/``VM10`` are documented for ``CSURF='EXTE'``. Availability depends on
  the MNH/SURFEX release and surface setup.
* `NAM_GRID_PRE
  <https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/executables_namelists/namelists/nam_grid_pre.html>`_:
  projection parameters, including ``XLON0``, ``XLAT0``, ``XBETA`` and ``XRPK``.
* `NAM_VER_GRID
  <https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/executables_namelists/namelists/nam_ver_grid.html>`_:
  vertical discretization and stored extra levels. Physical ranges must be
  validated by the adapter, not inferred from array length alone.

For AROME GRIB, `ECMWF resolution and component flags
<https://codes.ecmwf.int/grib/format/grib2/ctables/3/3/>`_ distinguish geographic
east/north from increasing grid x/y (ecCodes ``uvRelativeToGrid``). The WMO
definitions distinguish `pressure vertical velocity
<https://codes.wmo.int/grib2/codeflag/4.2/0-2-8>`_ (Pa s-1, commonly ``w``)
from `geometric vertical velocity
<https://codes.wmo.int/grib2/codeflag/4.2/0-2-9>`_ (m s-1, commonly ``wz``).
Check parameter identity and units; short names alone are insufficient.

These references define source conventions, not validation of every release or
grid by FrameIt. Unsupported metadata/geometry must be resolved explicitly.
