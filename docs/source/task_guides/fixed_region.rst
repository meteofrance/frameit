Extract a fixed geographical region
====================================

Use a fixed region when the scientific comparison concerns the same place at
each time, rather than a window following an event. FrameIt maps the declared
latitude/longitude to a native grid point and extracts neighbouring samples.
The Cartesian crop is grid-aligned, not recentered by interpolation.

Prerequisites and starter
--------------------------

Use the :doc:`reference environment <../getting_started/installation>` and an
inspected input stream with known fields, coordinate units and valid times.
The example below reuses the :doc:`instructional scalar
<../getting_started/first_run>`.
Start in a new directory:

.. code-block:: bash

   mkdir frameit-fixed-region
   cd frameit-fixed-region
   python -m frameit.testing.documentation_example --output data/first-run.nc
   frameit init arome --tracking fixed_box

This is equivalent to ``frameit init arome-fixed-scalar``. Its geographical choices are:

.. literalinclude:: ../../../src/frameit/templates/arome-fixed-scalar.yaml
   :language: yaml
   :start-at: tracking:
   :end-at: width_km: {x: 4, y: 4}

.. figure:: ../_static/figures/fixed-moving-regions.svg
   :width: 480px
   :target: ../_static/figures/fixed-moving-regions.svg
   :alt: Schematic contrasting one fixed native crop with crops following a moving centre. The selected native point can differ from the requested geographical centre.

   Schematic, not to scale. The crop snaps to native indices. Requested full
   widths are rounded to native point counts; realised extents can differ.
   The requested geographical centre remains available as the polar origin.

Adapt it to real inputs
------------------------

For this instructional run, leave the generated values unchanged. For real work,
edit ``frameit.yaml`` only after inspecting the intended stream:

* Replace ``input.directory/pattern/format`` and ``variables.fields_2d.names``
  together. ``instructional_scalar`` is not a producer field. Declare each needed
  vertical selection explicitly; stored indices are not physical depths.
* Set ``tracking.fixed_box.center`` in degrees north/east. Use a location relevant
  to the question, not a supplied illustrative centre.
* Set both ``domain.width_km`` components as positive **full widths in km**.
  Rounding to native grid points changes the realised extent. Near an edge the
  supported ``pad_nan`` policy retains centred geometry and missing outside samples.
* Keep a fresh ``output.directory`` and ``overwrite: false``. Leave polar sampling
  off unless selected for a separate purpose. Adding winds or currents requires
  their own sampling/basis declarations, not just extra field names.

See :doc:`../user_guide/configuration_file` for the full schema/defaults,
:doc:`../user_guide/input_files` for stream layouts, and
:doc:`../user_guide/ocean_netcdf` for native NEMO/CROCO distinctions.

Check, run and interpret
-------------------------

.. code-block:: bash

   frameit validate --schema-only
   frameit validate
   frameit run --dry-run
   frameit run
   grep -E '^(state|tracking_complete):' output/run-status.yaml
   python -c 'import xarray as xr; d=xr.open_dataset("output/products/arome-fixed-scalar.cart.surface.nc", engine="netcdf4"); print(d.sizes); print(d.instructional_scalar.isel(time=0).values); d.close()'

Schema checks open no data; metadata checks can read coordinates but not field
payloads. Execution reads the selected values. For this input expect a complete
two-time track and a ``time=2, y_box=5, x_box=5`` scalar product, with the same
5×5 values shown in the first run. The central zero stays valid and the missing
sample stays NaN. No polar file, wind diagnostic or unselected field is produced.

Use the actual status inventory for other run names or backends. Reopen products
with your normal reader, check coordinates/units and distinguish missing support
from physical zero. Keep the effective configuration and provenance alongside
the data. See
:doc:`../tracker/fixed_box` and :doc:`../user_guide/output_files`.
