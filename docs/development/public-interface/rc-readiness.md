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
- On 2026-11-05 the maintainer confirmed the working baseline by directing this
  execution to the current `dev_md`: everything had been merged cleanly the
  previous day. No additional merge or adapter-owner worktree edit is needed.
  Verification includes the later CROCO vector/shared-target tests as well as
  the five suites named in Task 2.
- Subsequent NetCDF-read and runtime optimizations are retained. Their historical
  evidence is in `../input-reading.md` and `../runtime-optimization.md`, not a
  claim that this plan reran or qualified those workloads.
- At the inspected baseline, package metadata was **1.1.0** with
  `requires-python = ">=3.10"`; YAML/templates used schema 2 and exposed migration
  and `init --full`.
  The target `2.0.0rc1`, Python 3.13-only support and exact string YAML `"2.1"`
  are not implemented or qualified by establishing this baseline.

## Integrated support / evidence matrix

Read this together with `docs/source/user_guide/ocean_netcdf.rst` and the native
FA guides for the full contracts. "Present" means implementation inspected, not
new scientific approval. Tests named below live in
`src/frameit/testing/numerical/`; the Task 2 run status is recorded separately.
No untested Cartesian product of these capabilities is implied.

| Input family / admitted quantities and grids | Centre/reference and time policy | Optional sampling / output | Evidence and maturity; exclusions |
| --- | --- | --- | --- |
| AROME GRIB/NetCDF: selected atmospheric scalars and declared vector pairs; admitted regular/regional geometry | Fixed/prescribed; atmospheric trackers subject to their input/method requirements. Named sources use exact `common` (default) or `strict` and compatible forecast cycles | Optional selected polar fields; NetCDF or optional Zarr v3 | Present. Task 2 synthetic NetCDF variable-shard checks in `test_netcdf_assembly.py`; real GRIB and tracker qualification not rerun by that evidence. No inference of arbitrary statistical intervals or wind basis. |
| Meso-NH NetCDF: surface/native-level scalars and explicitly represented staggered winds/W | Fixed/prescribed; selected atmospheric tracker with required fields; exact coupled time labels | Optional polar; NetCDF/Zarr | Present; `test_netcdf_assembly.py` reuse/native-branch tests. Broader native-level/tracker methods need their own later qualification. No inferred physical-height equivalence from stored labels. |
| AROME/SURFEX native FA streams: declared instantaneous gridpoint fields, admitted atmospheric full/interface cubes | FA references admit fixed/prescribed centres only; a separate atmospheric GRIB/NetCDF reference can supply tracking. SURFEX is a named source/FA profile, not a new model selector. Exact times and compatible forecast identity | Selected polar/shared targets subject to geometry/support; NetCDF/Zarr | Present with bounded engineering evidence in existing `test_fa_*.py`/`test_arome_fa_coupling.py`, not rerun in Task 2. Scaling, support, units and Earth model need explicit evidence. No spectral FA, packed SURFEX or implicit pressure/height diagnostic. |
| NEMO regional native T-grid scalars and separate U/V/W, barotropic and stress components: `(y,x)` geography; `deptht/u/v/w` retained | Fixed/prescribed ocean reference; or secondary source mapped independently to continuous atmospheric centres. Exact `common`/`strict` sample labels and native bounds | Scalar polar only if selected and eligible; NetCDF/Zarr; native component copies require the current `horizontal_winds: native` selector | Present, bounded synthetic oracles in `test_nemo_netcdf.py` and `test_nemo_arome_coupling.py`. No inferred mesh/mask/angle, component rotation/collocation, current speed, W mass conversion or component polar analysis. Regional spacing limits remain; not arbitrary global/folded grids. |
| Explicit AROME/NEMO preceding-hour association: instantaneous AROME fields and unique NEMO one-hour means with decoded bounds | Named NetCDF only; AROME reference, at least one NEMO participant, no other model. Pair `(T-1h,T]` by bounds; omit missing whole pairings with warning/record; never nearest matching | Native components and selected scalar polar under their own contracts; NetCDF/Zarr. Product `time` labels reference/end; `source_time` retains native mean label and bounds | Present explicit comparison policy, `test_nemo_arome_coupling.py`. Not the global default, interpolation, reconstruction of snapshots or mean/snapshot equivalence. Invalid/ambiguous required metadata fails. |
| CROCO regional declared history/Vtransform=2 rho scalars, N-1 native faces, `s_rho/s_w` and formula dependencies | Fixed/prescribed, alone or as secondary source; only exact `common`/`strict`. Do not apply the NEMO preceding-hour policy | Native NetCDF/Zarr; eligible scalar polar requires explicit static water support | Present, `test_croco_netcdf.py`, `test_croco_vectors.py`, `test_croco_mnh_coupling.py`. Native missing cells and zeros retained; copies do not interpret finite land placeholders. No arbitrary restart/averaged family, other Vtransform or diagnosed depth cube. |
| Explicit CROCO rho/Earth `u/v` and `ubar/vbar` analysis: midpoint collocation then declared angle rotation, same native sigma index | Same centres/exact times as CROCO above; explicit representation selection or selected polar current path loads required companion | NetCDF/Zarr; selected current polar points after preparation. Static binary rho support, optional restricting face masks, both valid brackets and joint finite vector mask | Bounded transformation, analytical constant/linear/rotated/reversed-axis oracles at 1e-12 in `test_croco_vectors.py`; no new stable diagnostic claim. No stress analysis, wet/dry, single-bracket fill, physical-depth interpolation, conservation or storm-motion subtraction. |
| Embedded SURFEX sea interpretation in Meso-NH NetCDF time series: explicit finite SEA field list plus `FRAC_SEA` support | Meso-NH source remains independent of ocean; fixed/prescribed or atmospheric reference when its required inputs exist. Exact coupled clocks | Native/scalar polar selected explicitly; NetCDF/Zarr | Opt-in producer-specific interpretation; `test_mnh_surfex_support.py` and `test_croco_mnh_coupling.py`. Exact source-999 invalidation only for interpreted fields; positive finite physical sea fraction, no fraction weighting. Unit comments complete labels only; no guessed sign/basis/timing or universal sentinel rule. |

Shared polar targets require explicit selection, compatible target geometry and
resource budgets. Identical target coordinates do not equate source masks,
depths, intervals or physical definitions. Continuous bilinear point sampling is
not conservative area/transport remapping; experimental alternatives are not
promoted by this baseline. Optional dependencies are forbidden by import guards
in the base-copy tests, and installed optional paths must actually execute rather
than be counted as covered through skips.

The inspected ocean tests retain independent source-window comparisons,
valid-zero versus missing checks, native axis/bounds/formula metadata, replay,
NetCDF/Zarr ordinary-reader subprocesses without FrameIt, synchronous/spawned
export and selected failure/overwrite behavior. This establishes bounded
engineering/numerical scope, not all production regimes or human acceptance.

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
- Baseline docs tooling: Sphinx 9.2.0, sphinx-rtd-theme 3.1.0. At baseline, docs
  requirements pinned Sphinx 8.1.3, docs CI selected Python 3.12 and runtime CI
  included Python 3.10. Align these in the planned support/CI tasks, not by
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

- Task 2: current `dev_md` selected by the maintainer, integrated contracts
  inspected, seven adapter suites passing and bounded baseline recorded below.
  Full RC qualification and human scientific review remain outstanding.
- **G1 approved on 2026-11-05:** the maintainer replied **"Approved"** to the
  complete [v2_1-design.md](v2_1-design.md) proposal at `ab0be01`. The strict loader
  is verified below; the catalogue, first run and editorial pilots remain
  outstanding. G1 is not scientific
  sign-off, G2 or publication/deployment authorization.
- **G2 pending:** first-run/deeper-guide pilots and supplied artwork/art direction
  need actual live-preview editorial approval before the wider rewrite.
- Required scientific/human review, unfamiliar-reader acceptance, wheel/sdist and
  fresh-environment checks, operational safety, authorized real-fixture checks,
  hosted CI and final candidate freeze are not complete.
- No push, merge into `main`, tag, package publication or documentation deployment
  is authorized by this record.

## Task 4 strict-interface verification

The public resolver and every YAML/mapping/preset route now require exact string
`"2.1"`. Old keys/values, flat dispatch and the public converter are removed.
The approved names translate to unchanged numerical tracker/vector settings;
current effective records reload, source-local input records omit global controls,
and inherited polar declarations retain YAML origins. Unresolved automatic spacing
stays null, not physical zero. Independent scientific-data, manifest, status and
FA worker/descriptor contracts were not renamed. The catalogue generator's full
mode remains for Task 5, not a completed minimal-template implementation.

Support metadata now requires Python `>=3.13,<3.14`; both environment recipes and
all runtime/docs CI interpreter selections agree. Reference and CI documentation
tools share `docs/docs-requirements.txt` (Sphinx 9.2.0). No runtime dependency or
environment upgrade was added; `python -m pip check` passed in `frameit_env`.
Hosted CI and installation from newly built artifacts were not run.

Checks in `frameit_env` (Python 3.13.18):

- `python -m pytest -q` → **1132 passed, 4588 warnings, 2 subtests passed,
  no skips, 505.01 s**. The earlier red run had 12 retired-fixture failures;
  they were migrated without removing independent values/masks/zero/basis/time/
  read-only and ordinary-reader assertions. The warnings are the known ndarray
  native-ABI, netCDF/NumPy shape and cfgrib combination warnings, not suppressed.
- Focused current-schema/NEMO/FA admission/surface run → **213 passed**.
  Added boundary tests were observed failing before fixes, including all public
  loader version guards, rejected aliases, source replay and automatic spacing.
- All **15** shipped YAML examples passed `frameit validate <path> --schema-only`;
  no old run-schema documents remain in active examples or templates. Low-level
  scientific structures and historical development evidence remain distinct.
- Strict `sphinx-build -q -W --keep-going -b html docs/source
  build/docs-preview/v2_1-05` and the publication check exited 0; publication unit
  tests passed (2). Direct reference, error, upgrade, installation and example
  documentation was refreshed, not the wider editorial rewrite reserved for G2.
- Affected pages were opened in the live GUI, with desktop/narrow rendered DOM
  checks and no broken images. The new upgrade table fits the 390 px iframe after
  scoped wrapping. Existing narrow-layout issues on some technical pages remain
  for planned presentation work. Screenshot capture still needs a visible desktop
  window; no visual/human approval is claimed. `git diff --check` and targeted
  Ruff F checks passed.

Scientific impact: no new calculation, diagnostic, unit interpretation or output
schema; these are public syntax/admission and runtime-support changes. Retired run
YAML must be manually reviewed using the published upgrade map. Passing this suite
is bounded regression evidence, not scientific sign-off or RC qualification.

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

## Task 2 verification and bounded measurement

Revision tested: `7027aa88630db7c957ba8dad6b79ed800c7a1f40`, with scientific
implementation unchanged from the initial `212fcca` baseline. Both branches'
instructions were reviewed; the only instruction difference was Task 1's new
documentation obligation. Credits, FA/Zarr work and subsequent optimizations
were retained. No new integration defect was reproduced or numerical code
changed in this task.

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_netcdf_assembly.py \
  src/frameit/testing/numerical/test_nemo_netcdf.py \
  src/frameit/testing/numerical/test_croco_netcdf.py \
  src/frameit/testing/numerical/test_mnh_surfex_support.py \
  src/frameit/testing/numerical/test_nemo_arome_coupling.py \
  src/frameit/testing/numerical/test_croco_vectors.py \
  src/frameit/testing/numerical/test_croco_mnh_coupling.py
```

Result: **214 passed, no skips, 2,522 warnings, 84.53 s**. The warnings include
the NumPy ndarray-size/native-ABI warning at netCDF import and xarray/netCDF4's
NumPy 2.5 shape-setting deprecation; they are recorded, not suppressed or
represented as warning-free native-stack qualification. Full output is under
ignored `build/rc/baseline-01/adapter-tests.log`. Only these suites, not the full
numerical/FA/GRIB suite, were run for Task 2.

### Reproducible compact baseline

Use the existing independently checked test, not a new benchmark framework:

```bash
conda run --no-capture-output -n frameit_env env \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /usr/bin/time -v -o build/rc/baseline-01/timing-01.time \
  python -m pytest -q \
  'src/frameit/testing/numerical/test_nemo_arome_coupling.py::test_nemo_arome_exact_track_maps_each_grid_independently[True-False]' \
  --basetemp build/rc/baseline-01/timing-01
```

The pytest ID was verified by `--collect-only`: synchronous export, fixed centre.
Choose a **nonexistent owned** `--basetemp` for each run (pytest replaces an
existing one); measurements used suffixes `01`, `02`, `03`. The three fresh
Python processes ran sequentially after the adapter suite, with warm filesystem
cache and no cache flushing. No production/private input was read. The plan's
bounded synthetic-fixture policy covers this workload; no expensive run, large
download or new data authorization was inferred.

Workload: two exact sample labels, three 9×9 AROME surface-variable shards plus
four independent 7×7 NEMO T/U/V/W sources, two native depths per ocean source;
fixed centre (-20°, 60°), 2×2 km full-width box. Selected atmospheric pressure/U/V
retain their existing speed companion; selected ocean scalars/components remain
native. No polar processing is enabled. One Dask worker, one native thread and
one synchronous export worker; h5netcdf input, ordinary NETCDF4 output through
netCDF4 with existing level-1 compression. Environment/platform are above.

| Run | Total wall time | GNU time maximum RSS (KiB) | Filesystem inputs / outputs (blocks) | Numerical result |
| --- | ---: | ---: | ---: | --- |
| 01 | 2.95 s | 244252 | 0 / 1840 | 1 passed, 28 warnings |
| 02 | 2.89 s | 244232 | 0 / 1872 | 1 passed, 28 warnings |
| 03 | 2.96 s | 244088 | 0 / 1744 | 1 passed, 28 warnings |

Median wall time: **2.95 s**; median reported maximum RSS: **244232 KiB**. This
includes pytest startup/imports, fixture generation, configuration, processing,
publication and the independent-reader subprocess, not Conda startup. Maximum
RSS is GNU time's reported process/child high-water statistic, not summed
concurrent-worker memory. Filesystem block counters are not decoded bytes or a
throughput measurement; zero input blocks reflects cache, not an absence of reads.

The reader subprocess imports xarray/NumPy, not FrameIt, and compares every
ocean crop to its own source window, including NaNs and legitimate zeros;
checks exact times, separate grids, native depth/time bounds, forecast identity,
source IDs and absence of ocean wind-representation metadata. Test success is
bounded decoded numerical agreement and metadata verification, **not** bytewise
product identity or scientific validation of real producers. Reuse the same
effective request, thread caps, filesystem/cache conditions and measurement
scope for the later comparison; no performance acceptance threshold is invented.

Task 2 is a development-evidence update only; public commands/configuration and
scientific output semantics are unchanged. Strict Sphinx build into fresh
`build/docs-preview/baseline-04` and its publication check both exited 0;
`git diff --check` passed. The public HTML is unchanged from Task 1's guide.

## Task 3 audit receipt — stopped for G1

The proposal covers 117/117 static default/open-map paths, dynamic validator
paths, public/mapping/generated/replay callers, exact proposed template commands
and comments/key sets, and 31/31 current reST page decisions. Mechanical
coverage checks ran in `frameit_env`; results are retained under ignored
`build/rc/g1-audit-01/inventory-check.log`. They measure inventory coverage,
**not** v2.1 runtime correctness or scientific validity. Current permissive cases
(null exclusions, empty file/name selections, ignored child controls and Zarr
format strings) were confirmed without data access and proposed tightenings
are explicit for approval.

A single fresh read-only design check found an omitted existing atmospheric
virtual-speed selection. Its implementation and independent FA speed-only oracle
were inspected; the proposal now explicitly preserves this path and non-exported
companions. No source code, template, fixture/oracle or numerical method was
changed. This is not human scientific or G1 approval, nor final whole-branch review.

Commands on the audit revision's unchanged public sources:

```bash
conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/baseline-05
conda run --no-capture-output -n frameit_env python docs/check_publication.py build/docs-preview/baseline-05
conda run --no-capture-output -n frameit_env python -m unittest discover -s docs -p test_check_publication.py
git diff --check
```

Strict build and publication check: exit 0; documentation unit tests: 2 passed;
diff check: passed. No full numerical/FA/GRIB suite or installed-artifact checks
are claimed for this documentation-only audit. G1 was subsequently approved by
the maintainer's **"Approved"** reply on 2026-11-05; the external plan is updated
with its exact implementation literals before Task 4. G2 and remaining
qualification gates stay pending.
