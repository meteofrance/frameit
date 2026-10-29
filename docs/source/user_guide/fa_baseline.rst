FA compatibility and limitations
================================

FrameIt provides a **limited native FA adapter**, using EPyGrAM 2.1.0 in isolated
worker processes. A library's broader format support does not establish FrameIt
support for every producer, layout or scientific operation. Start with
:doc:`fa_inputs` for inspection/declarations and :doc:`fa_environment` for the
single-environment installation and optional interpreter override.

The matrix below distinguishes implemented operations from metadata that is only
inspectable and operations that remain blocked. Implemented rows still require
valid geometry, selected field declarations, readable native encoding and the
decode-time scaling check. Compact independently prescribed fixtures exercise
these engineering/numerical contracts; they do not qualify arbitrary real fields
or constitute independent human scientific approval.

Current operation matrix
-------------------------

.. list-table:: Native FA support
   :header-rows: 1
   :widths: 25 36 39

   * - Family or operation
     - Current support
     - Requirements and limits
   * - Header/index and selected encoding inspection
     - Read-only metadata, names/lengths, clocks, source/directory facts and
       selected encoding flags or native errors.
     - An LFI index alone does not identify a supported FA producer, quantity or
       release. FA must be declared explicitly; suffixes are not evidence.
   * - Regional instantaneous atmospheric gridpoint records
     - Selected 2-D decode, labelled datasets, native extraction/export and
       explicitly requested eligible polar sampling.
     - ``profile: arome_history``, qualified modern regular-lon/lat or spherical
       tangent-Lambert geometry, explicit source units/kind/instantaneous meaning.
       Selected native errors and unknown scaling remain failures.
   * - Dense AROME-produced SURFEX histories
     - Selected horizontal real ``X1`` records, including categorical codes and
       individually named layer/patch records.
     - Evidenced AROME-47 / SURFEX-8.1 source tags, complete consistent FBUF,
       ``SFX.PACK=0``, storage-sized DIM1 and DIM2=-1, matching CI/state clock.
       ``PACK=0`` is a layout fact, not FA codec packing 0 or verified scaling.
   * - Explicit native atmospheric cubes
     - Selected gridpoint records on original full/interface labels, sparse
       selection and native/source/vertical-qualified NetCDF products.
     - Exact declared record associations and centre sampling; checked native
       A/B/PREFER and library vertical grid. No inferred pressure/height or
       full-level coefficients. See :doc:`fa_atmosphere`.
   * - Collocated physical wind pairs
     - Existing explicitly selected wind preparation and magnitude/polar products.
     - Declared matching Earth/grid basis, physical-velocity scaling and
       companions. Unresolved staggering/map scaling and additional producer
       vector conventions remain blocked; cube support is not vector validation.
   * - Coupled atmospheric GRIB/NetCDF plus FA, or native FA/FA
     - One geographical track, independent source grids/products, exact-common
       default or strict times, optional shared bilinear targets.
     - Each source must satisfy its own adapter contract. No common native
       indices, nearest-time substitution or automatic quantity equivalence.
       See :doc:`fa_surface`.
   * - Small typed structural metadata
     - Evidenced ASCII/integer/0-or-1 logical/real/date structure and directory facts.
     - Observed release/type/length checks; structural readability is not
       permission to decode physical arrays. See :doc:`fa_contracts`.
   * - Spectral records, including observed 103/18 encodings
     - Encoding/header facts only; physical decoding, raw coefficient export,
       transformed datasets, extraction and polar products are blocked.
     - Qualified coefficient/scaling/header-to-transform contracts and trusted
       native-grid references are missing. A library-only Fourier evaluation
       does not supply them. See :doc:`fa_spectral`.
   * - Packed SURFEX, support-map reconstruction, X2 or physical N1/L1/C1 arrays
     - Not supported for physical execution; available directory facts can be inspected.
     - Need release-matched type/order/support-map/missing-value definitions and
       independent decoded/scatter-gather references. C1 here is a native character
       type code, not a physical scalar capability.
   * - Soil/snow/layer/patch/tile axes or averages
     - Original dense 2-D record names can be selected; assembled scientific axes
       and weighting are not inferred.
     - Need original indices, bounds, fractions, masks and trusted layer/tile data.
   * - Accumulated/averaged/extreme FA fields, rates and static/PREP products
     - Only explicitly instantaneous FA physical records are admitted.
     - Need field-specific support/bounds/resets/signs/units and independent
       multi-time or static references. A header interval marker is insufficient.
   * - Other projections, global/reduced grids, other producers or plain LFI
     - Not supported by this adapter.
     - Need versioned native header/active-array mappings, actual Earth models,
       sampling/zone conventions and independent geographic/value references.

Regular lon/lat FA supports the complete ``CI`` grid only. Spherical tangent
Lambert supports selected ``CI`` or ``C`` zones with an explicit Earth radius;
rotated, stretched, academic, secant/ellipsoidal, dateline-crossing and polar
variants are not admitted. See :doc:`fa_geometry` for exact numerical choices.

FA-only tracking supports ``fixed_box`` or ``prescribed_track``. For atmospheric
trackers, use a qualified GRIB/NetCDF tracking source in a coupled run. Native
cubes do not themselves establish verified MSLP or pressure-level tracker inputs.
Diagnostics remain selected operations, not automatic consequences of available
fields. Continuous production polar sampling defaults to bilinear point samples,
without an area-budget conservation guarantee; categorical fields require an
explicit appropriate method such as ``nearest_s2d``.

Interpret failures without guessing physics
-------------------------------------------

* **Native -91/-93/-94 on a selected physical record:** execution fails rather
  than accepting a library metadata classification. Unselected records can remain
  indexed without payload reads. Observed ``SURFPRESSION``, ``S090TEMPERATURE``
  and ``S090WIND.U.PHYS`` header failures have no established encoding/cause from
  index lengths alone. Ask the producer/upstream for the exact native build,
  header/error specification and a trusted decode or known-good copy. The error
  alone does not establish corruption or harmless metadata.
* **Unresolved FMULTM/FMULTE scaling:** encoded packing-120 GRIB2 factors take
  precedence over the native warning; otherwise the default remains failure.
  ``allow_unscaled`` is a justified explicit identity-fallback permission, not a qualification or a
  unit conversion. No warning is not proof of identity scaling; see :doc:`fa_contracts`.
* **Incomplete/contradictory SURFEX directory or clocks:** obtain the required
  source/directory records and consistent state/header validity. Relabelling the
  stream as atmospheric cannot repair the missing evidence.
* **Geometry mismatch:** confirm source Earth model, zones, scanning and encoded
  corners; do not fit a radius or relax the numeric checks to obtain a plausible map.
* **Budget, timeout or transfer failure:** inspect storage size and selected work,
  then change declared budgets deliberately. A crop may require a complete native
  horizontal decode; point limits are not an RSS quota. See :doc:`fa_environment`.

Scientific evidence still needed
--------------------------------

Native names/flags, a readable index and plausible values do not establish
release-specific quantities, units, signs, temporal support, scaling, masks,
Earth model or vector/vertical sampling. ``KNIVER`` counts native levels, not a
producer/header release. A matching array shape does not prove a common grid.
Source size/mtime checks detect freshness changes, not content integrity or
corruption; package version strings do not verify the native Fortran revision.

Real-producer use still needs release-matched definitions, independently trusted
values/masks and geographic checkpoints with justified tolerances, appropriate
multi-time/cycle/reset examples, and scientific review. Missing native scaling,
unexplained selected errors and spectral/typed/interval references remain
unresolved. No implicit deaccumulation, pressure/height calculation, vector
conversion, averaging, extrapolation or missing-to-zero filling resolves them.
See :doc:`fa_contracts` for the facts retained in inspection and ordinary outputs.
