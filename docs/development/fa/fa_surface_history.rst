.. note::

   Frozen developer evidence from 9b11d602c4fb05fb2adf74b699439de6a0b8625b.
   Commands, support statements and results below describe historical checkpoints.
   See the `developer index <README.md>`_ for current topics and the removal plan.

P3 coupled cyclone inputs and shared polar products
====================================================

This page records the P3 **AROME atmospheric FA + AROME-produced SURFEX FA**
qualification, with separate products on the same explicit polar target.
The current primary target is EPyGrAM-backed SURFEX FA + AROME GRIB; see
`fa_epygram_c3 <fa_epygram_c3.rst>`_ for the compact primary-pair qualification, and
`fa_epygram_c4 <fa_epygram_c4.rst>`_ for the sole maintained reader/default and migration.
The GRIB/SURFEX examples select EPyGrAM
with scaling fallback disabled. Other atmospheric producers and new
native-container adapters are outside this increment.
Existing native Cartesian products and vertical-group
file separation remain. This bounded P3 repair uses admitted dense SURFEX
histories; missing packed/layered/native-container references remain gates, not
permission to guess their meaning. See `fa_baseline <fa_baseline_history.rst>`_, `fa_contracts <fa_contracts_history.rst>`_
and `fa_geometry <fa_geometry_history.rst>`_ for the earlier evidence and limitations.

The scope repair adds direct two-time AROME-FA/SURFEX-FA qualification on 1-km
and 3-km native grids, with a 54-point common target under a 60-point budget.
The same target can be replayed from resolved YAML. A 53-point budget, too-fine
sampling, anisotropic source geometry and ambiguous source clocks still fail.
Source metadata and geometry are checked while target allocation is deferred;
no scientific safeguard is disabled to make a target fit.

Common target, independent sources
-----------------------------------

.. code-block:: yaml

   polar:
     enabled: true
     shared_target: true
     radial_step_m: 4000
     azimuth_count: 72
     interpolation_method: bilinear

``shared_target`` defaults to **false**, preserving existing per-source sampling
configurations. It is a coupled-run option; source-level copies must agree with
the top-level value. In a single-source run it has no additional effect.
Only enabled sources with selected polar fields participate; a participating
``tracking.source`` is required. Disabled polar processing requires no new
native or interpolation dependency and does not construct target arrays.

The common target uses continuous centres from ``tracking.source``, the common
physical domain radius, its angular sampling convention and its ellipsoid.
Explicit source radial steps must agree and cannot be finer than any
participating native grid. Without an explicit step, this selected mode resolves
the **coarsest participating native spacing** and records that origin. Unspecified
secondary angles inherit the reference target; explicit conflicting axes or
ellipsoids fail. Source interpolation methods, masks, support thresholds, grids,
vertical coordinates and units remain independent. Source metadata, units,
vector frames and native geometry are validated first. Then common sampling is
resolved and the **effective** per-source and complete-time point budgets are
checked. An unused fine-grid intermediate cannot reject a valid common target;
the 54-point common-target/60-point-budget regression verifies this ordering.
Invalid native grids, too-fine requested steps and genuinely oversized targets
still fail. The private deferred-planning marker is cleared before processing
and never enters resolved YAML or data graphs.

Secondary-source extraction is internally geometric/fixed-box, but a supplied
moving atmospheric track now controls its polar origin at **every** time.
Previously that internal method froze the surface polar centre at the first
time. Coupled orchestration now explicitly declares the supplied centres
authoritative, even when ``shared_target`` is false. Standalone fixed-box freezing
and constant-track static geometry are preserved; coupled requested centres are
never replaced by each source's snapped native cell.

Every participating output group is checked against the continuous reference
track and against other outputs using exact time/radius/azimuth/longitude/
latitude values. A mismatch fails before scientific products are exported.
Successful products carry the same ``common_polar_target_id`` coordinate hash
and ``common_polar_reference_source``. The hash describes ordered target
coordinates and ellipsoid, not source-data identity, physical equivalence,
conservation, equal masks or bitwise identity of sampled fields.

Effective axes/counts, native spacings, requested sampling, resolution origin,
participants, signature and verification status are recorded in preflight,
``resolved-config.yaml``, ``run-provenance.yaml`` and ``run-status.yaml`` as
appropriate. The manifest key is ``common_polar_target``. Existing exact-common/
strict time selection and complete exclusion reports are preserved; no nearest
times, missing-to-zero fill or automatic interval conversion is introduced.

Separate products and future NetCDF adapters
---------------------------------------------

Use source IDs ``atmosphere`` and ``surface`` to obtain, for example:

.. code-block:: text

   SIMU.polar.atmosphere.surface.nc
   SIMU.polar.atmosphere.isobaricInhPa.nc
   SIMU.polar.surface.surface.nc

An atmosphere with multiple vertical groups still has multiple source-qualified
files. Existing source IDs such as ``surfex`` keep their filenames. No variables
are merged across native grids, and diagnostics are not enabled simply because
their inputs exist. Continuous production sampling remains bilinear, without a
conservation guarantee or an automatic experimental-method switch.

The source/target/export boundary is independent of FA: a three-source synthetic
NetCDF test exercises the same contract and separate files. This establishes an
orchestration basis for later ocean/wave adapters, **not CROCO/WW3 compatibility**.
Those need their actual grids, masks, staggering, vertical coordinates and field
conventions. Do not relabel a marine NetCDF file as a supported atmospheric
producer just to open it. Such extensions are not active FA-phase requirements.

Cyclone-analysis field priorities and supplied-corpus evidence
--------------------------------------------------------------

Start with explicitly selected MSLP/near-surface winds, pressure-level winds,
temperature, moisture and geopotential, then SST and appropriate near-surface
thermodynamic fields. They support downstream cyclone structure, intensity and
environment analysis; this priority is not a stable diagnostic catalogue or an
automatic all-fields preset. RH and specific humidity, geopotential and geometric
height, surface pressure and MSLP remain different quantities.

Surface heat/momentum exchange, accumulated rain and land/layer/tile states are
important follow-ups when their source definitions and temporal support are
admitted. In particular, accumulated heat energy is not an instantaneous heat
flux. No rates, deaccumulation, sign reversal, soil-depth interpretation or tile
averages are inferred to complete an output.

The maintained manifest records the finite priority list and actual observations:

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_p3.yaml
   :language: yaml

The supplied files **are useful inputs**. A fresh read-only investigation scanned
574 GRIB message headers and six selected SURFEX encoding descriptors. GRIB
metadata provides MSLP, 10-m winds, isobaric u/v/t/r/z at the example levels,
near-surface temperature/RH, accumulated rain and heat energy. The stress records
``iews``/``inss`` have an unresolved interpretation conflict: their labels say
instantaneous, while ``stepType=accum`` and hours 0--12 are encoded. Their
semantics are not guessed. SFX humidity units and any unestablished specific-
humidity selection are likewise not filled by analogy with another model.

One selected native SFX.T2M decode was attempted under a 6,300,000-point budget,
requesting only one returned point. It failed the existing **missing native
scaling metadata** guard with ``allow_unscaled=false``. No decoded value was
accepted and no real atmosphere/surface product is certified by that probe.
Adding a K label or plausible range cannot resolve codec scaling. Existing
explicit user opt-in remains available only when justified; this repair neither
enables it nor edits native definition tables. The GRIB atmosphere and separate
SURFEX source remain the selected workflow; there is no silent field substitution.

Both source sizes and mtime_ns were unchanged, as recorded in the manifest.
This is stat freshness, not a checksum/corruption proof. The 16-GB native
atmospheric FA was not decoded in this increment. No full archive conversion,
private upload or large production run was performed. Independent geometry,
scaling and field/time references are still needed for real scientific
qualification; engineering compatibility is qualified separately below.

Dense layout and selection qualification
-----------------------------------------

Small generated native FA fixtures cover dense ``PACK=0`` horizontal ``X1``
records with reordered directories and separate FULL/SEA/NATURE labels. They
verify selection of one original layer/patch name without decoding other fields,
valid zeros, IEEE NaNs, read-only bytes, serializable lazy loading and ordinary
NetCDF reopening on a shared moving target. Raw packing-0 fixtures preserve
IEEE NaNs directly; that encoding does not carry the explicit undefined flag/
sentinel. No sentinel-recognition heuristic was added to the production reader.
``SFX.PACK=0`` describes the SURFEX layout; it is distinct from the native FA
codec's packing number (0 in these raw fixtures, 120 on the supplied selected
real fields). A dense directory does not resolve missing codec scaling.

Full-array, individual-point, strided and reversed selections are checked against
independently specified asymmetric values, including missing values and real
zeros. These are selections from **dense storage**, not qualified sparse/packed
support-map reconstruction. Categorical X1 values retain their original codes,
NaNs, declared units/kind and float64 decoded representation through ordinary
NetCDF readers. Categorical polar selection requires explicit ``nearest_s2d``;
the default bilinear method fails before payload reads. This does not admit N1,
L1 or C1 physical arrays: those, X0/X2 and inconsistent DIM1/DIM2 remain blocked.

The support label is retained separately from actual finite/missing samples.
There is no guessed sparse support map or conversion of absent surface types to
zero. Native record identities survive as individual 2-D variables, not invented
soil-depth, tile or atmospheric-level axes. Other producers, ``PACK!=0`` and
unqualified X2/typed physical layouts remain actionable failures, while their
directories can still be inspected. A partial SURFEX directory cannot be relabelled
as atmospheric FA to bypass producer/layout checks, including when PROGRAM and
all directory records have been lost. Any surviving ``SFX.*`` namespace requires
the existing complete source/directory contract. Missing NAME/TYPE/MASK/SIZE,
dimension arrays or required source tags are reported as
``surfex_metadata.missing_records`` in raw inspection; available producer facts
are retained. The private inspector with ``profile=None`` and
``validate_selection=False`` can probe available encoding flags without physical
decodes; its field descriptors explicitly block physical execution on incomplete
sources. Validated profile inventory also rejects the source before loading,
even without selected fields. New producer/container adapters are outside this phase.

The qualified engineering operations are selected 2-D decode/dataset/native
extraction/export and explicitly selected eligible polar sampling on the compact
dense fixtures. Individual layer/patch names remain separate 2-D records.
No new YAML keys, product names, dimensions, units, encodings or dependencies
are introduced by this follow-up. Descriptor-v1 sampling metadata is additive.
Malformed sources now fail earlier; changing their profile cannot repair their
missing native source/directory records.

Atmospheric native vertical-header facts are carried forward in the P1
descriptors (see `fa_contracts <fa_contracts_history.rst>`_) and checked on ordinary-reader native-pair
outputs. No field-level sampling location, hybrid units, native vertical index
or full/interface meaning is assigned from that header or a record-name pattern.
Native atmospheric cube and vertical-selector acceptance remains P5 work.

The native FA/FA starting example is
``example/config_file/coupled_arome_fa_polar.yaml``; the AROME GRIB/FA variant is
``example/config_file/coupled_cyclone_polar.yaml``. Their SFX unit/time and radius
entries are explicit declarations requiring confirmation, not new producer
defaults. It intentionally leaves ``allow_unscaled`` false and therefore does
not conceal the supplied native-scaling blocker. Replace paths/centre and review
the declarations before scientific use. Pure NetCDF or other independently
qualified fields can exercise the common-target contract without FA.

Remaining phase gates
-----------------------

Packed layouts need actual release-specific support maps/order/coverage and
trusted scatter/gather values. Full layered/tiled axes need producer indices,
bounds, fractions and masking conventions. Those future AROME/SURFEX admissions
are not silently qualified by the dense branch. Other producers, plain-LFI
adapters and global/reduced grids are outside the current phase. Producer Earth
model and independent geographic
checkpoints also remain open from P2.

P4 requires readable native encodings first (including resolution of required
-91 cases), authoritative coefficient sizes/order/truncation/normalization and
a maintained optional transform library with independent reference cases. A
shared target does not decode coefficients or qualify native 3-D atmospheric
fields, vectors, intervals or new diagnostics. No scientific approval is claimed.

Initial P3 verification record
--------------------------------

Starting revision: ``6c735efe6bbdf54a2a28ef21522313cda7e9b50d``, clean.
The separate architecture repository had unrelated deleted/untracked work;
only its two FA-roadmap Markdown files are changed for this task.

Commands in the Python-3.13.16 reference environment used prefix
``conda run -n frameit_env``:

.. code-block:: bash

   python -m pytest -q
   python -m pytest -q src/frameit/testing/numerical/test_coupled_shared_polar.py \
       src/frameit/testing/numerical/test_fa_surface.py \
       src/frameit/testing/numerical/test_fa_pipeline.py \
       src/frameit/testing/numerical/test_polar_wind.py \
       src/frameit/testing/numerical/test_polar_contracts.py
   ruff check src/frameit/core/coupled.py src/frameit/core/configuration.py \
       src/frameit/core/settings_class.py src/frameit/core/execution.py \
       src/frameit/processing/polar/polar_grid.py src/frameit/processing/polar/polar_proj.py \
       src/frameit/testing/fa_fixture.py \
       src/frameit/testing/numerical/test_coupled_shared_polar.py \
       src/frameit/testing/numerical/test_fa_surface.py
   frameit validate example/config_file/coupled_cyclone_polar.yaml --schema-only
   frameit validate example/config_file/coupled_fa.yaml --schema-only
   LC_ALL=C LANG=C sphinx-build -q -W --keep-going -b html \
       docs/source /tmp/opencode/frameit-fa-p3-docs
   git diff --check

Final full regression: **554 passed, 2 subtests passed**, 722 existing cfgrib/
xarray future warnings, 271.17 seconds. Focused suite: **66 passed**, one
NumPy/netCDF binary-size runtime warning. Ruff, both schema examples and strict
Sphinx build passed. The original standalone fixed-box-freezing test remains
unchanged; the coupled fix is explicitly scoped rather than updating that test
to accept changed standalone behavior.

The separate Python-3.13 environment without FA or xESMF ran:

.. code-block:: bash

   python -m pytest -q src/frameit/testing/numerical/test_coupled_shared_polar.py \
       src/frameit/testing/numerical/test_fa_surface.py \
       src/frameit/testing/numerical/test_fa_pipeline.py::test_coupled_netcdf_sources_do_not_need_fa_backend

Result: **12 passed, 10 skipped** (native/polar-only cases). GRIB was installed in
that environment; this is not a no-GRIB qualification. Core/native CI jobs include
the applicable new tests. Ordinary-reader checks cover sync/spawn, multiple
atmospheric groups, a third synthetic NetCDF source and the dense FA surface.

To reproduce the bounded real native-scaling check, set ``SURFEX_FA`` to the
supplied surface path and run the following in that reference environment.
It reads one full native horizontal record internally (about 50 MB decoded),
requests one output point, and leaves the missing-scaling guard enabled:

.. code-block:: python

   import os
   from frameit.io.fa_backend import inspect_fa, request_fa
   path = os.environ["SURFEX_FA"]
   info = inspect_fa(path, "surfex_history", ["SFX.T2M"])
   request_fa({
       "operation": "read", "path": path, "profile": "surfex_history",
       "fields": ["SFX.T2M"], "identity": info["identity"],
       "max_points": 6_300_000, "zone": [0, 3061, 0, 2037],
       "key": [1000, 1500], "allow_unscaled": False,
   })

Observed failure: ``SFX.T2M: missing native scaling metadata``. The accompanying
GRIB check used ecCodes ``codes_grib_new_from_file(..., headers_only=True)``;
selected interval records explicitly reported ``stepUnits=1`` (hours). This
bounded corpus investigation was separate from synthetic numerical qualification.

Scope-repair checks
--------------------

The current in-scope regression is ``test_arome_fa_coupling.py``: actual generated
atmospheric FA and SURFEX FA streams, different native spacings/indices, moving
centres, exact separate-product coordinates and independently specified constant
fields. AROME-schema NetCDF cases additionally verify planning/replay and the
source ``valid_time`` to internal ``time`` contract, including multi-file order
and explicit failure on ambiguous time names. The base NetCDF case runs without
FA or polar dependencies. These are AROME workflow checks; other-producer
integration is neither a phase requirement nor claimed from these fixtures.

Malformed SURFEX sources retain their inspectable index and available producer/
layout facts but cannot
bypass source/profile checks by losing the field directory. The production
reader still rejects unqualified packing, representation and scaling. The
native source datasets remain read-only; no new real-data scientific approval
or native codec implementation follows from the scope repair.

Scope-repair verification used the same Python-3.13 reference environment:

.. code-block:: bash

   conda run -n frameit_env python -m pytest -q
   conda run -n frameit_env ruff check \
       src/frameit/core/settings_class.py src/frameit/core/configuration.py \
       src/frameit/core/preflight.py src/frameit/core/coupled.py \
       src/frameit/io/netcdf_utils.py src/frameit/io/fa_worker.py \
       src/frameit/testing/fa_fixture.py \
       src/frameit/testing/numerical/test_arome_fa_coupling.py \
       src/frameit/testing/numerical/test_fa_surface.py
   conda run -n frameit_env frameit validate example/config_file/coupled_arome_fa_polar.yaml --schema-only
   conda run -n frameit_env frameit validate example/config_file/coupled_cyclone_polar.yaml --schema-only
   conda run -n frameit_env frameit validate example/config_file/coupled_fa.yaml --schema-only
   LC_ALL=C LANG=C conda run -n frameit_env sphinx-build -q -W --keep-going \
       -b html docs/source /tmp/opencode/frameit-fa-scope-repair-docs
   git diff --check

Full regression: **567 passed, 2 subtests passed**, 722 existing cfgrib/xarray
future warnings, 279.63 seconds. Ruff, all three schema examples and the strict
documentation build pass. The separate no-FA/no-xESMF environment ran
``test_arome_fa_coupling.py``, ``test_coupled_shared_polar.py``,
``test_fa_surface.py`` and the existing no-FA coupled-NetCDF base case:
**13 passed, 22 dependency-specific skips**. The new AROME base case executes
without either optional dependency. No source archive was modified, no new
producer adapter was added and no scientific admission gate was removed.

Dense-admission follow-up
--------------------------

Starting revision: ``82a7f79``. The existing untracked ``opencode.json`` was
preserved. Baseline regression: **567 passed, 2 subtests passed**, 722 existing
cfgrib/xarray warnings, 272.23 seconds. Four newly strengthened malformed-source
cases failed before the repair: profile inventory with no selected fields could
pass, and losing all original detector records erased the SURFEX classification.
The repaired checks cover six incomplete-source cases as well as unqualified
physical types/dimensions. Existing common-target, time-policy, native-grid,
sync/spawn and optional-dependency tests remain applicable.

The supplied corpus was rechecked read-only after compact-fixture qualification:
574 GRIB headers (600-header ceiling); atmospheric FA index plus three encoding
probes, no atmospheric physical decode; six surface encoding probes; and one
guarded SFX.T2M native decode attempt (6,300,000-point ceiling, one returned
storage point requested). The atmospheric index has 1345 records and **no SFX
namespace records**; the tightened directory check preserves its classification.
SURFPRESSION still returns -91, S001TEMPERATURE is still spectral, and SFX.T2M
still fails missing native scaling with fallback disabled. The GRIB priority
records and stress-label/interval conflict are unchanged. All three source
sizes/mtime_ns match the P0/P3 manifest. No real values were accepted, geometry
reference supplied or scientific capability promoted. The finite field-priority
table and recheck facts are retained in ``testing/catalogs/fa_p3.yaml``.

To repeat the added atmospheric index/encoding check, with ``ATMOSPHERE_FA`` set
to the supplied source, use the isolated backend (no physical array read):

.. code-block:: python

   import os
   from frameit.io.fa_backend import inspect_fa
   info = inspect_fa(os.environ["ATMOSPHERE_FA"], None,
                     ["CLSTEMPERATURE", "SURFPRESSION", "S001TEMPERATURE"],
                     validate_selection=False)
   print(info["record_count"], info["fields"])
   print([name for name in info["records"] if name.startswith("SFX.")])

The surface guarded-decode reproduction above and P0 upstream probe remain
applicable. Coordinate identity only qualifies the shared sampling target;
independently supplied geometry/scaling/field definitions are still required.

Follow-up verification used Python 3.13.16. Native commands used the local conda
launcher for ``frameit_env``; the existing separate no-FA/no-xESMF environment
provided the optionality check and Ruff:

.. code-block:: bash

   conda run -n frameit_env python -m pytest -q
   conda run -n frameit_env python -m pytest -q \
       src/frameit/testing/numerical/test_fa_contracts.py \
       src/frameit/testing/numerical/test_fa_surface.py \
       src/frameit/testing/numerical/test_arome_fa_coupling.py \
       src/frameit/testing/numerical/test_coupled_shared_polar.py \
       src/frameit/testing/numerical/test_fa_pipeline.py
   /tmp/opencode/frameit-hpc-venv/bin/python -m pytest -q \
       src/frameit/testing/numerical/test_fa_contracts.py \
       src/frameit/testing/numerical/test_fa_baseline.py \
       src/frameit/testing/numerical/test_arome_fa_coupling.py \
       src/frameit/testing/numerical/test_coupled_shared_polar.py \
       src/frameit/testing/numerical/test_fa_surface.py \
       src/frameit/testing/numerical/test_fa_pipeline.py::test_coupled_netcdf_sources_do_not_need_fa_backend
   /tmp/opencode/frameit-hpc-venv/bin/ruff check \
       src/frameit/io/fa_worker.py src/frameit/io/fa_contracts.py \
       src/frameit/testing/fa_fixture.py \
       src/frameit/testing/numerical/test_fa_surface.py \
       src/frameit/testing/numerical/test_fa_contracts.py \
       src/frameit/testing/numerical/test_arome_fa_coupling.py
   conda run -n frameit_env frameit validate example/config_file/coupled_arome_fa_polar.yaml --schema-only
   conda run -n frameit_env frameit validate example/config_file/coupled_cyclone_polar.yaml --schema-only
   conda run -n frameit_env frameit validate example/config_file/coupled_fa.yaml --schema-only
   LC_ALL=C LANG=C conda run -n frameit_env sphinx-build -q -W --keep-going \
       -b html docs/source /tmp/opencode/frameit-p3-dense-followup-docs
   git diff --check

Results: **585 passed, 2 subtests passed**, 722 existing cfgrib/xarray warnings,
285.49 seconds; focused suite **67 passed**, 50.74 seconds; optionality suite
**28 passed, 37 dependency-only skips**, 2.56 seconds. GRIB was installed in the
optionality environment; this is not a no-GRIB qualification. Ruff, all three
schema examples and strict Sphinx checks passed. Dense data ordering and codes
are checked exactly; shared target coordinates are checked exactly, while polar
scalar values use the existing absolute ``1e-9`` interpolation tolerance.
Neither agreement criterion is independent scientific validation of real fields.
