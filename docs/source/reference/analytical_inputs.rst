Instructional analytical inputs
===============================

``python -m frameit.testing.documentation_example --tutorial translating --output data``
creates small deterministic inputs for :doc:`../task_guides/analytical_event`.
``stationary`` holds the centre fixed; ``missing`` adds a labelled static
hole and a categorical field. The original ``--output data/first-run.nc``
command still creates the separate first-run scalar.

Definitions
-----------

The atmosphere has a 25×25 latitude/longitude grid with 0.05° spacing and samples
at hours 0, 1 and 2 on 1 January 2000. The centre starts at 60°E, 20°S.
The translating case increases longitude by 0.1° per hour at constant latitude.
This prescribed path does not impose a constant metric translation speed.

Let :math:`r` be WGS84 geodesic distance from that time's centre. The signed
tangential wind and sea-level pressure are:

.. math::

   V_\theta(r) = (40\,\mathrm{m\,s^{-1}})
      \frac{r}{40\,\mathrm{km}}
      \exp\left[\frac{1-(r/40\,\mathrm{km})^2}{2}\right],

   p(r) = 101000\,\mathrm{Pa}
      - (5000\,\mathrm{Pa})\exp[-(r/40\,\mathrm{km})^2].

Positive tangential velocity is clockwise. Local east/north components
use the terminal-forward geodesic radial bearing; wind is zero at the centre.
Velocity magnitude peaks at 40 km. Pressure is minimal at the centre.
These are prescribed fields, with no dynamical-balance claim.

The atmospheric layer heights are 10, 1000 and 3000 m. Their instructional
temperature is :math:`300\,\mathrm K-(0.006\,\mathrm{K\,m^{-1}})z`.
Interfaces at 0, 500, 2000 and 4000 m carry
:math:`w=(0.001\,\mathrm{s^{-1}})z`. These fields illustrate separate axes,
not an atmospheric vertical discretization validated against a producer.

Ocean response
--------------

The ocean uses a coarser 13×13 rho-labelled grid with 0.1° spacing and its own
instantaneous samples at hours 0 and 2. At each ocean time it uses the same
prescribed centre as the atmosphere:

.. math::

   T(r,z,t) = 300\,\mathrm K + (0.01\,\mathrm{K\,m^{-1}})z
     - (2\,\mathrm K)\exp[-(r/40\,\mathrm{km})^2]\exp[z/(20\,\mathrm m)].

Here :math:`z` is height relative to the sea surface, at −30, −10 and 0 m.
The synthetic CROCO convention uses ``Vtransform=2``, ``s_rho=Cs_rho``
equal to ``[-0.75, -0.25, 0]``, bathymetry 40 m, critical depth 5 m and
zero surface elevation. Its declared formula therefore gives
:math:`z=40\,\mathrm m\,s_\rho`.
The surface-labelled rho sample is an instructional choice, not a claim of
CROCO producer conformance or ocean-response physics.

Coverage and verification
-------------------------

The baseline fields are finite. The ``missing`` variant sets atmospheric U/V
to missing at zero-based horizontal index ``(10, 11)``. Its ``surface_type``
has valid integer categories 0 (water) and 1 (land); categorical sampling requires
nearest-neighbour interpolation. The ocean's first row has a static land mask
and missing temperature. Missing samples are never replaced by physical zeroes.

Tests compare wind, pressure and temperature against direct formula evaluations
and reopen actual native/polar products with ordinary readers. Formula comparisons
use a 10⁻¹² absolute tolerance for float64 calculations. Interpolation has its
own error and coverage behavior; point sampling is not an area-budget calculation.
These checks establish the instructional definitions, not scientific validity
for real atmospheric or ocean-model outputs.

Each file is published atomically and existing paths are refused. The three-file
set is not a transaction: if generation fails part-way, retain that directory
for inspection and retry in a fresh directory rather than mixing attempts.
