Coupled atmosphere and surface sampling
=======================================

Named atmospheric and surface sources share a geographical track while retaining
their own native grids, masks, field definitions and source/vertical-qualified
products. The primary pair is atmospheric AROME GRIB plus EPyGrAM-decoded dense
AROME-47 / SURFEX-8.1 FA histories. Native atmospheric FA/SURFEX FA and compatible
NetCDF sources use the same coupling contract, subject to each adapter's limits.
See :doc:`fa_inputs`, :doc:`fa_baseline` and :doc:`fa_geometry`.

Use ``example/config_file/coupled_fa.yaml`` for base extraction,
``coupled_cyclone_polar.yaml`` for selected scalar polar fields with a supplied
track, or ``coupled_arome_fa_polar.yaml`` for separate native FA streams.
Adapt paths/centres and verify all source declarations. The example radius and
SFX units/time are explicit declarations, not universal producer defaults;
``allow_unscaled`` remains false. Neither a unit label nor a plausible range
resolves the native missing-scaling guard.

Independent native sources and exact times
------------------------------------------

The tracking source supplies continuous centres. Each secondary source maps them
onto its own footprint and selects its own native indices; equal shapes are not
grid identity. A required source with a centre outside its footprint fails, with
no edge substitution or spatial time skip. Boxes can retain NaN padding beyond
the source. Requested centres, snapped source points and vector bases remain distinct.

``input.time_alignment: common`` selects exact common valid times by default,
with warnings and complete per-source exclusions in provenance/final status.
``strict`` requires identical source times and prescribed-track coverage.
Conflicting cycles, ambiguous clocks or inconsistent SURFEX state/header validity
fail rather than being repaired by a nearest-time match. There is no temporal
interpolation, missing-to-zero fill or automatic interval conversion.
See :doc:`fa_inputs` for complete time and calendar requirements.

Select a common polar target
----------------------------

This fragment opts into one target; merge it into a complete coupled configuration:

.. code-block:: yaml

   polar:
     enabled: true
     shared_target: true
     radial_step_m: 4000
     azimuth_count: 72
     interpolation_method: bilinear

``shared_target`` defaults to false, retaining independent per-source sampling.
It is a coupled-run setting: source-level copies must agree with the top-level
value. In a single-source run it has no additional effect. Only enabled sources
with selected polar fields participate, and ``tracking.source`` must participate.
With polar disabled, no target arrays or interpolation dependency are required.

The target uses the tracking source's continuous centres, common physical domain
radius, angular convention and ellipsoid. Explicit radial steps must agree and
cannot be finer than any participating native grid. When omitted, this selected
mode resolves the **coarsest participating native spacing** and records that
origin. Unspecified secondary angles inherit the reference target; explicitly
conflicting axes or ellipsoids fail. Source interpolation methods, support
thresholds, masks, units and vertical coordinates remain independent.

Source metadata, units, wind frames and native geometry are checked **before**
common sampling/allocation. The effective per-source, complete-time target budget
is then checked. An unused fine-grid intermediate cannot reject a valid common
target; invalid native grids, too-fine requested sampling or genuine budget excess
still fail before payload reads/target construction.

For a compact 1-km/3-km pair with two common times, a 4-km outer radius and
9 azimuths, the default shared step is 3 km and radii are 0/3/4 km. That gives
``2 * 3 * 9 = 54`` target points per source: a 60-point budget fits, a 53-point
budget does not. These are target-allocation counts, not a full-native decode
budget, peak-memory estimate or a physical-resolution accuracy guarantee.

A supplied moving track controls each secondary polar origin at **every** time,
even with ``shared_target: false``. The secondary source's internal fixed-box
context cannot freeze its first centre. Standalone fixed-box freezing remains
its own behavior; coupled continuous centres are never replaced by snapped cells.

Verify coordinates, keep separate products
--------------------------------------------

Every participating output group is checked against the continuous track and
other groups using exact time/radius/azimuth/longitude/latitude values. A mismatch
fails before scientific product export. Products carry a common
``common_polar_target_id`` and ``common_polar_reference_source``. This signature
describes ordered target coordinates and ellipsoid, not source-data identity,
physical equivalence, conservation, equal masks or bitwise field identity.

Effective axes/counts, source spacings, requested sampling, resolution origin,
participants and verification status are recorded under ``common_polar_target``
in preflight, resolved configuration, provenance and final status as appropriate.
Source IDs ``atmosphere`` and ``surface`` produce, for example:

.. code-block:: text

   SIMU.polar.atmosphere.surface.nc
   SIMU.polar.atmosphere.isobaricInhPa.nc
   SIMU.polar.surface.surface.nc

An atmosphere with several vertical groups still produces several files.
An existing ID such as ``surfex`` keeps that qualification in its filenames.
Cartesian products retain native source grids. No variables are merged across
incompatible grids, and no diagnostic is enabled just because its inputs exist.

Continuous production polar sampling defaults to bilinear point interpolation,
without an area-budget conservation guarantee or automatic experimental-method
switch. Categorical X1 fields require explicit ``nearest_s2d``; default bilinear
fails before their payload read. Source support labels, actual masks, IEEE NaNs,
extension zones and valid zeroes must not be equated or silently filled.
See :doc:`output_files` for ordinary readers and per-product atomic publication.

Quantities, units and temporal meaning
--------------------------------------

Select actual quantities needed for downstream analysis. The following finite
examples describe observed metadata and interpretation limits, **not** an
automatic preset or a release-qualified physical catalogue. Inspect your own
records/levels/cycles; names and library tables are not independent validation.

.. list-table:: Atmospheric/surface field distinctions
   :header-rows: 1
   :widths: 29 30 41

   * - Quantity / example identity
     - Units and support to verify
     - Interpretation / unresolved evidence
   * - MSLP: GRIB ``prmsl`` / ``meanSea``
     - Pa, instantaneous valid time.
     - MSLP is not surface pressure; do not substitute one for the other.
   * - Near-surface winds: GRIB ``10u``/``10v`` at 10 m
     - m s-1; observed ``uvRelativeToGrid=0``.
     - Preserve/check Earth-relative basis, sampling and pairing, not short names alone.
   * - Pressure-level ``u``, ``v``, ``t``, ``r``, ``z``
     - m s-1, K, %, m2 s-2; example 850/700/500 hPa, instantaneous.
     - Pressure labels use their actual coordinate units; RH is not specific
       humidity and geopotential is not geometric height.
   * - GRIB ``2t``/``2r`` at 2 m
     - K / %, instantaneous.
     - Near-surface temperature/RH metadata does not supply a missing SFX unit definition.
   * - ``SFX.SST``, ``SFX.T2M``, ``SFX.HU2M``, ``SFX.TSRAD``
     - Observed support labels SEA / FULL / FULL / FULL; gridpoint 120/24 encoding.
     - Release-matched physical units/scaling/time/support remain unresolved.
       An observed missing-FMULTM/FMULTE T2M decode is not an accepted physical value.
   * - Native layer/patch states ``SFX.TG1P1`` / ``SFX.WG1P1``
     - Dense individual records, observed NATURE label and 120/24 encoding.
     - Keep the exact native IDs. No depth, patch/tile axis, fraction or average
       follows from the names or support label.
   * - ``slhf``, ``sshf``, ``ssrd``, ``strd``
     - Observed GRIB accumulated J m-2, with 0–12-hour support in the example.
     - Energy is not instantaneous W m-2 flux. Preserve source sign/bounds;
       no automatic rate, deaccumulation or sign reversal.
   * - GRIB ``tirf`` (time integral of rain flux)
     - Observed kg m-2 accumulated over 0–12 hours.
     - Rain amount is not a rate; interval/reset evidence is required for conversions.
   * - Turbulent stresses ``iews`` / ``inss``
     - Observed N m-2, ``stepType=accum`` with 0–12-hour keys.
     - Instantaneous labels conflict with accumulated temporal metadata;
       interpretation remains unresolved rather than guessed.

Exact IDs such as ``SFX.H``, ``SFX.LE``, ``SFX.FMU``, ``SFX.FMV`` and ``SFX.RAIN``
were not established in the inspected selection. This is not a claim about every
producer or permission to choose a different field by analogy. Unestablished SFX
humidity units/specific-humidity identity likewise remain unresolved.

Dense SURFEX scope and remaining limits
---------------------------------------

The admitted dense branch uses complete AROME-47/SURFEX-8.1 source/directory facts,
``SFX.PACK=0``, ``X1``, ``DIM1=storage X*Y`` and ``DIM2=-1``. IMAX/JMAX and DIM_FULL
describe CI, which need not equal complete storage. Layout PACK and native FA
codec packing are distinct. Dense directories do not establish native scaling.
Full/point/strided/reversed selections preserve prescribed values/NaNs/real zeroes;
categorical codes keep their declared units/kind and float64 decoded representation.

No sparse support map is guessed. Individually selected layer/patch records remain
2-D; no soil-depth, layer/tile or atmospheric axis is inferred. X0/X2 and physical
N1/L1/C1 arrays remain blocked: C1 is a native character-array type. Incomplete
NAME/TYPE/MASK/SIZE/dimension/source records are reported as missing; any surviving
``SFX.*`` namespace requires the source/directory contract and cannot be relabelled
atmospheric to bypass it. Available metadata can still be inspected without
accepting physical execution. See :doc:`fa_contracts`.

Compact independent native/GRIB/NetCDF cases cover multiple times, different
grids, moving centres, planning/replay, masks/zeroes, sync/spawn exports and fresh
ordinary readers. Shared coordinates are checked exactly; constant polar scalar
fixtures use the existing absolute ``1e-9`` interpolation bound. These are finite
engineering/numerical checks, not scientific validation of real producer fields.

Packed layouts require release-specific maps/order/coverage and trusted
scatter-gather references; scientific layer/tile axes require original indices,
bounds/fractions/masks. Real sources still need physical definitions/scaling,
Earth-model/geographic checkpoints and appropriate multi-time references/review.
Selected spectral/native-error, vertical/vector and interval operations retain
their separate limits in :doc:`fa_baseline`, :doc:`fa_atmosphere` and
:doc:`fa_spectral`. No pressure/height, rates, averaging or new diagnostic follows
from a shared target. Generic NetCDF orchestration is **not CROCO/WW3 support**;
marine grids, masks, staggering, vertical coordinates and physical conventions
need their own adapters and evidence.
