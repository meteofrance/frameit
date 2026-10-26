P3 coupled cyclone inputs and shared polar products
====================================================

The immediate contract is **separate atmosphere and surface products on the same
explicit polar target**. Existing native Cartesian products and vertical-group
file separation remain. This bounded P3 repair uses admitted dense SURFEX
histories; missing packed/layered/native-container references remain gates, not
permission to guess their meaning. See :doc:`fa_baseline`, :doc:`fa_contracts`
and :doc:`fa_geometry` for the earlier evidence and limitations.

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
vertical coordinates and units remain independent. Tight sampling budgets still
apply during source preflight; declare an explicit coarse step for large plans
rather than expecting the common-target option to bypass resource checks.

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
conventions. Current model validation remains AROME/Meso-NH; do not relabel a
marine NetCDF file as one of these models just to open it.

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

The support label is retained separately from actual finite/missing samples.
There is no guessed sparse support map or conversion of absent surface types to
zero. Native record identities survive as individual 2-D variables, not invented
soil-depth, tile or atmospheric-level axes. Other producers, ``PACK!=0`` and
unqualified X2/typed physical layouts remain actionable failures, while their
directories can still be inspected. Plain LFI and Meso-NH-produced FA are not
admitted by removing existing profile checks.

The schema-only starting example is
``example/config_file/coupled_cyclone_polar.yaml``. Its SFX unit/time and radius
entries are explicit declarations requiring confirmation, not new producer
defaults. It intentionally leaves ``allow_unscaled`` false and therefore does
not conceal the supplied native-scaling blocker. Replace paths/centre and review
the declarations before scientific use. Pure NetCDF or other independently
qualified fields can exercise the common-target contract without FA.

Remaining phase gates
-----------------------

Packed layouts need actual release-specific support maps/order/coverage and
trusted scatter/gather values. Full layered/tiled axes need producer indices,
bounds, fractions and masking conventions. Actual Meso-NH native inputs need
container evidence and companions. Those P3 rows remain blocked, not silently
qualified by the dense branch. Producer Earth model and independent geographic
checkpoints also remain open from P2.

P4 requires readable native encodings first (including resolution of required
-91 cases), authoritative coefficient sizes/order/truncation/normalization and
a maintained optional transform library with independent reference cases. A
shared target does not decode coefficients or qualify native 3-D atmospheric
fields, vectors, intervals or new diagnostics. No scientific approval is claimed.

Verification record
---------------------

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
