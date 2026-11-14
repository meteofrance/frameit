Coupled atmosphere and surface sampling
=======================================

Named atmospheric and surface sources share a geographical centre provider while
retaining their native grids, masks, field definitions and vertical coordinates.
The primary pair is atmospheric AROME GRIB plus EPyGrAM-decoded dense
AROME-47 / SURFEX-8.1 FA histories. Native atmospheric FA/SURFEX FA and compatible
NetCDF sources use the same coupling contract, subject to each adapter's limits.
See :doc:`fa_inputs`, :doc:`fa_baseline` and :doc:`fa_geometry`.

For the workflow, start with :doc:`../task_guides/coupled_inputs` and the complete
native source request in :doc:`fa_inputs`. Add a polar product only when needed.
Adapt paths/centres and verify all source declarations. The example radius and
SFX units/time are explicit declarations, not universal producer defaults;
``allow_unscaled`` remains false. Neither a unit label nor a plausible range
resolves the native missing-scaling guard.

Independent native sources and exact times
------------------------------------------

``region.center``, ``region.track`` or ``region.tracker`` supplies continuous
centres. Each source maps them onto its own footprint; equal shapes are not grid
identity. A centre outside a required source fails, with no edge substitution.
Model-grid crops can retain NaN padding beyond the source. Continuous centres,
snapped native points and vector bases remain distinct.

``region.sources_coupling_time_association`` defaults to ``exact``: selected native
source clocks may differ, but each required sample needs a centre. Explicit
``common`` records exclusions for the operation needing association. The narrow
AROME/NEMO NetCDF ``preceding_hour`` method does not admit FA histories.
Conflicting source cycles, ambiguous clocks or inconsistent SURFEX state/header
validity fail rather than being repaired by nearest-time matching. There is no
silent temporal interpolation, missing-to-zero fill or interval conversion.
See :doc:`../concepts/time_support` and :doc:`fa_inputs`.

Select a common polar target
----------------------------

Start with the complete ``atmosphere``/``surface`` request in :doc:`fa_inputs`.
That native-copy request does not need an interpolation kind for pressure.
For this polar example, add the following inside ``sources.atmosphere`` to
declare continuous interpolation where the input leaves kind unresolved.
Verify the selected pressure quantity first; the declaration is not inferred
from its name and cannot replace contradictory source metadata:

.. code-block:: yaml

   field_metadata:
     prmsl:
       kind: continuous

Then add this top-level polar product and supply a region centre provider as
described in :doc:`../task_guides/coupled_inputs`. It requests only the two fields:

.. code-block:: yaml

   products:
     polar:
       radius_km: 4
       shared_grid: true
       azimuth_count: 72
       fields:
         atmosphere: [prmsl]
         surface: [SFX.T2M]

``shared_grid`` defaults to false, retaining source-specific target resolution.
Only sources requested by the polar product participate. The centre provider
does not have to export fields. With no polar product, target arrays and the
interpolation dependency are not required.

The target uses the region's continuous centres and the product's radius/angular
controls. An explicit radial step cannot be finer than any participating native
grid. Omission resolves the **coarsest participating native spacing** and records
that evidence. Source methods, support thresholds, masks, units, vertical axes
and time associations remain distinct; shared coordinates do not harmonize physics.

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

A supplied moving track controls each source at every associated time, including
independent grids. An internal crop context cannot freeze its first centre or
replace continuous centres with snapped cells.

Verify coordinates, keep separate products
--------------------------------------------

Target verification checks actual radius/azimuth/geographic coordinates against
the associated continuous centre before publication. Sharing a horizontal target
does not merge or relabel native source clocks. A target signature describes
coordinates and Earth-model assumptions, not source-data identity, physical
equivalence, conservation, equal masks or bitwise field identity.

Preview/provenance records identify resolved axes/counts, source spacing evidence,
requested sampling, participants and target verification. Source IDs
``atmosphere`` and ``surface`` with run name ``coupled-surface`` produce:

.. code-block:: text

   coupled-surface.atmosphere.polar.nc
   coupled-surface.surface.polar.nc

Each requested source/product has one dataset; read each field's own dimensions
and coordinates. Unsupported combinations of native grids still fail.
Model-grid products retain their separately requested native/transformed
representations. Available inputs do not enable unrequested diagnostics.

Continuous production polar sampling defaults to bilinear point interpolation,
without an area-budget conservation guarantee or automatic experimental-method
switch. Proven categorical fields select nearest-neighbour; the public override
is ``interpolation: nearest``, not the backend name ``nearest_s2d``.
Unresolved kind and inapplicable methods fail. Source support labels, masks, IEEE NaNs,
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
     - Preserve/check eastward/northward component directions, sampling and pairing,
       not short names alone.
   * - Pressure-level ``u``, ``v``, ``t``, ``r``, ``z``
     - m s-1, K, %, m2 s-2; example 850/700/500 hPa, instantaneous.
     - Pressure labels use their actual coordinate units; RH is not specific
       humidity and geopotential is not geometric height.
   * - GRIB ``2t``/``2r`` at 2 m
     - K / %, instantaneous.
     - Near-surface temperature/RH metadata does not supply a missing SFX unit definition.
   * - ``SFX.SST``, ``SFX.T2M``, ``SFX.HU2M``, ``SFX.TSRAD``
     - Observed support labels SEA / FULL / FULL / FULL; gridpoint 120/24 encoding.
     - Verify physical meaning from source evidence. Packing-120 decoding records
       encoded scaling factors separately from native warnings; see :doc:`fa_contracts`.
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
:doc:`fa_spectral`. Use :doc:`ocean_netcdf` for the separate NEMO/CROCO adapters
and their grid, mask, current and vertical conventions.
