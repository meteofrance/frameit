Input files
===========

FrameIt accepts NetCDF and GRIB files, plus selected native AROME/SURFEX FA
histories through an optional isolated reader. See :doc:`fa_inputs` for the exact
FA scope, declarations and coupled-source configuration. Other GRIB model
conventions have not been generally qualified. Ordinary inventories include:

- A single NetCDF file containing all time steps.
- A list of files (NetCDF or GRIB), each representing a single time step.
- Complementary NetCDF variable files, explicitly selected as described below.

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
See :doc:`configuration_file` for YAML settings, units and native-grid inference.
For a task route, use :doc:`../task_guides/field_selection` or
:doc:`../task_guides/coupled_inputs`.

Inspect a deliberately selected stream before choosing quantities and methods:

.. code-block:: bash

   frameit inspect ./data --model arome --format grib --pattern '*.grib'
   frameit inspect ./data --model mesonh --format netcdf --pattern '*.nc'

Review native names, units, time support/cycles, levels and grid coordinates.
Inspection reads metadata/coordinates, not scientific field payloads, and does
not prove decoded scaling or scientific suitability. ``validate --schema-only``
checks configuration without opening inputs; ``validate`` and ``run --dry-run``
perform metadata preflight for the configured selections. See
:doc:`../getting_started/first_run` for a worked example.

Sources are read-only. FrameIt keeps GRIB indexes in the designated output
``cache/``, not beside input files. In coupled runs, streams keep their own grids,
masks and products; exact-common/strict time selection is described in
:doc:`fa_inputs`. Available fields do not automatically enable diagnostics,
unit/interval conversions or missing-data filling.

NetCDF reading performance
--------------------------

The NetCDF loader reuses open inputs during a run and closes them afterward.
The cache does not persist across runs.

Choose the input reader and chunks with:

.. code-block:: yaml

   input:
     netcdf:
       engine: h5netcdf  # Default; netcdf4 is the alternative.
       chunks: {}        # Respect each variable's native storage chunks.

Compare readers with your actual selection, measuring runtime and peak memory.
This setting selects the input reader independently of ``output.backend``;
FrameIt does not substitute another reader automatically.

Keep ``chunks: {}`` as the starting point. Oversized chunks (especially ``-1``
for whole axes) can force reading much more than a small spatial/vertical
selection needs; very small chunks increase scheduling and repeated storage
chunk reads. Chunk overrides use the source's dimension names. Measure wall
time, memory and output agreement before adopting a different layout.

The runtime ``Input loading`` section includes metadata, coordinates and lazy
graph preparation, not necessarily physical-field reads. With lazy execution,
those reads may be charged to tracking or export. Compare the entire run as well
as individual sections, using the same thread budget and filesystem-cache state.

Complementary NetCDF variables
------------------------------

For one physical field per file, declare the layout within that source:

.. code-block:: yaml

   input:
     format: netcdf
     files: [pressure.nc, u10.nc, v10.nc]
     netcdf:
       file_layout: variables
   variables:
     fields_2d:
       names: [prmsl, u10, v10]

Adapt names and wind declarations to the source metadata. A wind companion may
live in a different shard. Files must share identical decoded sample times,
forecast cycle and horizontal coordinates; shared vertical definitions and
auxiliaries must agree. Selected physical fields must have exactly one provider.
Payloads remain selected and lazy; coordinate checks can read small axes and
required geography, not physical cubes to prove duplicate equality. Time blocks
mixed with variable shards are unsupported; separate unlike grids into sources.

AROME NetCDF ``valid_time`` becomes canonical ``time``. A colliding scalar
``time`` is retained as ``forecast_reference_time`` only when its source
``standard_name`` explicitly identifies that clock; conflicting or unidentified
clocks fail. Original forecast identity, time bounds and interval annotations
remain distinct from valid/sample time. No timestamp shifting, nearest matching,
resampling or value filling is performed. This assembly option does not make
interval means scientifically equivalent to instantaneous fields.

Wind metadata to check
----------------------

Inspect each pair's sampling coordinates, units and vector basis, not only its
names. Meso-NH native ``UT``/``VT`` occupy different horizontal faces and ``WT``
occupies vertical interfaces. DIAG ``UT_ZM``/``VT_ZM`` are zonal/meridional
diagnostics; ``UM10``/``VM10`` are Earth-relative 10-m surface winds. Do not apply
one file-wide grid-relative assumption to all of them.

The declarations are in :doc:`configuration_file`; diagrams of collocation,
rotation and level selection are in
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

Use release-matched definitions to resolve unsupported metadata or geometry.
