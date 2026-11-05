# v2 public-interface RC readiness

This development record is not published documentation or an RC qualification
certificate. Status below describes the inspected checkout on 2026-11-05;
historical results are explicitly separated from checks run during this plan.
Execution logs and qualification payloads belong under ignored `build/rc/`.

## Baseline and integration

- Delivery branch: `dev_md`; initial revision
  `212fccab2ac16a10fe289be600eee2c0cd6d65b9`.
- Tracked files and index were clean at entry. Unrelated untracked
  `opencode.json` is preserved and is not part of this work.
- `ocean-netcdf-coupling` at `4878ba7459278338d82db2cdf42f445624b66549`
  is already integrated by `0f9852031f508fafa9a0cb54fa8fba92891dd8a8`.
  Its worktree was clean and there were no incoming commits at inspection.
  Do not repeat the merge or overwrite the adapter owner's worktree. Task 2 must
  verify the integrated contracts and record the integration-readiness evidence;
  the existing merge is not scientific sign-off.
- Subsequent NetCDF-read and runtime optimizations are retained. Their historical
  evidence is in `../input-reading.md` and `../runtime-optimization.md`, not a
  claim that this plan reran or qualified those workloads.
- Current package metadata is **1.1.0**, `requires-python = ">=3.10"`; current
  YAML/templates use schema 2 and still expose migration and `init --full`.
  The target `2.0.0rc1`, Python 3.13-only support and exact string YAML `"2.1"`
  are not implemented or qualified by establishing this baseline.

## Inspected capability / maturity inventory

This is a starting inventory, not the Task 2 support/evidence matrix. No method
is promoted to scientifically validated status here.

| Area | Present implementation/documentation | Remaining admission or qualification work |
| --- | --- | --- |
| Atmospheric extraction | AROME GRIB/NetCDF and Meso-NH NetCDF; fixed/prescribed and selected atmospheric trackers | Map exact grids, selected quantities, metadata, fixtures and independent verification. |
| Native FA | Explicitly declared instantaneous gridpoint records and associated atmospheric cubes | Retain producer/scaling/Earth-model evidence requirements; no spectral or packed-SURFEX admission. |
| NEMO | Regional native scalar and separate component copies; exact native levels and time bounds | No inferred current/stress rotation, physical-depth diagnosis or mean/snapshot equivalence. |
| NEMO/AROME association | Explicit `preceding_hour` profile for declared one-hour means paired with instantaneous AROME records | Not the global default, not interpolation; inspect participants, bounds, exclusions and provenance. |
| CROCO | Regional history/Vtransform=2 native scalars/faces and explicitly selected rho/Earth currents | Preserve sigma dependencies and separate native/analysed contracts; not arbitrary CROCO products or NEMO time policy. |
| Embedded SURFEX | Opt-in supported sea-field interpretation in Meso-NH NetCDF | Preserve field-specific sentinel/support/unit evidence; do not infer flux sign, basis or averaging configuration. |
| Polar sampling | Optional bilinear point sampling and explicit shared targets | No area-conservation claim; conservative/patch/additional transport methods remain experimental. |
| Tracking/diagnostics | Documented pressure-wind/centroid paths; experimental multi-field tracker; optional UTrack | Inventory method evidence, dependencies, applicability and outstanding human review. |
| Export | NetCDF and optional sharded Zarr v3; per-product atomic publication and run-root locking | Independently reopen both formats and test failure/overwrite/concurrency contracts within the admitted scope. |

## Reference environment observed

The Python guard ran successfully in Conda `frameit_env`: **Python 3.13.18**,
conda-forge, GCC 15.3.0. No environment was created, upgraded or substituted.

- Host platform observed: Bazzite 44.20261026.0 (Fedora-derived Kinoite), Linux
  x86_64, local Btrfs checkout with SSD mount options. This is not qualification
  of every Linux distribution, shared filesystem, cluster, macOS or Windows.
- Installed metadata: NumPy 2.5.4, SciPy 1.18.1, xarray 2026.9.0, Dask 2026.8.0,
  PyYAML 6.0.3, pyproj 3.8.0, netCDF4 1.7.2, h5netcdf 1.8.2, h5py 3.16.0,
  Zarr 3.4.2.
- Observed native versions: PROJ 9.9.0, netCDF C 4.9.3, HDF5 1.14.6 (both
  h5py and netCDF4). Optional-package metadata: cfgrib 0.9.15.1, ecCodes Python
  2.44.0, EPyGrAM 2.1.0, falfilfa4py 1.2.1, ctypesForFortran 1.3.0,
  ectrans4py 1.6.0, xESMF 0.9.2, ESMPy 8.9.1. Package presence alone is not a
  successful native reader or processing check. The recorded GRIB native-library
  initialization limitation remains in `../runtime-optimization.md`.
- Actual docs tooling: Sphinx 9.2.0, sphinx-rtd-theme 3.1.0. The docs requirements
  pin Sphinx 8.1.3 and docs CI currently selects Python 3.12; runtime CI still
  includes Python 3.10. Align these in the planned support/CI tasks, not by
  silently reinstalling tooling for this baseline.

## Fixtures and authorization boundary

- Compact synthetic fixtures generated by the numerical tests are the initial
  bounded engineering inputs. They are not real-producer or all-regime evidence.
- The packaged CI-data directories contain five AROME GRIB files (17,370,964
  bytes total) and four Meso-NH NetCDF files (44,016,083 bytes total). This is a
  presence/size inventory only: neither content identity nor manifest completeness
  has been verified in Task 1. The manifest lists five AROME and three Meso-NH
  inputs; the additional Meso-NH file is not thereby qualified.
- Do not acquire private archives, use historical large-file benchmarks as new
  authorization, launch production/HPC work, upload data or modify source inputs.
  Any required real-fixture identity, availability and permission must be recorded
  before its qualification run. No such run is claimed here.

## Gates and blockers

- Task 2: integrated adapter review/tests, support matrix and bounded baseline
  measurement outstanding; establish owner-confirmed integration readiness.
- **G1 pending:** complete key/value/default map, precedence, generator interface,
  concrete commented catalogue, page/figure map and behavioral exceptions need
  actual maintainer approval before Task 4.
- **G2 pending:** first-run/deeper-guide pilots and supplied artwork/art direction
  need actual live-preview editorial approval before the wider rewrite.
- Required scientific/human review, unfamiliar-reader acceptance, wheel/sdist and
  fresh-environment checks, operational safety, authorized real-fixture checks,
  hosted CI and final candidate freeze are not complete.
- No push, merge into `main`, tag, package publication or documentation deployment
  is authorized by this record.

## Task 1 verification receipt

- `conda run --no-capture-output -n frameit_env python -c 'import sys; assert sys.version_info[:2] == (3, 13); print(sys.version)'`
  → Python 3.13.18, exit 0.
- `conda run --no-capture-output -n frameit_env python -m unittest discover -s docs -p test_check_publication.py`
  → 2 tests passed.
- Fresh strict preflight build into `build/docs-preview/preflight-01` → exit 1:
  short title underline in `tracker/pressure_centroid.rst:12` and missing blank
  line after a figure caption in `tracker/pressure_wind_tracker.rst:142`.
  Both were corrected without warning suppression or scientific changes.
- `baseline-01` caught a short underline in the new contribution guide; it was
  corrected, and that failed iteration is not presented as a passing preview.
- `conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/baseline-02`
  → exit 0, no warnings.
- `conda run --no-capture-output -n frameit_env python docs/check_publication.py build/docs-preview/baseline-02`
  → public documentation boundary passed, exit 0.
- The OpenCode GUI browser loaded the index, contribution guide and both affected
  tracker pages. Rendered content/DOM layout was inspected at 1000 CSS px and in
  a same-origin 390 CSS px iframe (not device emulation). Navigation switched to
  its narrow layout; the tracker illustration loaded; corrected sections are
  recognized as headings. The new guide and index had no page-wide horizontal
  overflow; long commands scroll within their code blocks. The existing centroid
  page reached 401 px scroll width in the narrow viewport: retain this layout
  issue for the planned guide/style work, not a scientific-content change here.
- Screenshot capture was unavailable because the desktop window was not visible,
  despite focusing the connected browser tab. DOM/layout inspection is not visual
  editorial approval; G2 remains pending. The live server is left available, with
  its actual process/URL/restart details in the session handover only.
- Per-commit impact: new contributor guidance/navigation and two markup fixes;
  runtime commands, schema, scientific methods/defaults and outputs unchanged.
  Applicable checks are the strict build, publication check/unit tests, rendered
  inspection and `git diff --check`; no unrelated numerical benchmark is required
  for this documentation-only task.
