Best-track comparison method
============================

``best_track`` v1 is experimental. It formats model results for comparison
with the Météo-France RSMC La Réunion archive; it is not an official best
track. It does not estimate cyclone class, position uncertainty or Dvorak T/CI.

Physical and temporal inputs
----------------------------

Select one atmospheric source. Bind actual names for mean sea-level pressure
and 10 m Earth-relative scalar wind speed or a collocated component pair.
A name like ``U10`` is not height evidence. Use producer standard names,
units, an above-ground height coordinate or verified height attribute, and
physical/basis metadata. ``level`` selects an exact physical value with
units; ``group`` is for original selectors only. No storm motion is subtracted.
Missing evidence leaves the affected metric unavailable; conflicting
evidence, such as an explicitly different height, fails admission.

Each field sample must match the saved centre time exactly. The native and
forecast-reference calendars must support the admitted Gregorian clock.
A crop's ``center_time`` does not replace its field clock. Independent field
grids remain distinct; unresolved member or cycle choices are refused.

``require_10min`` requires a scalar mean over 600-second recorded bounds or
explicitly compatible component-mean evidence. The magnitude of mean
components is not a mean of scalar speed. Cadence or a CF sampling interval
does not prove mean duration. ``native_proxy`` permits a known native
statistic in companion variables, not in strict RSMC columns. Optional gust
requires evidence of 10 m height, a 3-second operator and a compatible
reference interval. Unresolved equivalence leaves it missing; there is no
gust factor.

NetCDF admission can read CF ``height`` above ground or the producer's
``height_above_ground_m``. It checks a compatible component-mean convention
only when producer metadata includes
``sustained_wind_convention: magnitude_of_mean_components_compatible_10min``.
Likewise, gust qualification needs ``gust_duration_seconds: 3``, recorded
maximum support and an explicit producer relationship to the pinned profile
in ``gust_reference_profile``. These are evidence from the producer, not
labels to add to force an otherwise unsupported comparison.

Finite-disc estimators
----------------------

Distances and initial bearings use the source's declared sphere or ellipsoid.
The ``structured_center_perimeter_v1`` support test uses the outer native
sample centres, a local centre-based azimuthal-equidistant projection, and
a 1 m containment guard. Geodesic short-edge bounds and native adjacency
must support the disc. Finite data in a window do not prove the disc fits it.

Maximum wind is the largest admitted speed in the core disc. Central
pressure is the lowest admitted mean sea-level pressure in its own disc.
Rim extrema or stronger winds outside the core are not strict comparisons.
Incomplete support can leave a wind lower bound or pressure upper bound,
not a resolved result. The centre never moves to the extremum.

Wind radii are the farthest native sample at or above 28, 34, 48 or 64 knots
per compass quadrant. Bearing starts from geographic north, clockwise,
with half-open quadrants at 0, 90, 180 and 270 degrees. The exact centre has
no direction. A qualifying rim sample censors the result. Only full support
with no threshold exceedance gives a zero. Disconnected strong winds within
the finite disc can contribute.

RMW uses ``sum(area × speed) / sum(area)`` in each radial bin and returns
the midpoint of the unique interior peak. A named physical area field or
verified CF ``cell_measures`` area must match the wind grid; there is no
equal-weight assumption. Whole native cell areas weight sample centres in
half-open bins, including the final outer edge. Every azimuth sector needs
samples in the peak and its neighbours. The peak tolerance is the larger of
``1e-10 m/s`` and ``1e-12 × max(abs(bin mean))``. Tied peaks remain missing;
a smaller secondary peak is flagged.

Output and method evidence
--------------------------

Canonical float64 SI values retain all saved times and quality flags.
``*_observed`` and ``*_bound`` distinguish restricted estimates and bounds;
``*_native_proxy`` is separate from qualified estimates. RSMC CSV has exactly
29 columns at exact 00, 06, 12, and 18 UTC times, in knots, hPa and nautical
miles. Missing entries are blank. Round nonnegative integers to nearest,
with halves upward. Positive radii below half a nautical mile remain blank
with ``below_export_resolution``; thresholds and differences use unrounded
values. The units are 1 nautical mile = 1852 m, 1 knot = 1852/3600 m/s,
and 1 hPa = 100 Pa.

The `Météo-France archive and technical description`_ support this profile.
The 2026-10-07 description uses inclusive thresholds, unlike the older
dictionary wording. Bousquet et al. (`2020 <https://doi.org/10.1002/asl.950>`__)
demonstrate use of intensity and structure in the SW Indian Ocean.
Knaff et al. (`2016 <https://doi.org/10.1175/MWR-D-15-0267.1>`__) support
quadrant wind extent, not this finite-disc implementation. Gao et al.
(`2021 <https://repository.library.noaa.gov/view/noaa/32299>`__) use
radial-binned azimuthal-mean wind; FrameIt retains Earth-relative winds
and uses native cell-area weighting. That adaptation is not the study's
full method or a reproduction of agency eyewall analysis.

Tests compare discrete extrema and quadrant extents with independent
synthetic calculations, exercise a dateline perimeter and annular peak
decisions, and compare identical original and cropped samples. Real-producer
qualification, complex-grid support and independent scientific review remain
open. Completion is not evidence of observational equivalence or forecast skill.

.. _Météo-France archive and technical description:
   https://www.data.gouv.fr/datasets/historique-des-cyclones-tropicaux-du-sud-ouest-de-locean-indien
