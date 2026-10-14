Output files
============

FrameIt produces NetCDF output files that are designed to be shareable and easy to reuse with standard tools
(xarray, NCO, CDO, ncview).

The output files are :

- cyclone track dataset
- user-requested variables extracted on a cartesian box
- user-requested variables extracted on a polar grid (optional)

Naming convention
-----------------

All files use the configuration field ``conf.simulation_name`` as a prefix (see :doc:`configuration_file`), referred to below as ``SIMU``.

Track file:

- ``SIMU.track.nc``

Group files (one file per group key in the output dictionaries):

- ``SIMU.cart.<group>.nc``  (cartesian crop products)
- ``SIMU.polar.<group>.nc`` (polar projection products)

The ``<group>`` token is the corresponding key of the dictionary (for example ``surface``, ``level``,
``heightAboveGround``). The name is sanitized for filenames (any non-alphanumeric character is replaced by ``_``),
but the original group name is preserved in the file metadata (see below).

``output.directory`` is the run root (see :doc:`configuration_file`).
Artifacts use the same layout for ordinary runs and each matrix case::

    <output_dir>/
        cache/       # GRIB index files
        products/    # Track, Cartesian and polar NetCDF files
        logs/        # Simulation logs
        resolved-config.yaml  # Reloadable effective schema-v2 configuration
        run-provenance.yaml   # Geometry, inputs, units, and execution settings

GRIB indexes are stored in ``cache/``, never beside the input files. Cache
filenames distinguish input paths and cfgrib indexing keys. Meso-NH NetCDF
loading does not create disk indexes; its processing caches remain in memory.
Migration removes the ineffective legacy ``grib_index_dir`` YAML field;
indexes always use the run's ``cache/`` directory.

Previously, ordinary runs wrote products and logs directly into the run root.
Existing files are not moved; new runs use the layout above.

Produced files
--------------

SIMU.track.nc
~~~~~~~~~~~~~

This file contains the cyclone trajectory and kinematic diagnostics computed by the tracking module and typically includes:

- Coordinates: ``time``
- Data variables: center indices (for example ``cx``, ``cy``), latitude and longitude, motion estimates
  (for example ``heading_deg``, ``speed``), and any additional diagnostic variables created by
  ``enrich_track_with_kinematics``.

This file is intended to be the minimal entry point to interpret all other FrameIt products.

SIMU.cart.<group>.nc
~~~~~~~~~~~~~~~~~~~~

These files contain user-requested fields extracted on a cartesian box around the storm center or the fixed subdomain center.

Typical structure:

- Dimensions: ``time``, plus spatial axes such as ``x_box`` and ``y_box``
- Optional vertical dimension depending on the group (``level`` or ``heightAboveGround``)
- Coordinates commonly include: ``latitude``, ``longitude``, and box metrics ( ``x_box_km``,
  ``y_box_km``) when available
- Data variables depend on the YAML request (see :doc:`configuration_file`)

Derived wind variables
''''''''''''''''''''''
If the zonal (``u``) and meridional (``v``) wind components are included in the
requested variables, FrameIt automatically computes and appends ``wind_speed`` to
the target group (``heightAboveGround`` for AROME, ``level`` for MNH):

.. math::

   \mathrm{wind\_speed} = \sqrt{u^2 + v^2}

If ``u`` or ``v`` are absent from the group, the computation is silently skipped.

If you export cartesian crops, you obtain one file per vertical group, which keeps the outputs modular
and avoids mixing incompatible vertical coordinates in a single file.

SIMU.polar.<group>.nc
~~~~~~~~~~~~~~~~~~~~~

These files contain the polar-projected products. 
They are typically created after the cartesian extraction, using the polar projection module.

Typical structure:

- Dimensions: ``time``, radial coordinate (``r``), angular coordinate (``theta``),
  plus optional vertical dimension depending on the group
- Coordinates may include:
  - Polar grid axes: ``r`` and ``theta`` (and optionally a degree representation such as ``theta_deg``)
  - Derived cartesian coordinates on the polar grid: ``x_km`` and ``y_km``
  - Geolocation: ``latitude(time, r, theta)``, ``longitude(time, r, theta)``
- Data variables depend on the requested fields (see :doc:`configuration_file`).

The polar files also include a set of attributes that document the angular convention (for example the
zero-angle location and rotation direction) as produced by the polar projection module.

Metadata and attributes
-----------------------

FrameIt adds a minimal set of global attributes to each file:

- ``Conventions`` (currently ``CF-1.8``)
- ``title``, ``summary``, ``institution``, ``source``
- ``simulation_id`` (from ``conf.simulation_name``)
- ``FRAMEIT_version`` (from the installed FrameIt package)

Additional export-specific attributes:

- ``product_type``: one of ``track``, ``cart``, ``polar``
- ``group``: the original dictionary key (for group files)
- ``track_filename``: the corresponding track file name (for group files)

A ``history`` attribute is appended at write time and includes a UTC timestamp and the exporting module.

Attribute sanitization
~~~~~~~~~~~~~~~~~~~~~~

NetCDF backends do not accept complex Python objects as attributes. During export:

- Python dictionaries, lists, or tuples found in ``ds.attrs`` are converted to JSON strings and stored under
  a ``*_json`` attribute name.
- Boolean attributes are converted to integer flags (0 or 1), because the netCDF4 backend does not support
  boolean attributes.

Compression and performance
---------------------------

By default, the exporter applies DEFLATE compression to all data variables:

- ``zlib=True``, ``shuffle=True``, ``complevel=<compress_level>``

Notes:

- Lower compression levels (for example 1) typically write faster but generate larger files.
- Higher compression levels reduce size but increase CPU cost during export.
- Export time is also controlled by dask materialization, because writing triggers computation of lazy arrays.

Coordinates are not compressed by default. You can enable coordinate compression using ``compress_coords=True``.

You may want to tune compression, then launch frameit with ``--compress-level`` option:

.. code-block:: bash

   frameit run path/to/config.yml --compress-level 2

Default value is compress-level=1

NetCDF exports
--------------

By default, the CLI runs NetCDF exports at the end of the pipeline:

- NetCDF export: enabled by default
- Polar export: enabled by default
- Cartesian export: enabled by default

To disable some exports:

.. code-block:: bash

   # Disable all NetCDF exports
   frameit run path/to/config.yml --no-export-netcdf

.. code-block:: bash

   # Disable only polar exports
   frameit run path/to/config.yml --no-export-polar

.. code-block:: bash

   # Disable only cartesian exports
   frameit run path/to/config.yml --no-export-cart
