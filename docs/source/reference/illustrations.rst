Illustration data and plotting scripts
======================================

Documentation plots are made with small standalone Python scripts, not a FrameIt
plotting API. The scripts use NumPy, xarray and Matplotlib; Matplotlib is a
downstream plotting dependency, not a requirement for core extraction.

BATSIRAI: stored 10-m zonal wind
--------------------------------

The fixed-box, pressure-wind and Cartesian/polar illustrations use these Meso-NH
files, supplied separately from the repository:

* ``1BT01.1.MXX30.001dg.nc``: 2022-02-01 00:10;
* ``1BT01.1.MXX30.002dg.nc``: 2022-02-01 00:20.

All four plots show the stored ``UM10`` at **00:20**, in m/s. The source describes
it as zonal wind at 10 m: positive values point east, negative values west. There
is no rainfall-to-reflectivity approximation, time differencing, smoothing or
storm-motion subtraction. A common symmetric colour scale spans ±30 m/s, the
largest absolute physical-domain value rounded up to a multiple of 5 m/s. Zero
wind remains valid; grey marks missing samples.

The source axes declare physical ranges ``ni: 2:961`` and ``nj: 2:601`` in
one-based inclusive notation. The outer one-cell halo is outside these ranges
and contains finite ``1e20`` wind values. The standalone source-context plot
excludes that **declared nonphysical halo**, not values above an invented wind
threshold. The script verifies this layout before plotting. The interior
extraction boxes are unaffected.

The fixed geographical centre is the first file's MSLP minimum,
(-16.342215°, 62.154875°). Both extractions request full 500×500 km widths, which
give 167×167 native points at the resolved 3000 m spacing. The fixed run samples
``UM10`` on 43 radii at 6 km spacing and 180 azimuths. It interpolates the declared
eastward/northward wind components. Polar coordinates
describe sampling locations: ``UM10`` remains eastward wind, not radial wind.
The moving run uses the pressure-wind method with default 100/50 km search/refine
half-widths. Its centres move from native ``(cy,cx)=(380,732)`` to ``(380,731)``.
The files describe ``UM10/VM10`` as zonal/meridian 10-m winds in m/s, declared here
as eastward/northward components. These two fixes illustrate extraction, not track
validation.

Regenerate from the checkout
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Download or copy the two configurations:
:download:`fixed <../../../example/plots/batsirai-fixed.yaml>` and
:download:`moving <../../../example/plots/batsirai-moving.yaml>`.
Keep the input files read-only. Set ``input.directory`` in both YAML files to
their actual directory; relative paths use the YAML's location.

.. code-block:: bash

   mkdir figures-batsirai
   cp example/plots/batsirai-fixed.yaml example/plots/batsirai-moving.yaml figures-batsirai/
   # Edit input.directory in both copied YAML files, then:
   frameit validate figures-batsirai/batsirai-fixed.yaml
   frameit validate figures-batsirai/batsirai-moving.yaml
   frameit run figures-batsirai/batsirai-fixed.yaml
   frameit run figures-batsirai/batsirai-moving.yaml
   python example/plots/batsirai_wind.py \
     /path/to/BATSIRAI-10mins \
     figures-batsirai/batsirai-fixed figures-batsirai/batsirai-moving \
     figures-batsirai/figures

The :download:`plotting script <../../../example/plots/batsirai_wind.py>`
imports no FrameIt code. It requires a new figure directory outside the source
data directory. Both configurations select ``UM10``; vector preparation also
loads its declared companion ``VM10``. The moving tracker additionally reads
MSLP. No three-dimensional field is needed.
Check both ``run-status.yaml`` files before using the products. Raw source files
are not bundled or downloaded by this example.

The instructional first run
---------------------------

The :doc:`../getting_started/first_run` figure shows the actual generated input
and exported first-time crop. Its scalar has units ``1`` and **no physical
meaning**; it is not labelled as reflectivity.

After completing that tutorial, run the
:download:`separate plotting script <../../../example/plots/first_run.py>`
from the tutorial directory, using the checkout's actual path:

.. code-block:: bash

   python /path/to/frameit/example/plots/first_run.py \
     data/first-run.nc results/products/first-run.cart.surface.nc first-run.png

The script refuses an existing output filename. It retains zero as a valid value
and shows the missing sample in grey. Neither plotting script changes its inputs.
