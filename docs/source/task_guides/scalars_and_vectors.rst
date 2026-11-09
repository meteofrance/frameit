Choose scalar and vector representations
========================================

Start from an inspected stream and its matching starter:

.. code-block:: bash

   frameit init mesonh-pressure-wind

Adapt paths, selected fields and domain. Scalar copies retain source units;
prepared atmospheric velocities use m s-1. Field names alone do not establish
quantity, sample location or vector basis.

Declare atmospheric wind pairs
------------------------------

Declare **eastward/northward components** with ``reference_frame: earth``:
U is positive eastward and V northward, also called **Earth-relative components**.
Declare **grid-aligned components**, following the model's x/y axes, with
``reference_frame: grid``. These labels specify component directions, not
storm-motion subtraction; see :ref:`wind-component-directions`.

For Meso-NH, native ``UT/VT`` are grid-aligned and ``UM10/VM10`` are
eastward/northward. Declare each pair separately. This fragment assumes the
inspected projection metadata establishes the native grid rotation:

.. code-block:: yaml

   input:
     wind_pairs:
       - group: level
         u: UT
         v: VT
         reference_frame: grid
         rotation: {method: mesonh_projection}
       - group: fields_2d
         u: UM10
         v: VM10
         reference_frame: earth
   output:
     cartesian:
       horizontal_vectors: earth_centered
       vertical_velocity: interfaces
     polar:
       vertical_velocity: mass

``earth_centered`` collocates atmospheric U/V and rotates grid-aligned pairs to
eastward/northward components. ``native`` retains their source staggering and
declared basis, with normalized velocity units. W location is an independent
choice. Tracking and polar processing use a separate analysis representation,
so changing Cartesian
representation does not change their results. See :ref:`wind-grid-contract`
for existing C-grid/W diagrams, level mapping and method limitations.

.. figure:: ../_static/figures/sampling-frames.svg
   :target: ../_static/figures/sampling-frames.svg
   :width: 540px
   :alt: Three separate operations: choose native or polar sample locations, rotate a vector basis to east and north, and subtract frame motion only in an explicitly separate downstream calculation.

   Schematic. Sample locations, vector basis and reference-frame motion are
   different choices. Storm-centred polar positions do not subtract storm motion
   from the winds.

Check the result
----------------

Run ``frameit validate``, ``frameit run --dry-run`` and ``frameit run``. Reopen the
selected products and check each component's dimensions, coordinates, units and
basis. Do not take ``hypot`` of staggered face arrays as though they were a
collocated point vector. A requested ``wind_speed`` uses the prepared pair and
does not export internal-only companions.

For native ocean components, select ``horizontal_vectors: native`` unless the
documented CROCO rho/Earth analysis is intended and its angle/mask/bracket
requirements are met. NEMO component analysis and ocean wind diagnostics are
unsupported. See :doc:`../user_guide/ocean_netcdf`; atmospheric wind declarations
do not supply missing ocean geometry or physical meaning.
