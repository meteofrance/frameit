Your first run
==============

Learn how FrameIt uses a YAML file to select inputs, a region and outputs.
This example takes a small window from a generated scalar field. It needs no
model archive. First, follow :doc:`installation`.

Create the example
------------------

Use a new directory:

.. code-block:: bash

   mkdir frameit-first-run
   cd frameit-first-run
   python -m frameit.testing.documentation_example --output data/first-run.nc
   frameit init arome-fixed-scalar

You now have an input file and ``frameit.yaml``. The input has two times and a
17×17 grid around (-20°, 60°). Its scalar has units ``1``: the values have no
physical meaning. It uses the AROME NetCDF layout, but is **not an AROME producer
file or a physical simulation**.

Inspect the input:

.. code-block:: bash

   frameit inspect frameit.yaml

Check the reported field names, units, times and coordinates. For this file,
the field to extract is ``instructional_scalar``.

Read the configuration
-----------------------

This is the starter created by ``frameit init``:

.. literalinclude:: ../../../src/frameit/templates/arome-fixed-scalar.yaml
   :language: yaml

The main choices are:

* Integer ``schema_version: 3`` identifies the configuration format.
* ``sources.atmosphere.model: arome`` selects the input adapter. Choose the
  adapter for your source, not the quantity you want to study.
* Source ``files`` selects ``data/first-run.nc`` and ``format: netcdf`` declares
  its format. Relative paths start at the YAML file's directory.
* Source ``variables.2d`` selects the example scalar. Field names and units come
  from the source.
* ``region.center`` keeps one geographical centre at every time, in degrees
  north and east.
* ``region.width_km`` sets **full widths**, not half-widths. This 4×4 km request
  selects 5×5 native points on this grid. It does not create a new grid.
* ``products.model_grid: true`` requests native-grid fields only, without polar
  sampling or an exported trajectory.
* ``output.overwrite: false`` protects existing products.

Name your run
-------------

Edit two values in the existing blocks of ``frameit.yaml``. Leave the other keys
unchanged; do not add a second ``run`` or ``output`` block.

.. code-block:: yaml

   run:
     name: first-run
   output:
     directory: ./results

``run.name`` supplies the product filename prefix. ``output.directory`` sets the
run directory. These choices give filenames such as
``results/products/first-run.atmosphere.model_grid.nc``.

Check before running
---------------------

.. code-block:: bash

   frameit validate --schema-only
   frameit validate
   frameit config show frameit.yaml --effective

Without a filename, these commands read ``frameit.yaml``.

* ``--schema-only`` checks YAML keys, types and declared choices. It opens no data.
* ``validate`` also checks input metadata, units, coordinates and required fields.
* ``config show --effective`` shows settings and planned products without writing them.

Check that the preview selects the intended work. Validation reads metadata and
needed coordinate/static-support arrays; requested field values are read during
execution.

.. figure:: ../_static/figures/processing-products.svg
   :width: 440px
   :target: ../_static/figures/processing-products.svg
   :alt: Inputs and YAML pass checks, then scalar extraction writes data products and separate run records.

   This run extracts one scalar. Data products are separate from status,
   settings and provenance. Open the figure for a full-size view.

Run and check the result
------------------------

.. code-block:: bash

   frameit run
   frameit status ./results

Expect ``state: completed`` and ``tracking_complete: true``. The products are:

* ``results/products/first-run.atmosphere.model_grid.nc``: the scalar window and
  its native-grid coordinates. A fixed centre alone does not request a track file.

Open the scalar with xarray, without importing FrameIt:

.. code-block:: bash

   python -c 'import xarray as xr; d=xr.open_dataset("results/products/first-run.atmosphere.model_grid.nc", engine="netcdf4"); print(d.instructional_scalar.isel(time=0).values); print(d.instructional_scalar.attrs); d.close()'

The first time has units ``1`` and these values:

.. code-block:: text

   [[-22. -21. -20. -19. -18.]
    [-12. -11. -10.  nan  -8.]
    [ -2.  -1.   0.   1.   2.]
    [  8.   9.  10.  11.  12.]
    [ 18.  19.  20.  21.  22.]]

Zero is a valid sample. ``nan`` is missing, not zero. The second time adds 1000
to finite samples. The source values follow ``1000*t + 10*(j-8) + (i-8)``;
``j=7,i=9`` is missing. Indices start at zero. The source file is unchanged.

Keep ``results/run-request.yaml``, ``results/resolved-config.yaml``,
``results/run-provenance.yaml`` and ``results/run-status.yaml`` with the products.
They separate the captured request, effective settings, processing facts and
execution state. A failed run can leave earlier complete products, so check
status before using them.

.. figure:: ../_static/figures/first-run.png
   :target: ../_static/figures/first-run.png
   :width: 100%
   :alt: First-time instructional input and its actual exported 5-by-5 crop. Both use the same dimensionless colour scale; the missing sample is grey and zero remains valid.

   Actual input and exported crop from this tutorial, not a simulation. The
   :doc:`standalone plotting recipe <../reference/illustrations>` uses ordinary
   xarray and Matplotlib, without importing FrameIt.

Next steps
----------

Follow :doc:`../task_guides/fixed_region` to adapt the extraction to your data.
Use :doc:`quick_start` as a short CLI reminder. The
:doc:`configuration reference <../user_guide/configuration_file>` explains other
keys and defaults; :doc:`../user_guide/output_files` describes the outputs.
