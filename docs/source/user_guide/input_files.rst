Input files
===========

Put a path, glob, or list of paths/globs under each named source's ``files``;
put exclusions under its ``exclude``. YAML paths are relative to the YAML directory.

FrameIt reads NetCDF, GRIB and selected native AROME/SURFEX FA histories.
Check :doc:`fa_inputs` for FA declarations and :doc:`ocean_netcdf` for ocean
conventions. A supported container does not establish compatible quantities or grids.

This complete request uses an illustrative field, path and time window. Inspect
your source metadata before replacing them:

.. code-block:: yaml

   schema_version: 3
   run:
     name: selected-times
   sources:
     atmosphere:
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

Model and format declarations must agree with reliable input evidence.
Missing declarations require unambiguous detection; file names and selected
quantities alone are not enough. Admitted profiles distinguish atmosphere,
ocean and separately supplied surface streams. One source of each type is allowed.

Review native field names, units, levels, timestamps, cycles and coordinates.
Metadata inspection may read needed coordinates, but not scientific field
payloads. Input-aware validation may also read declared static analysis support,
such as CROCO masks and rotation angles. It does not prove decode-time scaling
or scientific suitability.
See :doc:`configuration_file` and :doc:`../task_guides/field_selection`.

For direct native polar sampling of Meso-NH NetCDF, FrameIt can use
``kind: continuous`` for numeric ``UM10`` or ``VM10`` on the native ``nj``/``ni``
mass grid. It matches the `Meso-NH 6.0 DIAG definition
<https://github.com/JorisPianezze/mesonh_doc/blob/061c0f29ea33fc374b318d77efcec2d29a12b12a/docs/source/documentation/users_guide/executables_namelists/namelists/nam_diag_default.rst>`_.
A supplied standard name must describe a horizontal wind component. The fallback
does not establish units or vector basis, and excludes wide integer storage.
It applies only to records selected for polar sampling when neither the input
nor YAML supplies the needed kind. Check the matched record and rule in
validation and ``run-provenance.yaml``. A native export spanning matched and
unmatched records does not label the whole variable with the fallback.

For direct native AROME GRIB2 point sampling, the same fallback matches WMO
wind components 0/2/2 and 0/2/3 in master/local tables 15/0. It requires
template 4.0, an exact single 10 m surface above ground, and unchanged process
codes in the selected field series. Gusts, other levels and other templates
do not match. This checks the wire codes; it does not identify a forecast
producer or resolve incompatible streams.

CROCO ``zeta`` uses a separate history-writer match with native rho geography
and a same-file static mask. See :doc:`ocean_netcdf`. There is no corresponding
fallback for NEMO ``zos``.

File inventory and ambiguity
-----------------------------

Supported time-split and field-split layouts are discovered without a layout
switch. A retained file can contain several times. Admitted native grids remain
distinct, including staggered fields within one source.

Records are ordered by decoded timestamps, not file names. Paths, symlinks and
hard links to the same physical file are deduplicated. Overlapping glob patterns
are reported. Separate copies remain separate providers; FrameIt does not hash
whole archives to decide whether they are equivalent.
Declared symlink paths remain inspectable; exclusions match those paths before
physical-file deduplication.

Competing providers of a requested field, level, time and cycle fail.
Use ``files``, ``exclude`` or ``time.cycle`` to make the request unambiguous.
There is no first/last-provider setting. If excluding a whole file would remove
needed records, make the input archive unambiguous upstream.

Complementary AROME NetCDF files may repeat linked forecast periods and scalar
height labels. FrameIt treats these as coordinates of their owning fields, not
as competing physical fields. It retains different heights or surface labels and
does not combine wind components with conflicting coordinate definitions, even
when the coordinates use different names. If one component owns a scalar
surface label, its partner must identify the same surface. A separate field
referenced by a vertical formula stays a scientific input.
When forecast times are split across files, the forecast period stays attached
to its sample. Different lead times do not make an otherwise identical
sampling grid a different tracker grid.

For Meso-NH NetCDF, a native-level request can proceed if its declared altitude
formula lacks the model-top operand (often ``ZTOP``) and no requested operation
needs it. FrameIt warns and keeps the native ``level`` or ``level_w`` labels. It
does not infer a model-top value or physical altitudes. Other required links to
that operand still have to resolve. A transform to mass levels checks the
destination axis's formula, not just the input axis's formula. A method that
needs physical height requires valid altitude on its working grid or a complete
supported formula.

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
proof that cycles are equivalent. See :doc:`../task_guides/forecast_archive`
for a worked selection.

Forecast reference time, sample/valid time, interval bounds and sampling meaning
remain distinct. Conflicting clocks or calendars fail, including when reference
aliases or supporting files decode to the same timestamp. Ordering or assembling
files does not make interval means equivalent to instantaneous fields, shift
timestamps or fill missing samples.

A one-record Meso-NH NetCDF file may also declare a scalar ``DTCUR`` current
time. It must match the sole decoded ``time`` value and calendar exactly.
FrameIt selects by ``time`` and retains ``DTCUR`` along that axis when assembling
the files. If a selected file lacks the optional alias, the assembled product
keeps the canonical clock and records why ``DTCUR`` was omitted. It does not
invent an alias. Forecast reference clocks and interval bounds are still checked.
This convention does not extend to multi-record input files or other models.

An explicit source ``allow_initial_gaps`` list can preserve a wholly absent
selected field at the first selected time as missing output, without dropping
that timestamp. The default remains strict. See :doc:`configuration_file` for
the unchanged-grid and required-support limits; this never fills physical values
or infers an accumulation interval.

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

Native GRIB extraction reads only the selected encoded messages, using their
inventoried locations. It needs no disk index. Each requested message is decoded
as a whole horizontal field, even if a later operation uses a smaller area;
the selected output size is not a decoder-memory limit.

NetCDF assembly supports one varying native sample axis, including selected
leads from one forecast cycle. A selection varying several sample axes at once
fails before reading scientific values. FrameIt does not guess a flattening
order or fill the gaps between those samples.

Inputs stay open until calculation/export finishes. Compare whole-run timings:
lazy preparation may only build a computation graph. Storage chunks and full-record
decoders add costs beyond the selected output size; a point guard is not a memory
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

If metadata is inconclusive, use the producer's release-matched documentation.
Model/variable names and grid shape do not establish component directions.
Projection parameters can support a rotation calculation but do not show whether
the stored components are already eastward/northward.

Operations needing a pair use reliable metadata first. A source declaration can
fill unresolved meaning using producer evidence; contradictions fail.
Copying a native component alone does not require a pair or rotation.
Without identifying metadata, resolve uncertainty with the producer before
requesting an operation that needs component directions.

In ``frameit inspect frameit.yaml --json``, look under
``data.plan.sources.<source>``:

* ``fields`` contains definitions keyed by identity. Each has a ``name`` and,
  for GRIB, a ``group`` separating repeated names on different level types.
  Pressure groups use ``isobaric``; units and raw GRIB level-type enums remain
  coordinate/external metadata. Use :ref:`explicit-vertical-groups` when names
  are ambiguous.
* ``record_inventory`` links records to definitions through ``field_id``.
* Field ``attributes`` retains units, CF ``standard_name``, component flags and
  ``wind_reference_frame`` when present. Relevant dataset-wide evidence stays
  under the owning input's ``dataset_attributes``. Missing facts remain absent;
  conflicting evidence remains visible.

Inspection does not choose a pair, rotate values or edit the request.
``GRIB_uvRelativeToGrid: 1`` alone does not identify a wind: scalar messages can
also carry this flag. Inconsistent units or wind flags across records of the
same GRIB field/group fail header inspection rather than being silently merged.

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
