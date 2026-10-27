EPyGrAM C2: labelled geometry and selected metadata
===================================================

C2 starts from ``6a7e161`` on Python 3.13.16. It transfers the maintained FA
path's horizontal interpretation to EPyGrAM 2.1.0, following :doc:`fa_epygram_c1`.
Qualification covers compact modern regular-lon/lat CI and spherical tangent
Lambert CI/C fixtures, dense evidenced SURFEX histories and the existing declared
atmospheric full/interface cubes. Real-producer scientific approval remains open.
This is the C2 stage record. :doc:`fa_epygram_c4` completes retirement and migration;
the legacy-backend/extra and future-stage statements below describe the C2 checkpoint.

Geometry, Earth model and source identity
------------------------------------------

``fa_epygram.geometry_contract`` adapts the actual library geometry's dimensions,
``gimme_corners_ij``, ``ij2xy``, ``ij2ll``, projection and CRS to serializable
source-grid facts. ``fa_geometry`` labels these facts with ordinary xarray/CF
coordinates; it no longer interprets FA angular/header words on the EPyGrAM
dataset path. Missing qualified facts fail rather than selecting the manual path.

The worker transfers only one-dimensional native axes, CF CRS, CI/C/CIE bounds
and evidence origins, **O(nx+ny)** metadata. The parent expands geographical
coordinates from those library-derived axes/CRS. Native storage point budgets
apply before worker axis allocation and parent coordinate expansion. Physical
payloads remain lazy. Existing domain, anisotropy, finite-coordinate, nonpolar/
non-dateline, source-freshness and per-sample native-axis association checks remain.
Geometry discovery still precedes shared-target resolution and allocation planning.

EPyGrAM centres projected x/y on CI and uses a different false origin. A CRS
translation expresses those same points in FrameIt's established CF tangent-
latitude origin. This is a coordinate-origin adapter, not a fitted projection,
field interpolation, vector rotation or physical-coordinate diagnosis. CI/C
slices retain original zero-based ``source_i``/``source_j``; CIE is recorded but
not an output-selection option. Geometry masks cannot become valid coordinates.
Physical undefined masks, IEEE NaNs, support labels and valid zeroes stay distinct.

Projected geometry requires explicit ``input.fa.earth_radius_m``, passed into
the isolated library configuration and checked against its geoid. Its default
Earth model is never accepted as producer evidence. An angular regular grid can
leave the Earth model unresolved; its output does not acquire the library geoid.
Library CI corners must match the original encoded corners within the existing
``2e-5 degree`` header-precision bound. The radius is never estimated from them.

The EPyGrAM horizontal signature now describes library axes/CRS/zones and the
chosen output zone, independent of vertical header inheritance. Equal shapes
are insufficient: a shifted grid cannot share a source time sequence. Source
mapping continues to distinguish requested centres, selected points and snapping
offsets, with the existing ``fa_source_crs_native_axes_v1`` convention.

Selected fields and vertical metadata
---------------------------------------

After the selected native-error/spectral guard, the version-matched library
``_readH2DField(getdata=False)`` supplies metadata without the redundant
``field_type`` dispatch. For one selected record, measured FANION calls decrease
from three to **two** for inspection, and four to **three** for a data transaction.
Physical metadata decodes remain zero; a selected data transaction decodes one
record. These call counts are not a wall-time or memory throughput claim.
Original storage dimensions are checked even for metadata-only inspection that
does not request a labelled geometry; swapping X/Y cannot pass on point count alone.

The resource's ``vcoordinate.grid`` supplies pressure-valued A and B. One source-
level contract per transaction verifies all interface labels and exact
``A_Pa = PAHYBR * PREFER`` / ``B = PBHYBR`` agreement. Original normalized A and
PREFER remain observations, not a division by an assumed 101325-Pa constant.
Cube bounds use this checked library interface contract. Each selected field's
vertical grid must agree with the resource, and its original native label is kept.
The parent no longer rebuilds the coefficient contract for each source inspection.

Native/profile facts still precede explicit user completion; library tables do
not supply release-qualified units, per-field full/interface position or vector
basis. All declared records in a selected cube receive metadata checks; only
selected levels/times receive payload decodes. Original IDs, sparse/reordered
full/interface axes and the complete coefficient axis survive export. Required
wind companions and horizontal neighbours precede sparse selection; native and
analysis branches and idempotent preparation retain their existing contracts.
No new pressure/height diagnosis, averaging, extrapolation, wind assumption or
diagnostic is activated by available inputs.

Retained technical exceptions and GRIB decision
------------------------------------------------

* **Original FA header observation:** ``_raw_header_get`` on the owned resource
  retains discriminants/rotation/stretch flags, encoded CI corners, original
  normalized A and coefficient count. These are admission/independent-evidence
  facts omitted from the library object, not a second geometry engine. Two
  FACIES inquiries remain per transaction; eliminating this observation would
  discard the corner and normalization evidence.
* **Private library CRS/accessors:** EPyGrAM 2.1.0 has no public CRS accessor;
  ``geometry._proj.crs`` supplies it. ``_readH2DField`` fails closed on later
  encoding errors, and ``_readMiscField`` handles only allowlisted structural
  types. Version checks and native regression coverage constrain these APIs.
* **Selected FANION errors:** direct inquiry preserves -91/-93/-94 rather than
  the library's broad Misc fallback. Spectral execution remains gated.
* **Index facts:** bounded same-unit LFI lengths/counts/duplicate checks supplement
  ``listfields``, which omits cadre/DATX records and does not expose these guards.
* **L0/T0 and clock consistency:** narrow same-unit structural observations retain
  0/1 logical validity and mixed date/IEEE seconds. FADIEX rejects permissive
  clock normalization; two header-clock inquiries remain. No physical raw codec.
* **Scaling:** no qualified structured FMULTM/FMULTE query exists. The actionable
  diagnostic-text guard remains; absence of a warning is not identity proof.
* **Exact cube association:** ``CombineLevelsResource`` scans complete generic
  IDs, groups by library quantity definitions, and normally materializes joined
  fields; virtual fields retain resource handles. ``FA.sortfields`` also probes
  unrelated records. Neither establishes explicit research full/interface sampling
  or FrameIt's serializable selected-only Dask contract. Keep the small declared
  record/axis assembly, without a second library cube path or physical transform.
* **Legacy native backend:** its existing implementation remains the explicit
  compatibility baseline until C3/C4 gates pass. It is never an EPyGrAM fallback.

GRIB was evaluated against the actual 2.1.0 ``listfields(additional_keys, select)``,
``iter_messages(headers_only=True)`` and selected ``readfield`` APIs. The first
can collect keys, but alias mapping, per-message grid/unit/wind consistency,
unmapped products, cycle/time coverage and FrameIt's group semantics still need
an adapter. Changing requested key/selector arguments can rescan headers.
``iter_fields`` requests full messages, and ``readfields`` builds an index and
eager field objects; there is no qualified lazy multi-file xarray replacement.

Consequently ``preflight._grib_metadata`` remains the bounded metadata/coverage
scan, and ``grib_utils`` retains the requested-name selector plus cfgrib grouping,
lazy payloads, required wind geometry and native/analysis preparation. Replacing
only the key loop would add a separately configured GRIB-only helper/translation
without removing those responsibilities. C2 therefore makes **no GRIB switch**.
There are no competing production GRIB readers or hidden fallbacks. Any future
switch must be a separate isolated step with independent values/masks and complete
time/level/quantity/output parity. FA/GRIB same-process coexistence is not assumed.

Compatibility, provenance and verification
---------------------------------------------

Existing single-source/coupled YAML, explicit backend choice, helper paths and
native/vertical/source-qualified NetCDF schema retain their meanings. Exact
common times with warnings/full exclusions remain the default; strict stays
selectable. Continuous production polar sampling stays optional and bilinear,
without a conservation claim. Package extras/defaults await C4 migration.

Additive source provenance ``geometry_contract`` records the library axes/CRS,
native zones, origin translation and Earth-model origin. The historical key
``horizontal_header_signature`` is preserved, with a library-derived JSON value
on this backend; consumers must not assume its old raw-header layout. Dataset
attributes ``fa_geometry_origin`` / ``fa_earth_model_origin`` identify the adapter.
No exported scientific variable/dimension, precision, compression, masks, time
or physical definitions are renamed. Fresh ordinary readers verify outputs.

Independent truth includes Snyder spherical equations in both hemispheres with
off-origin anchors, asymmetric offset CI/C/E, ``1e-7 m`` canonical-axis agreement
and ``2e-11 degree`` inverse-equation agreement; regular ascending/descending
angular axes use ``1e-10 degree`` agreement. Existing tolerances are unchanged.
The GRIB check independently prescribes 700/850 hPa, date/cycle, units and known
5-by-7 values, compares both metadata APIs and reopens the selected baseline
NetCDF product without FrameIt/EPyGrAM. It explicitly distinguishes EPyGrAM's
85000-Pa field level from the native 850-hPa public coordinate.

The packaged record below contains actual versions, exact commands and results.
Final full suites each report **667 passed, 1 expected optionality skip and
2 subtests passed**. Native focused: **180 passed**; native CI: **136 passed**;
EPyGrAM CI: **137 passed**; spectral-native CI: **22 passed**. Core-only CI is
**85 passed / 109 confirmed dependency-only skips / 2 subtests passed**. The six-
case packaged matrix, schema examples, compact primary-pair dry-run, strict docs
and wheel build pass. Changed Python files pass Ruff; repository Ruff retains
four independently reproduced pre-existing findings in unchanged
``processing/polar/conservative.py`` (E501 89/153/323, B905 300).
No new private corpus read, large run, download or upload was performed. Remaining
real-producer units/scaling/support/geometry/vertical/vector references and human
scientific review are unresolved. Unsupported packed/typed/interval/spectral and
physical-coordinate families keep their gates.

**C3 prerequisites:** real GRIB containers with AROME conventions plus admitted
EPyGrAM SURFEX fixtures at multiple times on different native grids; moving centres,
common/strict exclusions, disabled/shared bilinear targets, sync/spawn source-
qualified exports and fresh ordinary-reader truth. Component regressions do not
claim this end-to-end qualification. C4 retirement additionally requires full
regression parity and explicit backend/extra/default migration evidence.

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_c2.yaml
   :language: yaml
