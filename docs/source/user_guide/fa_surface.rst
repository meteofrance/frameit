Coupled atmosphere and surface sampling
=======================================

Start with the named-source request in :doc:`fa_inputs`. Atmospheric AROME
GRIB/NetCDF or admitted FA and dense AROME-47/SURFEX-8.1 FA can share geographical
centres while retaining separate grids, clocks, masks, quantities and vertical axes.
Each source must meet its own :doc:`adapter limits <fa_baseline>`.

Verify paths, centres and field units/time against producer evidence.
For a nonstandard projected source, explicitly declare the producer's Earth
radius. Example field declarations are not defaults; ``allow_unscaled`` remains false.
Use :doc:`../task_guides/coupled_inputs` for a worked run. Add polar sampling only
when needed.

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
Add this top-level polar product and supply a region centre provider as
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

Validation checks source meaning/geometry and each source's full-time target budget
before constructing targets or reading payloads. Invalid grids, finer-than-native
requested spacing and budget excess fail.

For a compact 1-km/3-km pair with two common times, a 4-km outer radius and
9 azimuths, the default shared step is 3 km and radii are 0/3/4 km. That gives
``2 * 3 * 9 = 54`` target points per source: a 60-point budget fits, a 53-point
budget does not. These are target-allocation counts, not a full-native decode
budget, peak-memory estimate or a physical-resolution accuracy guarantee.

A supplied moving track sets each source's continuous centre at every associated
time; snapped extraction cells do not replace it.

Verify coordinates, keep separate products
--------------------------------------------

Target verification checks actual radius/azimuth/geographic coordinates against
the associated continuous centre before publication. Sharing a horizontal target
does not merge or relabel native source clocks. A target signature describes
coordinates and Earth-model assumptions, not source-data identity, physical
equivalence, conservation, equal masks or bitwise field identity.

Effective settings/provenance record axes/counts, source spacing, participants,
requested sampling and target verification. Source IDs
``atmosphere`` and ``surface`` with run name ``coupled-surface`` produce:

.. code-block:: text

   coupled-surface.atmosphere.polar.nc
   coupled-surface.surface.polar.nc

Each requested source/product has one dataset; read each field's own dimensions
and coordinates. Unsupported combinations of native grids still fail.
Model-grid products retain their separately requested native/transformed
representations. Available inputs do not enable unrequested diagnostics.

Numeric polar fields default to bilinear point interpolation,
without an area-budget conservation guarantee or automatic experimental-method
switch. Proven categorical fields select nearest-neighbour; the public override
is ``interpolation: nearest``, not the backend name ``nearest_s2d``.
The FA input declaration still requires ``kind``; polar does not require it for
the GRIB fields. Source support labels, masks, IEEE NaNs,
extension zones and valid zeroes must not be equated or silently filled.
See :doc:`output_files` for ordinary readers and per-product atomic publication.

Quantities, units and temporal meaning
--------------------------------------

Check quantity, units and time support before comparing sources. These examples
explain distinctions, not an automatic preset or a release-qualified catalogue.
Native names and library tables alone do not establish physical meaning.

.. list-table:: Atmospheric/surface field distinctions
   :header-rows: 1
   :widths: 29 30 41

   * - Quantity / example identity
     - Units and support to verify
     - Interpretation rule
   * - MSLP: GRIB ``prmsl`` / ``meanSea``
     - Pa, instantaneous valid time.
     - MSLP is not surface pressure; do not substitute one for the other.
   * - Near-surface winds: GRIB ``10u``/``10v`` at 10 m
     - m s-1; component-direction metadata.
     - Preserve/check eastward/northward component directions, sampling and pairing,
       not short names alone.
   * - Pressure-level ``u``, ``v``, ``t``, ``r``, ``z``
     - U/V: m s-1; temperature: K; RH: %; geopotential: m2 s-2.
       Verify pressure labels and instantaneous support.
     - Pressure labels use their actual coordinate units; RH is not specific
       humidity and geopotential is not geometric height.
   * - GRIB ``2t``/``2r`` at 2 m
     - K / %, instantaneous.
     - Near-surface temperature/RH metadata does not supply a missing SFX unit definition.
   * - ``SFX.SST``, ``SFX.T2M``, ``SFX.HU2M``, ``SFX.TSRAD``
     - Producer-defined units, support and encoding.
     - Declare verified physical meaning. SEA/FULL labels do not establish masks
       or units. Check packing-120 scaling separately; see :doc:`fa_contracts`.
   * - Native layer/patch states ``SFX.TG1P1`` / ``SFX.WG1P1``
     - Individual dense records, native support labels and encoding.
     - Keep the exact native IDs. No depth, patch/tile axis, fraction or average
       follows from the names or support label.
   * - ``slhf``, ``sshf``, ``ssrd``, ``strd``
     - For accumulated energy: J m-2, source interval/reset and sign.
     - Energy is not instantaneous W m-2 flux. Preserve source sign/bounds;
       no automatic rate, deaccumulation or sign reversal.
   * - GRIB ``tirf`` (time integral of rain flux)
     - kg m-2, accumulation interval and reset convention.
     - Rain amount is not a rate; interval/reset evidence is required for conversions.
   * - Turbulent stresses ``iews`` / ``inss``
     - N m-2; verify time support and signs.
     - If instantaneous labels conflict with accumulated temporal metadata,
       resolve the contradiction with the producer; do not guess.

Do not choose an SFX field by analogy with a GRIB name. In particular, a humidity
name does not establish units or specific-humidity identity.

Dense SURFEX scope and remaining limits
---------------------------------------

The admitted dense branch uses complete AROME-47/SURFEX-8.1 source/directory facts,
``SFX.PACK=0``, ``X1``, ``DIM1=storage X*Y`` and ``DIM2=-1``. IMAX/JMAX and DIM_FULL
describe CI, which need not equal complete storage. Layout PACK and native FA
codec packing are distinct. Dense directories do not establish native scaling.
Categorical codes keep their declared units/kind and float64 decoded representation;
missing values and real zeroes remain distinct.

No sparse support map is guessed. Individually selected layer/patch records remain
2-D; no soil-depth, layer/tile or atmospheric axis is inferred. X0/X2 and physical
N1/L1/C1 arrays remain blocked: C1 is a native character-array type. Incomplete
NAME/TYPE/MASK/SIZE/dimension/source records are reported as missing; any surviving
``SFX.*`` namespace requires the source/directory contract and cannot be relabelled
atmospheric to bypass it. Available metadata can still be inspected without
accepting physical execution. See :doc:`fa_contracts`.

Shared coordinates are checked exactly; compact constant-scalar checks use an
absolute ``1e-9`` interpolation bound. These numerical checks do not validate real
producer fields.

Packed layouts require release-specific maps/order/coverage and trusted
scatter-gather references; scientific layer/tile axes require original indices,
bounds/fractions/masks. Real sources still need physical definitions/scaling,
Earth-model/geographic checkpoints and appropriate multi-time references/review.
Selected spectral/native-error, vertical/vector and interval operations retain
their separate limits in :doc:`fa_baseline`, :doc:`fa_atmosphere` and
:doc:`fa_spectral`. Use :doc:`ocean_netcdf` for the separate NEMO/CROCO adapters
and their grid, mask, current and vertical conventions.
