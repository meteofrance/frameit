Input files
===========

FrameIt accepts NetCDF and GRIB files, plus selected native AROME/SURFEX FA
histories through an optional isolated reader. See :doc:`fa_inputs` for the exact
FA scope and declarations. A supported container alone does not establish
compatible model, field or grid conventions.

Files belong to named sources. Each source can use a path, glob, or list of
paths and globs under ``files``. Exclusions belong under that source's
``exclude``. All YAML paths are relative to the YAML directory.

This complete request uses an illustrative field, path and time window. Inspect
your source metadata before replacing them:

.. code-block:: yaml

   schema_version: 3
   run:
     name: selected-times
   sources:
     weather:
       model: mesonh
       files: ./data/*.nc
       exclude: ["*unwanted-stream*"]
       time:
         start: "2026-01-01T00:00:00"
         end: "2026-01-02T00:00:00"
         stride: 2
       variables:
         2d: [MSLP]
   output:
     directory: ./results/selected-times

The source name ``weather`` does not determine its model or physical type.
Explicit model/format declarations must agree with reliable input evidence.
Missing declarations require unambiguous detection; file names and selected
quantities alone are not enough. Admitted profiles distinguish atmosphere,
ocean and separately supplied surface streams. One source of each type is allowed.

Review native field names, units, levels, timestamps, cycles and coordinates.
Metadata inspection may read needed coordinates, but not scientific field
payloads. It does not prove decode-time scaling or scientific suitability.
See :doc:`configuration_file` and :doc:`../task_guides/field_selection`.

File inventory and ambiguity
-----------------------------

Supported time-split and field-split layouts are discovered without a layout
switch. A retained file can contain several times. Admitted native grids remain
distinct, including staggered fields within one source.

Records are ordered by decoded timestamps, not file names. Paths, symlinks and
hard links to the same physical file are deduplicated. Overlapping glob patterns
are reported. Separate copies remain separate providers; FrameIt does not hash
whole archives to decide whether they are equivalent.

Competing providers of a requested field, level, time and cycle fail.
Use ``files``, ``exclude`` or ``time.cycle`` to make the request unambiguous.
There is no first/last-provider setting. If excluding a whole file would remove
needed records, make the input archive unambiguous upstream.

A matched file is skipped only when metadata proves that it supplies no requested
field or required dependency. The reason is reported. An unreadable matched file
fails; it is not treated as irrelevant. Calculation inputs must come from the
selected inventory after exclusions, not another format or neighbouring stream.

Source data are read-only. GRIB indexes belong in the run's ``cache/``, not
beside inputs. Available fields do not automatically enable diagnostics, unit
conversions, interval changes or missing-value filling.

Times and cycles
-----------------

Source ``time`` is optional. Omission keeps all available records. ``start`` and
``end`` select an inclusive window; bounds need not be stored labels.
``stride: N`` keeps every Nth record after that window, starting at its first
record. Alternatively, ``values`` requests exact timestamps; every value must
exist. Quote timestamps in YAML. Empty selections fail.

The source calendar is retained. If several forecast cycles exist, supply the
exact reference time as ``time.cycle``. Do not treat equal valid timestamps as
proof that cycles are equivalent.

Forecast reference time, sample/valid time, interval bounds and sampling meaning
remain distinct. Conflicting or unidentified clocks fail. Ordering or assembling
files does not make interval means equivalent to instantaneous fields, shift
timestamps or fill missing samples.

Time selection restricts scientific field reads for extraction, tracking,
derived inputs and polar processing. Metadata and coordinate reads may establish
which records are selected. A method needing excluded temporal support fails;
FrameIt does not calculate a denser track and thin only its exports.

Independent source extraction retains each source's own times, cycles and masks.
Associate times only for the operation needing centres or cross-source data.
The region's association policy does not widen a source selection.
See :doc:`../concepts/time_support`.

Reader settings and cost
------------------------

Source ``reader.engine`` selects ``h5netcdf``, ``netcdf4`` or ``scipy`` for
their supported NetCDF encodings. It is independent of ``output.writer.engine``.
``reader.chunks`` uses input dimension names and element counts; ``-1`` means
a whole axis. Start with automatic layouts and measure wall time, peak memory
and output agreement before changing them.

The loader owns open inputs until calculation/export finishes, then closes them.
Lazy preparation is not the same as computing or writing data; compare whole-run
timings as well as phase timings. Storage chunks and full-record native decoders
can impose costs beyond the selected output size. A point guard is not a memory
ceiling. See :doc:`../task_guides/storage_and_resources`.

.. _wind-metadata:

Wind metadata to check
----------------------

Inspect each pair's sampling coordinates, units and vector basis, not only its
names. Determine the component directions from source metadata first:

* **East/north components:** GRIB ``uvRelativeToGrid=0`` (read as
  ``GRIB_uvRelativeToGrid``), or the CF ``standard_name`` pair
  ``eastward_wind`` / ``northward_wind``. U points east and V points north.
  A declaration uses ``basis: earth``.
* **Grid-aligned components:** GRIB ``uvRelativeToGrid=1``, or the CF
  ``standard_name`` pair ``x_wind`` / ``y_wind`` or
  ``grid_eastward_wind`` / ``grid_northward_wind``. U/V follow the model's x/y
  axes. A declaration uses ``basis: grid`` with a supported rotation.

If this metadata is absent or inconclusive, use the producer's documentation
for the release and fields in your files. Do not guess from the model name,
variable names or grid shape. Projection parameters describe grid orientation
and can support a rotation calculation; they do not establish whether a field
already contains eastward/northward components.

Operations needing a pair use reliable metadata first. A source declaration can
fill unresolved meaning using producer evidence; contradictions fail.
Copying a native component alone does not require a pair or rotation.
Without identifying metadata, resolve uncertainty with the producer before
requesting an operation that needs component directions.

``frameit inspect`` includes a ``variable_metadata`` list for every GRIB/NetCDF
input, in addition to the existing names/units mapping under ``variables``.
Each record identifies the field by ``name`` and, for GRIB, its inventory
``group`` so repeated names on different level types remain separate.
Group labels describe native metadata, not qualified selectors. Distinct fields
sharing a requested name are unsupported; FrameIt reports the conflict.
``attributes`` contains the recorded units, CF ``standard_name``, component
flags and ``wind_reference_frame`` when present. Missing attributes are omitted,
not filled with assumptions. Relevant dataset-wide evidence is retained
separately as ``dataset_attributes``.

For example, this excerpt describes a GRIB field whose header declares
grid-aligned wind components:

.. code-block:: yaml

   variable_metadata:
     - name: u
       group: isobaricInhPa
       attributes:
         units: m s**-1
         GRIB_uvRelativeToGrid: 1
       wind_basis: grid-aligned components

``wind_basis`` explains the available wind-reference metadata:

* ``eastward/northward components`` or ``grid-aligned components`` when the
  identifying attributes agree;
* ``unknown`` when no recorded attribute identifies the convention;
* ``conflicting metadata`` when attributes disagree;
* ``invalid metadata`` with ``wind_metadata_error`` when an attribute is unusable.

These labels describe wind conventions, not proof that a field is a wind:
GRIB grid flags can also occur on scalar messages. Inspection does not select
wind pairs, rotate components or change the configuration. Inconsistent units
or wind flags across GRIB records of the same field/group still fail header
inspection rather than being silently merged.

After declaring the pairs, run ``frameit validate`` to check them against
available input metadata; ``--schema-only`` checks the YAML without opening inputs.

Meso-NH native ``UT``/``VT`` occupy different horizontal faces and ``WT``
occupies vertical interfaces. DIAG ``UT_ZM``/``VT_ZM`` are zonal/meridional
diagnostics; ``UM10``/``VM10`` are eastward/northward 10-m surface wind components
(Earth-relative). Do not apply one file-wide grid-aligned assumption to all of
them. These labels describe component directions, not storm-motion subtraction;
see :ref:`wind-component-directions`.

The declarations are in :doc:`configuration_file`; diagrams of collocation,
rotation and level selection are in :ref:`wind-grid-contract`.

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
