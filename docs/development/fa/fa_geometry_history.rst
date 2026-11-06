.. note::

   Frozen developer evidence from 9b11d602c4fb05fb2adf74b699439de6a0b8625b.
   Commands, support statements and results below describe historical checkpoints.
   See the `developer index <README.md>`_ for current topics and the removal plan.

FA P2 regional geometry repair and remaining gates
===================================================

This bounded repair starts from clean revision
``abce667bb5e791f39baa657968c415a69edbb47d``. It implements P2's native-grid
association on the evidenced modern regional AROME/SURFEX branch. Additional
AROME/SURFEX headers need separate admission evidence; global/reduced grids and
other producers are outside this phase. This is not full FA compatibility.
The `fa_baseline <fa_baseline_history.rst>`_ in-scope missing-corpus requests remain applicable.
This is the historical P2 repair record. The maintained EPyGrAM path now uses
the library-derived geometry/CRS/zones in `fa_epygram_c2 <fa_epygram_c2.rst>`_, with the same
source-axis lookup and CF origin. EPyGrAM independence is superseded.
The manual production reconstruction is retired in `fa_epygram_c4 <fa_epygram_c4.rst>`_;
independent equations, original-header admission checks and snapping guards remain.

Repair and numerical compatibility
------------------------------------

Previously FA Lambert centres were selected using squared differences in
latitude/longitude degrees even though the source has explicit projected metre
axes. An independently constructed southern Lambert example reproduces a
different cell: requested projected position ``(-4499.99, -2100) m`` selects
``(j=1, i=0)`` under the old degree metric and ``(1,1)`` under native-axis distance.
The latter is the defined P2 native sampling convention, not a claim to minimize
ground/geodesic distance.

The admitted FA geometry now declares ``fa_source_crs_native_axes_v1``.
Fixed-box, prescribed-track and coupled secondary-source association transform
the requested geographic point into **that source's** spherical Lambert CRS,
then choose the nearest point independently on its labelled metre axes. No field
interpolation, vector rotation, pressure/height diagnosis or regridding occurs.
Non-FA inputs and regular lon/lat FA keep their original squared-degree choices;
an ordinary CF CRS on another format does not silently change that behavior.

This is an intentional numerical correction: projected FA crop centres can
change near cell boundaries. There is no YAML migration or new projection
selector. Requested ``lat``/``lon`` remain continuous and continue to define the
polar target/track kinematics; they are not replaced by snapped coordinates.
Production continuous polar interpolation stays bilinear with no conservation
claim. No experimental method is activated.

Native association and boundaries
-----------------------------------

Each admitted projected source must have explicit spherical Lambert CF metadata,
static labelled latitude/longitude in degrees, and finite monotone regular X/Y
axes in metres. Ascending and descending storage are supported by lookup. Before
mapping centres, **every** geographic point is projected and checked against its
labelled axes in blocks of at most 32 rows. This detects mismatched axes, CRS,
units and interior geography, rather than proving identity from a few corners
or an equal shape. Only geographic coordinate arrays are touched; scientific
payloads remain lazy. The full proof has real coordinate-I/O/transform cost and
has not been performance-qualified on the private archive.

The internal double-precision CRS association tolerance is ``1e-5 m``. Axis
regularity, boundary roundoff and ties use the greater of that tolerance and
``64 * machine_epsilon * coordinate_magnitude``. Exact/roundoff ties choose the
first **storage index**, including descending axes. These numerical tolerances
are not physical coverage extensions, CRS fitting or relaxed native-header
checks. Source/header precision remains a separate limitation.

Coupled required sources reject centres outside the native point-axis envelope
(apart from numerical roundoff); no edge substitution or time skip occurs.
Existing single-source edge-nearest selection is preserved and its offset is
recorded. Boxes extending outside the domain retain existing missing-value
padding. CI and C offsets stay attached to native ``source_i``/``source_j``.
Every source is located independently: no exact indices are shared between
sources, so equal array shapes never imply a shared sample grid.

Separate X/Y distances are used for this lookup, not a new anisotropic extraction
algorithm. Existing core guards still reject more than 10 percent X/Y spacing
difference or 20 percent within-axis variation, even with a spacing override.

Active header contract
------------------------

The horizontal cache/signature uses the admitted rectangular dimensions,
transform discriminator and active ``KNLOPA[:8]`` / ``PSINLA[:16]`` entries plus
the chosen zone/radius. Inactive native work-buffer tails, header lifetime state,
inherited vertical coordinates and independent ``KTRONC`` coefficient metadata do
not define these 2-D sample positions. This signature is **not** a vertical, quantity,
spectral-coefficient or content-identity contract.

Unknown header discriminators, nonintegral/negative zone widths, rotated,
stretched or academic conventions are rejected instead of truncating values or
silently treating them as modern regional geometry. Complete regular-lon/lat CI
bounds and nonzero angular increments are required. Regular and Lambert encoded
corner contradictions fail; the existing ``2e-5 degree`` native-angle tolerance
is preserved. It reflects rounded modern header angles, not an independently
verified producer Earth model. A supplied radius is never fitted to the corners.

Provenance and ordinary track outputs
---------------------------------------

FA preflight/load inventories now record ``horizontal_header_signature`` and
``grid_lookup`` per file. ``grid_geometry.index_lookup`` records the source
lookup choice. Single-source track summaries retain ``tracking_grid_lookup``,
``tracking_snap_convention`` and ``tracking_grid_ties`` in run provenance.

Projected FA tracks add:

* ``grid_selected_latitude`` / ``grid_selected_longitude``: actual selected source point;
* ``grid_snap_dx_m`` / ``grid_snap_dy_m``: selected minus requested projected X/Y;
* ``grid_snap_distance_m``: Euclidean norm of those projected offsets, not ground distance.

Coupled tracks prefix these with the source ID, e.g. ``surfex_grid_snap_dx_m``.
Per-source provenance ``grid_lookup`` identifies the method/convention and track
variables recording requested/selected locations and offsets. Base ``cx``/``cy``
still belong to the tracking source; source-prefixed indices remain independent.
Reference-source snapping variables/attributes are removed before mapping a
different legacy source, so it cannot inherit another grid's observations.
The lookup tag describes the **input source**, not a promise that exported local
box coordinates can themselves be reinterpreted as source-projection axes.
Product names, field dimensions/values at selected indices, masks, precision,
compression and atomic publication mechanisms are otherwise unchanged. Outputs
are checked with ordinary xarray/NetCDF readers without importing FrameIt.

Qualification and blockers
----------------------------

.. list-table:: P2 operation/family status
   :header-rows: 1

   * - Family/operation
     - Evidence and status
   * - Modern spherical tangent Lambert CI/C geometry and native-axis lookup
     - Independently specified Snyder equations in both hemispheres, asymmetric
       and offset zones, descending storage, equivalent longitudes, ties,
       coverage and different-grid cases. Compact southern native FA extraction
       and coupled NetCDF/FA export/reopening pass; no real-producer sign-off.
   * - Modern regular lon/lat CI
     - Existing native fixtures retained; independent descending-axis geometry
       and corner-contradiction checks added. Lookup remains legacy degrees.
   * - Other/older regional headers, secant Lambert, Mercator, polar stereographic,
       rotated geography, ellipsoidal Earth models
     - Blocked: no demonstrated native examples with authoritative versioned
       header mappings, Earth models, anchor/scan/zone conventions and independent
       checkpoints. Request those exact inputs before admitting each variant.
   * - Global/reduced active geometry metadata
     - Outside this regional AROME/SURFEX phase. A future broader reader requires
       a native reference corpus and verified active-buffer extents. The worker still
       retains only the qualified regional prefixes, not full active Gaussian/
       spectral arrays. Request authoritative active counts/layouts and trusted
       reference headers first; no rectangular reshape or processing is admitted.
       Regional spectral transforms remain the separately gated P4 capability.
   * - Real private corpus geometry
     - P0/P1 metadata facts only. Producer Earth model and independent geographic
       checkpoints remain missing; no large qualification run was performed.

Method basis remains the spherical tangent-Lambert equations and USGS/Snyder
reference in `fa-geometry-method <fa_inputs_history.rst#fa-geometry-method>`_. Tests use independently evaluated equations
with ``2e-11 degree`` agreement tolerances; a pyproj round trip alone is not the
scientific oracle. Internal sample/axis consistency checking does not constitute
independent confirmation of a real producer's CRS or scientific field meaning.
P2 retained Python 3.13 and the native FA/GRIB isolation boundary. The former
EPyGrAM-independence requirement is superseded by C2's maintained library path;
core-only geometry tests still require no native optional dependency.

P3 prerequisites remain actual producer/container examples, native type/packing/
support-map specifications, known ordering and missing-value conventions, layer/
patch/tile definitions and trusted decoded values/masks. P0's -91 and P1's physical
definition/scaling gaps stay blocked. Geometry success cannot qualify those
layouts, and no scientific approval is invented.

Verification record
---------------------

The reference environment uses Python 3.13.16 and the unchanged published
``falfilfa4py==1.3.0`` wheel. Commands below used the prefix
``conda run -n frameit_env`` (resolved to the installed local conda launcher):

.. code-block:: bash

   python -m pytest -q
   python -m pytest -q src/frameit/testing/numerical/test_fa_mapping.py \
       src/frameit/testing/numerical/test_fa_geometry.py \
       src/frameit/testing/numerical/test_fa_pipeline.py
   ruff check src/frameit/io/fa_geometry.py src/frameit/io/fa_utils.py \
       src/frameit/tracking/geographic.py src/frameit/tracking/FixedBox_Tracker.py \
       src/frameit/tracking/PrescribedTrack_Tracker.py src/frameit/core/coupled.py \
       src/frameit/core/grid_geometry.py src/frameit/core/preflight.py \
       src/frameit/testing/fa_fixture.py src/frameit/testing/numerical/test_fa_mapping.py
   frameit validate example/config_file/coupled_fa.yaml --schema-only
   LC_ALL=C LANG=C sphinx-build -q -W --keep-going -b html \
       docs/source /tmp/opencode/frameit-fa-p2-docs
   git diff --check

Final full regression: **533 passed, 2 subtests passed**, 722 existing cfgrib/
xarray future warnings, 244.79 seconds. Final focused suite: **30 passed**, one
NumPy/netCDF binary-size runtime warning. Ruff and schema validation passed;
the strict documentation build passed. The initial reverse-source regression
fixture lacked its legacy time-dimension setting; that fixture was corrected
before the final passing runs. No numerical expectation was relaxed.

A separate Python-3.13 environment without falfilfa4py ran:

.. code-block:: bash

   python -m pytest -q src/frameit/testing/numerical/test_fa_mapping.py \
       src/frameit/testing/numerical/test_fa_contracts.py \
       src/frameit/testing/numerical/test_fa_baseline.py \
       src/frameit/testing/numerical/test_fa_pipeline.py::test_coupled_netcdf_sources_do_not_need_fa_backend

Result: **27 passed, 4 skipped**, only the native-fixture cases skipped. GRIB was
installed there; this is not described as a no-GRIB environment qualification.
Both core and FA CI jobs now include ``test_fa_mapping.py``. No private sample was
decoded, uploaded or converted, no large run/download was performed, and no
production throughput or bitwise reproducibility claim follows from these checks.
