Scientific qualification and product migration
==============================================

Run and retain the evidence
----------------------------

FrameIt samples geodesically defined storm-centred target points, rather than
performing a stereographic map projection. Bilinear interpolation samples scalar
values and earth-relative east/north winds; rotation uses the terminal-forward
geodesic bearing at each target. Tangential wind is positive clockwise.

.. code-block:: bash

   python -m frameit.testing.polar_qualification --output ./runs/polar-qualification
   python -m frameit.testing.polar_qualification --example --output ./runs/analytical-vortex
   frameit run-all-tests --output ./runs/all-tests

Each output directory must be fresh or empty. The small example exports
``analytical-vortex.nc`` and plots truth/sampled profiles, radial/tangential errors,
and harmonic amplitudes and peak directions in ``vortex-diagnostics.png``.

The complete qualification writes:

* ``summary.json``: compact fixture parameters, finest errors, convergence orders,
  target-grid radius-of-maximum-wind comparisons and failed gates;
* ``qualification.json``: source/target sampling parameters, common valid-point
  counts, physical and normalized errors, radial profiles, complex coefficients,
  phase comparisons, centre offsets, software provenance and resource observations;
* ``analytical-vortex.nc`` and ``moving-masked-vortex.nc``: independently checked
  reloads, including dynamic masks and clipped-domain quality flags;
* ``convergence-and-profiles.png``: visual evidence supplementing numerical checks.

Analytical definitions
----------------------

``frameit.testing.analytic_vortices`` evaluates source values and exact target
values directly, without frameit's interpolator or component-rotation functions.
Geodesic fixtures use WGS84 distance and terminal bearing independently through
pyproj. Existing geometry tests separately check published Karney coordinates.

The geodesic kinematic vortex uses
:math:`f(r)=(r/R)\exp[(1-(r/R)^2)/2]`, :math:`v_t=V_0 f` and
:math:`v_r=-U_0 f`, with :math:`R=40` km and :math:`|V_0|=50` m/s.
Northern-hemisphere cyclonic fixtures use negative :math:`V_0`; southern ones
use positive :math:`V_0`. Inflow cases use :math:`U_0=5` m/s. These are prescribed
kinematic profiles, not a claim about ellipsoidal Gaussian vorticity.

The planar Gaussian-vorticity oracle derives
:math:`V_\gamma=Ab^2[1-\exp(-(r/b)^2)]/(2r)` from Zhao et al. (2019), Eq. (2),
using :math:`A=1.5\times10^{-3}` s\ :sup:`-1`, :math:`b=45` km, stable ``expm1``
and the regular origin limit. Its RMW is :math:`1.1209064228 b`; centre offsets
are fractions of that derived RMW. Planar fixtures use an azimuthal-equidistant
x/y chart and prescribe its Cartesian velocity values as local east/north
components. Their target truth includes the resulting curved-Earth basis change.
They do not assert the same vorticity identity on an ellipsoid.

The asymmetric streamfunction adapts Zhao et al., Eq. (4), with mathematical
angle counterclockwise from east, :math:`u=-\partial_y\psi` and
:math:`v=\partial_x\psi`. A documented quintic C2 switch makes it zero below
5 km, transitions between 5 and 15 km, and leaves the published radial Gaussian
unchanged outside 15 km. The oracle includes the switch derivative. Refinement
metrics use an annulus from 20 km. Streamfunction displacement fractions refer
to its 40-km envelope radius, not an axisymmetric RMW.

Scalar references include a constant, the periodic geographic field
:math:`q=2+\cos^2\phi\sin(2\lambda)`, and modes 1--3 with a near-origin
:math:`r^m` envelope. At the true centre the positive-mode coefficient is
:math:`c_m=A_m(r)\exp(-im\theta_0)/2`, with :math:`\theta_0=0.37` radians.

Experiment and tolerance policy
-------------------------------

Source grids are refined from nominal 8 to 4 to 2 to 1 km while target radii
(2-km spacing) and 128 endpoint-exclusive angles remain fixed. Geographic and
smooth curvilinear cases cover both hemispheres, 60-degree latitude and the
antimeridian. Pointwise RMS/max errors are not area-weighted integrals. Scalars
are normalized by their prescribed amplitude (one); vector errors are normalized
by the maximum prescribed speed on the target grid, including radial leakage
from tangential-only winds.

Designated smooth interior scalar and tangential fields require observed order
:math:`p\geq1.7` over the finest two intervals. Inflow radial components also
require this order. Constants must agree within :math:`10^{-12}`. Finest wind
RMS errors must be below 0.05 m/s and the smooth scalar below :math:`10^{-6}`;
the geodesic profile RMW must be within one 2-km target interval of sampled truth.
These engineering bounds reflect the 40--45-km vortex and 15-km asymmetric
envelope scales relative to 1-km source spacing; they are not published cyclone
paper acceptance thresholds or universal guarantees for arbitrary model fields.

Centre sweeps hold source fields fixed and sample exact east/north truth about
displacements of 0, 0.05, 0.1 and 0.25 reference radii in several directions.
The appropriate oracle rotates about each displaced centre: radial wind can
legitimately emerge from a vortex tangential about its true centre. Fractional-cell
translations quantify grid-alignment error and must improve under refinement.
Angular sweeps hold 1-km source spacing fixed and use 16, 32, 64 and 128 angles.
Complex errors are compared directly; peak direction is checked only above
coefficient floors of 0.1 m/s for winds or :math:`10^{-3}` for scalar harmonics.
Near-zero coefficients do not have meaningful phases, and high unresolved modes
can alias on a coarse grid. A partial-sector mean is not an unbiased full-ring mean.

Accuracy metrics use an oracle-declared common set: missing required points
invalidate a score instead of lowering its RMS. Separate clipped-domain and
changing-sector experiments check coverage and eligibility through export.
The report distinguishes actual model-boundary mapping loss from missing-data
support. NetCDF reloads also exercise full-ring means, FFTs and plotting closure.
Cached/uncached and eager/Dask products are compared at tight tolerances. Backend
versions and resource measurements apply to the environment recorded in the report.

The AROME BATSIRAI/MNH CHIDO matrix covers fixed/moving origins, supplied tracks,
scalar-only, U-only, V-only, speed-only, W-only, sparse levels and coarse angles.
Its contract/norm checks complement analytical truth, not observational validation.
Cropped CI data do not establish coverage of the pressure-centroid tracker's
500-km reference ring; retain its dedicated tests and use full-domain inputs for
that scientific comparison.

.. _wind-preparation-method:

Wind preparation method record
------------------------------

**Quantity and status.** Implemented preparation of physical horizontal velocity
components and Meso-NH vertical W for extraction, tracking and polar sampling;
this is not a new stable diagnostic. Location/basis choices and examples are in
:ref:`wind-grid-contract`; declarations are in
:doc:`/user_guide/configuration_file`.

**Inputs and conventions.** Each pair declares its group, U/V names and Earth or
grid basis; a grid pair declares exactly one rotation method. Components
normalize to m s-1 per input file before concatenation. Collocation uses labelled,
finite, strictly monotone native coordinates and actual mass targets, before
cropping/subsetting removes neighbours. Linear interpolation between coordinates
:math:`s_0,s_1` uses :math:`q(s)=(1-t)q_0+tq_1`,
:math:`t=(s-s_0)/(s_1-s_0)`. No extrapolation or lone-neighbour substitution is
used. Missing contributing values remain missing; an exact source-node target
does not require the unused neighbour. Meso-NH vertical coordinates are model
coordinates, not assumed constant geometric altitude. W-to-mass target selection
and preservation of other interface fields follow :ref:`wind-grid-contract`.

For angle :math:`a` counterclockwise from east to positive grid x:

.. math::

   u_E = u_g\cos a-v_g\sin a, \qquad
   v_N = u_g\sin a+v_g\cos a.

These are physical vector components: no map-factor scaling or storm-motion
subtraction is applied. ``coordinate`` converts the named angle to radians.
``mesonh_projection`` uses
:math:`a=\mathrm{BETA}-\mathrm{RPK}\,\mathrm{wrap}(\lambda-\mathrm{LON0})`
in degrees, wrapping to [-180, 180), then converts to radians. BETA/LON0 are
degree-valued Meso-NH metadata; RPK must be in [-1, 1]. Cartesian Meso-NH geometry
is excluded. ``geolocation`` estimates signed native-axis directions from local
WGS84 neighbour bearings, including descending axes. It rejects degenerate,
reflected or nonorthogonal geometry (absolute cosine of axis separation > 0.02)
and sharp neighbour-direction changes (cosine < 0.99). These are implementation
support thresholds, not universal scientific accuracy criteria.

**References and departures.** The `Meso-NH grid documentation
<https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/grids.html>`_
describes the Arakawa C-grid convention and cites Arakawa and Lamb (1977).
Projection metadata are defined by `NAM_GRID_PRE
<https://mesonh.readthedocs.io/en/mnh-6-0/documentation/users_guide/executables_namelists/namelists/nam_grid_pre.html>`_.
The projection-angle sign follows the EPyGrAM software convention in
`netCDFMNH._read_geometry
<https://github.com/UMR-CNRM/EPyGrAM/blob/master/src/epygram/formats/netCDFMNH.py>`_
and `ProjectedGeometry.compass_grid/reproject_wind_on_lonlat
<https://github.com/UMR-CNRM/EPyGrAM/blob/master/src/epygram/geometries/ProjectedGeometry.py>`_,
without optional map-factor correction. These source conventions and software
references are not evidence of independent scientific sign-off. Geolocation is
a local finite-neighbour approximation, not a conservative transformation.

**Verification and tolerances.** Under ``src/frameit/testing/numerical/``,
``test_wind_reference.py`` checks quarter-turn vector truth, metadata conflicts,
idempotence and independently projected axes. Projection-sign tests use pyproj
Mercator/Lambert/stereographic perturbations (north-component absolute tolerance
2e-7 m/s); 100-m geolocation fixtures allow 5e-5 m/s for one-sided boundary
direction error. ``test_wind_collocation.py`` and ``test_request_selection.py``
check coordinate-based interpolation and level mappings.
``test_native_extraction.py`` and ``test_grid_representations.py`` check labelled
faces, field-specific W, per-file units, independent NetCDF reopening, and
tracking/polar invariance under Cartesian choices. The latter's real-xESMF
synthetic 1-km-cell vector check allows 2e-4 m/s for spherical-cell curvature.
``test_wind_preflight.py`` checks declarations and shared tracker preparation.

**Metadata and remaining limits.** Effective configuration/provenance records
pair declarations and level choices; field metadata retains source basis,
collocation, rotation method/parameters, units and target location. AROME omega
and geometric vertical velocity remain distinct. Synthetic tests establish the
stated numerical contracts, not all real-model regimes. Real-data qualification
across Meso-NH releases/projections and independent scientific review remain
outstanding; large or strongly curved cells need separate assessment. No stable
diagnostic admission or general conservation claim follows from these checks.

Migrating older numerical products
------------------------------------

Intentional changes affect radial/tangential winds (local rather than launch
bearing), MNH native collocation, speed as the norm of sampled components,
continuous subgrid origins, and exactly uniform endpoint-exclusive angle grids.
At zero radius, radial/tangential components are undefined even when east/north
winds and speed are finite. Coverage and missing-data policies are explicit.

Schema-v2 configuration uses ``polar.radial_step_m`` in metres; migrate the old
``radial_resolution`` key explicitly. Output ``rr`` uses kilometres, ``theta``
radians and ``theta_deg`` degrees. Requested angular steps are maxima; effective
steps are uniform ``360/N`` and may differ for nondivisor requests.

For an old closed file, use the tested validation helper:

.. code-block:: python

   import xarray as xr
   from frameit.processing.polar.polar_utils import finalize_polar_output

   with xr.open_dataset("old-polar.nc") as source:
       migrated = finalize_polar_output(source.load())
   migrated.to_netcdf("endpoint-exclusive-polar.nc")

This removes a last column only when its angular separation is exactly one cycle
within coordinate precision and all angular fields and auxiliary coordinates
duplicate the first slice (including matching missing values). Already-open
files retain every column; inconsistent closed files fail. Irregular old grids
remain labelled directional samples and are rejected by full-ring FFT/mean
helpers. This topology migration does not recompute old winds or interpolation;
regenerate those products from native model inputs when numerical equivalence
with corrected sampling is required.

Compare files only after examining centres, Earth model, requested/effective
angles, masks, collocation and wind reference frames. Different choices describe
different products, even when dimension sizes happen to agree. Exported auxiliary
coordinates, basis/origin attributes and interpolation provenance preserve this
distinction.

Methodological references
-------------------------

* Zhao, Song, Leng and Zhao (2019), *Atmosphere*, 10, 300,
  https://doi.org/10.3390/atmos10060300 (Eqs. 2 and 4; phase-sensitive asymmetries).
* Ryglicki and Hodyss (2016), *JAMC*, 55, 531--559,
  https://doi.org/10.1175/JAMC-D-15-0125.1 (controlled centre-displacement design).
* Karney (2013), *Journal of Geodesy*, 87, 43--55,
  https://doi.org/10.1007/s00190-012-0578-z (geodesic geometry).
* Fischer et al. (2022), *MWR*, 150, 2255--2278,
  https://doi.org/10.1175/MWR-D-21-0223.1 (explicit azimuthal coverage screening).
