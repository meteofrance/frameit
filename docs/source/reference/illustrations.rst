Illustration data and plotting scripts
======================================

Documentation plots are made with small standalone Python scripts, not a FrameIt
plotting API. The scripts use NumPy, xarray and Matplotlib; Matplotlib is a
downstream plotting dependency, not a requirement for core extraction.

BATSIRAI: real rainfall, illustrative rain-only dBZ
---------------------------------------------------

The fixed-box, pressure-wind and Cartesian/polar illustrations use these Meso-NH
files, supplied separately from the repository:

* ``1BT01.1.MXX30.001dg.nc``: 2022-02-01 00:10;
* ``1BT01.1.MXX30.002dg.nc``: 2022-02-01 00:20.

Neither file contains stored radar reflectivity. Their ``ACPRR`` field is
accumulated rainfall amount in mm. The plotting script derives a ten-minute mean
rain rate and applies a declared rain-only Z–R approximation:

.. math::

   R = \frac{A_{00:20}-A_{00:10}}{1/6\ \mathrm{h}},\qquad
   Z = 200 R^{1.6},\qquad
   \mathrm{dBZ} = 10\log_{10}\!\left(\frac{Z}{1\ \mathrm{mm}^{6}\,\mathrm{m}^{-3}}\right).

Here :math:`R` is in mm/h and :math:`Z` in mm⁶/m³. This is an illustrative
Marshall–Palmer-type choice, **not instantaneous model reflectivity**, an
observation, a calibrated tropical-rain retrieval or a validated FrameIt diagnostic.
It omits ice scattering and does not use a model drop-size distribution.
The historical background is Marshall and Palmer (1948),
`The Distribution of Raindrops with Size
<https://doi.org/10.1175/1520-0469(1948)005%3C0165:TDORWS%3E2.0.CO;2>`_;
a reference does not validate this approximation for these files.

Missing rainfall stays missing. Zero rain has :math:`Z=0` and dBZ :math:`-\infty`;
the display shows it below the colour scale, not as missing. White also includes
values below −10 dBZ; grey denotes missing values. Negative accumulation increments
cause failure rather than clipping a possible reset. No negative finite increment
was found in this pair. Sparse rain patches reflect this actual short interval;
they have not been filled, smoothed or extended.

The fixed geographical centre is the first file's MSLP minimum,
(-16.342215°, 62.154875°). Both extractions request full 500×500 km widths, which
give 167×167 native points at the resolved 3000 m spacing. The fixed run samples
``ACPRR`` on 43 radii at 6 km spacing and 180 azimuths. It interpolates rainfall
amounts **before** the external dBZ calculation; it does not interpolate dBZ.
The moving run uses the pressure-wind method with default 100/50 km search/refine
half-widths. Its centres move from native ``(cy,cx)=(380,732)`` to ``(380,731)``.
The files describe ``UM10/VM10`` as zonal/meridian 10-m winds in m/s, declared here
as Earth-relative. These two fixes illustrate extraction, not track validation.

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
   python example/plots/batsirai_reflectivity.py \
     /path/to/BATSIRAI-10mins \
     figures-batsirai/batsirai-fixed figures-batsirai/batsirai-moving \
     figures-batsirai/figures

The :download:`plotting script <../../../example/plots/batsirai_reflectivity.py>`
imports no FrameIt code. It requires a new figure directory outside the source
data directory. The configurations export ``ACPRR`` only; the moving tracker also
reads MSLP and the two horizontal winds. No three-dimensional field is needed.
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
