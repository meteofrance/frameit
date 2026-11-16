Process a small prescribed event
================================

Practice selecting times and a single saved level, processing atmosphere/ocean
inputs separately, and requesting polar products.
The :doc:`input definitions <../reference/analytical_inputs>` give the formulas,
units and masks. These are instructional inputs, not simulation or producer
validation data.

Generate the inputs
-------------------

Use the :doc:`reference environment <../getting_started/installation>`.
Start in a fresh working directory:

.. code-block:: bash

   mkdir frameit-analytical
   cd frameit-analytical
   python -m frameit.testing.documentation_example --tutorial translating --output data

The command writes ``data/atmosphere.nc``, ``data/ocean.nc`` and
``data/track.nc``. It refuses to replace an existing input. Use a different
directory for ``--tutorial stationary`` or ``--tutorial missing``.

Select the task
---------------

Save this complete request as ``frameit.yaml``:

.. literalinclude:: ../../../example/tutorials/analytic-moving.yaml
   :language: yaml

The atmosphere selects hours 1 and 2 and retains the singleton 1000 m layer.
The ocean keeps hours 0 and 2 on its own rho grid. Exact association uses centres
at those actual times; it does not interpolate either source in time.
Native interface samples stay on their separate axis.

Only the selected polar product calculates ``speed``. It samples Earth-relative
components before taking their magnitude. The common target uses the coarser
prepared spacing, but each source retains its own mask and clock.
No centre-motion velocity is subtracted.

.. code-block:: bash

   python -m frameit inspect frameit.yaml
   python -m frameit validate frameit.yaml --schema-only
   python -m frameit validate frameit.yaml
   python -m frameit config show frameit.yaml --effective
   python -m frameit run frameit.yaml
   python -m frameit status results

Read the products
-----------------

The completed inventory in ``results/run-status.yaml`` lists:

* ``products/analytic-moving.atmosphere.model_grid.nc``: pressure, the selected
  layer temperature and interface velocity;
* ``products/analytic-moving.ocean.model_grid.nc``: temperature on the three
  requested rho indices, corresponding here to 0, −10 and −30 m;
* ``products/analytic-moving.atmosphere.polar.nc``: ``u``, ``v``, ``speed``
  and their coverage/status variables;
* ``products/analytic-moving.ocean.polar.nc``: ``temp`` and its coverage/status;
* ``products/analytic-moving.track.nc``: the prescribed three-time trajectory.

Open a product without importing FrameIt:

.. code-block:: python

   import xarray as xr

   with xr.open_dataset("results/products/analytic-moving.atmosphere.model_grid.nc") as air:
       temperature = air["height.temperature"]
       print(air.time.values)  # Hours 1 and 2.
       print(temperature.sizes["height"])  # 1, not a removed vertical dimension.
       print(temperature.values.min())  # 294 K.

   with xr.open_dataset("results/products/analytic-moving.ocean.model_grid.nc") as ocean:
       print(ocean.time.values)  # Hours 0 and 2.
       print(ocean.s_rho.values)  # [0, -0.25, -0.75], in requested native-index order.

Keep ``run-request.yaml``, ``resolved-config.yaml`` and ``run-provenance.yaml``
with the products. See :doc:`../user_guide/output_files` for stored coordinates
and :doc:`../concepts/missingness_and_status` for polar quality flags.

Adapt or repair the request
---------------------------

For native extraction without diagnostics, remove ``polar`` and ``track`` from
``products``. The two model-grid products remain usable; an unused derived
declaration does not execute it. For polar-only output, remove ``model_grid``.
Remove ``track`` too if you do not need a separate trajectory file: the input
track can still supply centres.

To retain every atmospheric time, omit its ``time`` block. To change the layer,
edit ``sources.atmosphere.variables.3d.height.levels``; index 0 is 10 m and
index 2 is 3000 m. Inspect the effective selection before running.

An unavailable index, field or centre time makes validation fail. Correct the
affected source/selection rather than filling data or choosing a different
quantity. If ``results`` already belongs to an attempt, select a fresh
``output.directory``. See :doc:`field_selection`, :doc:`coupled_inputs` and
:doc:`../troubleshooting` for other requests and repairs.

Compare missing-data policies and categories
---------------------------------------------

Generate the separate stationary variant from the same working directory:

.. code-block:: bash

   python -m frameit.testing.documentation_example --tutorial missing --output missing-data

Save this complete request as ``missing.yaml``:

.. literalinclude:: ../../../example/tutorials/analytic-missing.yaml
   :language: yaml

.. code-block:: bash

   python -m frameit validate missing.yaml
   python -m frameit run missing.yaml
   python -m frameit status strict-results

The only product is
``strict-results/products/analytic-missing.atmosphere.polar.nc``. It contains
``u``, ``surface_type`` and their coverage/status variables. Strict bilinear
sampling leaves U missing where a required source neighbour is missing.
Nearest-neighbour sampling preserves the category labels, including valid zero.
Using bilinear interpolation for this categorical field fails validation.

To compare an explicitly different scientific policy, change only
``u``'s options to
``{missing_data_policy: renormalize, min_valid_weight_fraction: 0.5}`` and
set ``output.directory: ./renormalize-results``. Validate and run again.
Partial support at or above 0.5 may then produce a U sample with status 0
(valid under the selected policy) and support fraction below 1. Status 3 instead
means insufficient support. A valid renormalized value is not a complete-stencil
value or a zero-filled gap.

.. code-block:: python

   import xarray as xr

   with xr.open_dataset(
       "renormalize-results/products/analytic-missing.atmosphere.polar.nc"
   ) as fields:
       print(fields.u_support_fraction.values)
       print(fields.u_interpolation_status.values)
       print(fields.surface_type.min().item())  # 0 is a valid category.

Keep the two outputs separate. Choose a missing-data policy for scientific
reasons, not merely because it produces more finite values.

.. _prepare-interface-input:

Practice an explicit W remap
-----------------------------

The baseline's generic AROME-labelled interface field does not authorize an
AROME mass remap. For the supported Meso-NH coordinate-linear operation, create
a separate instructional input from the stationary atmospheric arrays. This
recipe changes labels and adds computational horizontal axes; it does not alter
the temperature or W formula. It is not a Meso-NH producer-conformance fixture.
In a fresh working directory, run
``python -m frameit.testing.documentation_example --tutorial stationary --output data``,
then:

.. code-block:: python

   from pathlib import Path
   import numpy as np
   import xarray as xr

   path = Path("interfaces.nc")
   if path.exists():
       raise FileExistsError(path)
   with xr.open_dataset("data/atmosphere.nc") as source:
       fields = source[["temperature", "interface_w"]].load()
   fields = fields.rename({
       "height": "level", "interface_height": "level_w",
       "temperature": "THT", "interface_w": "WT",
   }).rename_dims({"latitude": "nj", "longitude": "ni"})
   fields = fields.assign_coords(
       ni=("ni", 5000. * np.arange(25), {"units": "m"}),
       nj=("nj", 5000. * np.arange(25), {"units": "m"}),
   )
   fields.WT.attrs["standard_name"] = "upward_air_velocity"
   fields.to_netcdf(path, mode="w")

Save this request as ``interfaces.yaml``:

.. literalinclude:: ../../../example/tutorials/analytic-interfaces.yaml
   :language: yaml

.. code-block:: bash

   python -m frameit validate interfaces.yaml
   python -m frameit run interfaces.yaml
   python -m frameit status interface-results

The model-grid file
``interface-results/products/analytic-interfaces.atmosphere.model_grid.nc``
retains native index 1 at ``level_w=500 m``, with W=0.5 m s-1.
The polar file with the same prefix and ``.polar.nc`` suffix uses destination
index 1 at ``level=1000 m``, with W=1 m s-1. Both retain a length-one vertical
axis. Their equal index numbers do not denote the same sampling location.

.. code-block:: python

   import xarray as xr

   with xr.open_dataset(
       "interface-results/products/analytic-interfaces.atmosphere.polar.nc"
   ) as fields:
       print(fields.level.values)  # [1000].
       print(fields.WT.min().item(), fields.WT.attrs["units"])  # 1 m s-1.

The remap uses native coordinate brackets, without extrapolation. It does not
convert pressure velocity to geometric velocity, rotate horizontal vectors or
subtract storm motion. See :doc:`scalars_and_vectors` for real-input requirements.
