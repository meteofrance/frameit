Input files
===========

FrameIt accepts NetCDF and GRIB files (only GRIB for the AROME model; other GRIB files have
not been tested yet) as input. The following input formats are supported:

- A single NetCDF file containing all time steps.
- A list of files (NetCDF or GRIB), each representing a single time step.

All variables must share the same time dimension with the same name, usually ’time’ for MesoNH and ’valid_time’ for AROME.
For NetCDF files, be sure that the latitude and longitude variable are defined as coordinate for the other variables of the netcdf file.

Selection uses ``input.pattern`` (a standard glob or exact filename) or
``input.files`` (an ordered explicit inventory), with optional ``input.exclude``
globs. Relative paths are resolved from the YAML file. Content-based format
detection rejects mixed inputs; ``input.format`` may explicitly specify ``grib``
or ``netcdf``. See :doc:`configuration_file` for schema-v2 examples, units,
native-grid inference, and migration from the old filename fragments.

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
