# v2 public-interface RC readiness

This development record is not published documentation or an RC qualification
certificate. Dated receipts include the inspected baseline on 2026-11-05 and
maintainer feedback corrections on 2026-11-06. Historical results are explicitly
separated from checks run during this plan.
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
| NEMO regional native T-grid scalars and separate U/V/W, barotropic and stress components: `(y,x)` geography; `deptht/u/v/w` retained | Fixed/prescribed ocean reference; or secondary source mapped independently to continuous atmospheric centres. Exact `common`/`strict` sample labels and native bounds | Scalar polar only if selected and eligible; NetCDF/Zarr; native component copies require `horizontal_vectors: native` | Present, bounded synthetic oracles in `test_nemo_netcdf.py` and `test_nemo_arome_coupling.py`. No inferred mesh/mask/angle, component rotation/collocation, current speed, W mass conversion or component polar analysis. Regional spacing limits remain; not arbitrary global/folded grids. |
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
  and starter catalogue and source-checkout first run are verified below;
   editorial pilots are drafted for G2 review below. G1 is not scientific
  sign-off, G2 or publication/deployment authorization.
- **G2 approved subject to completed corrections:** the maintainer said, "Once this
  is fixed, you have my approval." The requested corrections and checks are
  recorded below. This is editorial approval, not scientific or reader sign-off.
- **Task 10 engineering checks complete:** bounded numerical, analytical, reduced
  real-fixture, ordinary-reader, optionality and operational-safety evidence is
  recorded below. Final regression at `63faa89`: 1187 passed, no skips.
- Scientific/human review, unfamiliar-reader acceptance, wheel/sdist,
  fresh-environment checks, hosted CI and final candidate freeze remain open.
  Bounded fixture checks do not resolve the broader scientific evidence gaps.
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
mode was retained in Task 4 for replacement in Task 5 below.

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

## Task 5 starter catalogue verification

The generator now uses the approved `write_template(name, path, *, tracking=None,
coupling=None, force=False)` interface. Seven named selectors and the admitted
model/composed commands retain authoritative resource comments, active sections
and explicit declarations only. `--full` and guessed advanced-method starters are
removed; explicit UTrack/experimental multi-field YAML remains runnable. Existing
atomic publication prevents unforced replacement and avoids modifying a symlink's
input-data target when force replaces the selected configuration path.

- New catalogue tests were observed RED (**55 failed, 12 passed**) then GREEN
  (**67 passed**). They execute all 30 advertised command forms and pin minimal
  keys, fields, comments, same-base equivalence, invalid composition, no optional
  imports/access, complete effective inspection and overwrite behavior.
- Focused catalogue/configuration/multi-field/Meso-NH centroid tests:
  **234 passed, 583 known warnings**.
- `conda run --no-capture-output -n frameit_env python -m pytest -q`:
  **1179 passed, 4588 known warnings, 2 subtests, no skips, 529.54 s**.
- Strict Sphinx/publication `templates-02` passed; documentation unit tests (2),
  targeted Ruff F checks and diff check passed. The live catalogue, upgrade and
  other affected pages were inspected at desktop/narrow widths. Catalogue and
  upgrade tables fit the 390 px iframe; existing output-page overflow is recorded
  for later presentation work. No new screenshot/visual approval is claimed.

No runtime dependency or numerical method changed. Package-data already includes
every `templates/*.yaml` resource; executing the same catalogue from installed
wheel/sdist artifacts remains a Task 12 obligation, not a result claimed here.
At the Task 5 receipt, the instructional input and G2 editorial approval were still
pending; see the later receipts below for their current status.

## Task 6 instructional example verification

`frameit.testing.documentation_example.create_first_run_input(path)` and its
`--output` module command create two labelled times on a 17×17 geographical grid,
using only core NumPy/xarray/NetCDF dependencies. The dimensionless scalar follows
`1000*t + 10*(j-8) + (i-8)`, with two explicitly missing samples and a valid zero.
It is labelled synthetic/instructional, not an AROME producer or physical simulation.
Creation uses the existing atomic no-clobber writer; inputs are not overwritten.

- Four tests observed RED before implementation, then **4 passed**. A fresh
  ordinary-reader subprocess checks the literal 5×5 window, units, geography,
  times, track indices, valid zero versus NaN and unchanged read-only source bytes.
- Exact documented console commands replayed in a fresh owned directory:
  generator → `frameit init arome-fixed-scalar` → schema-only → metadata validation
  → dry-run → run. Result: `state: completed`, `tracking_complete: true`, only
  track and surface Cartesian NetCDF products. The independent reader printed
  the documented values without importing FrameIt.
- `conda run --no-capture-output -n frameit_env python -m pytest -q` →
  **1183 passed, 4590 known warnings, 2 subtests passed, no skips, 543.93 s**.
- Strict Sphinx/publication `first-run-01`, documentation unit tests (2), targeted
  Ruff F and diff checks passed. The linked quick-start rendered correctly in the
  live GUI at desktop/narrow widths, without page overflow or broken images.

This is source-checkout engineering evidence, not an installed wheel/sdist check,
real-producer qualification or human acceptance. The same installed-artifact
procedure remains mandatory in Task 12. No numerical algorithm or scientific
output schema was changed; illustration and editorial G2 review follow in Task 7.

The first post-commit combined focused run passed 71 assertions but exited 134
at native-library shutdown. Reproduction isolated xarray **automatic** backend
discovery loading cfgrib/ecCodes before a later pyproj import, matching the already
documented native PROJ collision in `../runtime-optimization.md`. Automatic reader
→ pyproj exited -6; explicitly named NetCDF reader → pyproj exited 0 without
loading those optional readers. The new test now selects `engine="netcdf4"`, as
the guide/fixture writer already do, and also checks a fresh-process read/import
and normal exit. Final combined focused run passed 71 with normal shutdown.
This is not an upstream native-stack repair or an environment/backend substitution.

## Task 7 draft pilots — G2 review pending

Historical draft receipt at `8500c3c`; the G2 correction receipt below supersedes
its pending status and stop instruction.

The installation, first-run and fixed-region pilots are implemented as a **draft**,
not approved editorial guidance for the remaining site rewrite. Both supplied SVG
masters were copied byte-identically; their 2172×724 wordmark and 1024×1024 symbol
compositions/colors are unchanged. The served wordmark was outlined with the
verified Liberation Mono Bold 2.1.5 face using existing FontTools. The export
recipe, logo roles, contrast tokens and scientific-colormap exception are in the
contribution guide. Documentation builds/readers do not require that font or tool.
Browser-rasterized outlines were compared to the supplied PNG artwork; this is
not human approval of branding or page appearance.

Two editable, captioned/alt-labelled schematics explain the chosen processing
products and fixed/moving sampling locations. No scientific data colormap was
restyled. A small existing-theme template override supplies navigation heading
levels and a native labelled mobile button, without another theme, script or
dependency. The wider documentation rewrite has not begun.

Verification in `frameit_env` (Python 3.13.18):

- `python -m unittest discover -s docs -p test_check_publication.py` → **4 passed,
  no skips**. Asset/export tests were observed RED then GREEN. They check missing
  or malformed configured source/build SVGs, live font text/CSS, scripts including
  event handlers, external resources, and the outline's geometry/color/glyphs.
- `python -m pytest -q src/frameit/testing/numerical/test_documentation_example.py
  src/frameit/testing/numerical/test_templates.py` → **71 passed**, normal exit,
  3 known native-ABI/NumPy deprecation warnings. The full numerical suite was not
  repeated for this documentation/tooling-only task; Task 6's result is above.
- Both console pilot routes were replayed in fresh owned directories, including
  input creation, inspection where shown, the exact `init`, schema/preflight,
  dry-run, execution, status and ordinary xarray/netCDF4 reader commands. Both
  completed with only track/scalar products, the expected 2×5×5 values, units 1,
  valid zero versus NaN and no FrameIt import in the reader. `pip check`, help and
  info also completed. Environment creation/installation commands were not rerun;
  fresh-prefix/installed-artifact qualification remains Task 12.
- Strict `sphinx-build -q -W --keep-going -b html docs/source
  build/docs-preview/pilots-05`, `python docs/check_publication.py
  build/docs-preview/pilots-05`, targeted Ruff F and staged diff checks passed.
  The staged check caught whitespace retained by the SVG serializer; a regression
  test observed RED, standard-library XML indentation fixed it, and all 4 docs
  tests passed again. Regenerated geometry, colors and labels are identical to
  the reviewed preview; only XML whitespace changed.
- Rendered DOM checks on installation, quick start, fixed region and contribution
  pages passed at desktop/narrow widths without page-wide overflow or broken
  images. Figures retain aspect ratios, unclipped labels and alt text; wordmark
  renders at 240×80 with clear space and the symbol favicon loads. Print-rule
  simulation at A4-like width hides navigation, removes its margin and avoids
  figure breaks; actual paginated printing was not available.
- Contrast checks: body **18.02:1**, links **6.38:1**, status headings ≥ **6.38:1**,
  focus ≥ **5.63:1**, relevant diagram/control boundaries ≥ **3.61:1**. The browser
  audit caught inherited footer contrast (3.95:1), missing navigation heading
  levels and small expand controls; browser assertions observed RED then GREEN
  after the focused fixes. Footer text is now **6.16:1**, expand controls 24×24,
  mobile control 44×44, and visible focus/menu click-open/close checks passed.
- Lighthouse on both the fixed-region and first-run pilots: accessibility **100**,
  best practices **100**, SEO **80** (missing meta description). This is an automated sample,
  not accessibility certification. No SEO extension was added.

Limitations for G2: the invisible desktop prevented screenshot capture and tool
key delivery, so real Tab/Enter/Space traversal remains a human check. Native
button semantics, focus styling and click behavior were checked, not misreported
as real key events. Actual print pagination and unassisted-reader/editorial
acceptance remain open. Existing narrow-layout issues on older technical pages
are retained for the later approved presentation work. No new scientific method,
default, configuration/output semantics, release qualification, push or deployment
is implied. Commit the verified draft, then wait for page-specific G2 feedback;
do not mark Task 7 complete or start Task 8.

## Task 7 G2 corrections and approval

The maintainer reviewed `pilots-05` and requested shorter wording, clearer
installation, separate first-run/quick-start pages, Maxence DEFERREZ credit,
current-only YAML guidance and fully visible figures. They accepted the
fixed-region prose. Their exact approval condition was: **"Once this is fixed,
you have my approval."** The following checks establish completion of those
corrections; no additional human inspection or scientific approval is invented.

- Installation now has one reference-environment route. `environment.yaml`
  already installs FrameIt, so no duplicate pip step is added. Advanced core/extra
  setup is linked separately. No environment was rebuilt during this review.
- **Your first run** explains the generated YAML and has the reader change
  `run.name` to `first-run` and `output.directory` to `./results`. **Quick start**
  is a short Meso-NH template/edit/check/run reminder with CLI/template links.
  Navigation and callers distinguish them. The contribution guide records these
  rules and shorter, direct wording for the rest of the documentation.
- Public schema-history/conversion guidance and its page/links are removed.
  Current YAML uses `schema_version: "2.1"`; strict admission is unchanged.
  Only the shared error text changed in processing code. Independent scientific
  data, manifest/status and FA worker/provenance contracts were not rewritten.
- Maxence DEFERREZ is included in the documentation copyright, README credits and
  package author metadata. Other author credits and the existing citation remain.
- All eight figures have full-size links. Screen display is limited to 75vh with
  `object-fit: contain`; print has no screen-height cap. Scientific raster data,
  SVG geometry and colormaps are unchanged. A nearby output table reuses the
  existing wrapping style to remove its narrow-page overflow.

Verification in `frameit_env` (Python 3.13):

- Two documentation checks and the current-only loader-error check were observed
  RED before the corrections. `python -m unittest discover -s docs -p
  test_check_publication.py` now passes **6 tests**, no skips.
- `python -m pytest -q` → **1185 passed, 4590 known warnings, 2 subtests passed,
  no skips, 566.69 s**. Tests retain source-read-only/unchanged bytes, independent
  literal values, valid zero versus NaN and normal subprocess exit checks.
- The six instructional tests include both unchanged starter and edited first-run
  configurations, plus the refresher's Meso-NH case. Both documented console
  routes were also replayed in fresh owned directories. The edited first run
  completed with 2×5×5 scalar values/units 1; the Meso-NH reader checked 2×3×3
  MSLP = 100000 Pa. Reader processes imported no FrameIt. Help, inspection,
  settings/resolved settings and the refresher's three extra starter commands ran.
- Strict Sphinx and publication checks passed for `pilots-09`; `pip check`,
  targeted Ruff F and diff checks passed. `pilots-06` caught a short heading
  underline and is not a passing iteration. Public sources/artifacts contain no
  link to the deleted schema-history page.
- Browser checks covered all **8 figures at 320/390/768/1200 px** (32 placements):
  image boxes fit, height limits hold, aspect is contained and full-size targets
  return HTTP 200. All **44 SVG text labels**, as well as drawing bounds, lie
  within their viewBoxes. Existing raster images were inspected without changing
  data. The revised onboarding pages and output page have no overflow at 390 px;
  changed reference pages load with no broken images/history links. Copyright
  credit and the print height-cap reset were checked in the rendered pages.

The maintainer's G2 condition is met by the corrections above. Keep the live
preview available. Actual desktop screenshots, real key delivery and paginated
print inspection remain unavailable in this browser session; bounds/focus/print
rules are not misreported as those checks. Fresh installation, installed artifacts,
unassisted-reader acceptance, scientific review and release qualification remain
their separate later gates. No push, publication or deployment is authorized.

## Post-G2 correction: focused processing and useful documentation

The maintainer requested site-neutral HPC guidance, removal of visualization
functionality, and a review of all user documentation for unhelpful text. During
execution they also corrected the name to **Maxence DEFERREZ** and supplied refined
logo masters. This correction does not start the remaining release tasks.

Changes:

- Removed `frameit.viz`, the plotting-only angular closure helpers/re-export,
  standalone plotting example/tests, qualification PNG generation and figure
  options, plotting logger settings, the explicit Matplotlib environment dependency
  and Slurm `MPLBACKEND` overrides. Explanatory documentation figures remain.
- Preserved numerical endpoint validation, analytical truth, errors, profiles,
  spectra, masks, means/FFTs, production settings and scientific product schemas.
  Qualification now writes JSON/NetCDF only. Intentional compatibility removals
  include the plotting APIs, `figures` arguments and `--no-figures`; the numerical
  report flag is `mean_fft_checked` instead of `mean_fft_plotting_checked`.
- Reviewed all 33 original public reST sources and README. Removed the
  visualization page/navigation/recipes, installation repetitions, development
  commentary, unsupported future-command promises and redundant disclaimers.
  Kept method records, references, assumptions, applicability and actionable
  failure behavior. The contribution guide records the choose/run/interpret/
  troubleshoot usefulness rule and site-neutral HPC wording.
- Corrected stale current-schema examples (`output.backend`, `export.enabled`,
  `polar.variables: extracted`, pair-specific winds) against the resolver and
  shared wind/lookup code. No scientific behavior was changed to fit the docs.
- Used the existing wrapping styles for tables, long keys and prose after narrow
  reference-page overflows were observed. Code blocks retain their scrolling.
- Corrected current credits/copyright/package author spelling. Both packaged logo
  masters match the supplied refinements byte-for-byte. The outlined wordmark uses
  the exact Simpletix normal, Version 1 face, preserving the new size, positions,
  colors and zero rotations. No font file or new reader dependency is distributed.

Verification in `frameit_env`, Python 3.13.18:

- RED: analytical CLI failed on `import matplotlib` with plotting imports blocked;
  publication checks failed on stale visualization pages/references. Both are now
  covered. The launcher check also failed when a plotting override replaced its
  caller's environment; it passed after removing that override. The old logo
  recipe rejected the new face before its narrow recipe/test update.
- `conda run --no-capture-output -n frameit_env python -m pytest -q` → **1186
  passed, 4590 known warnings, 2 subtests passed, no skips, 558.66 s**, normal exit.
- `conda run --no-capture-output -n frameit_env python -m unittest discover -s
  docs -p test_check_publication.py` → **7 passed**, no skips. The optional exact-
  font regeneration check ran here; builds/readers use the committed outlines.
- `conda run --no-capture-output -n frameit_env python -m
  frameit.testing.polar_qualification --output
  build/rc/plot-removal-qualification-01` → **463 checks passed, zero failures**.
  An independent process importing no FrameIt reopened both NetCDFs and checked
  values, units, topology and coverage. Seven cases, profiles and spectra remain;
  only two JSON and two NetCDF products were written.
- `conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b
  html docs/source build/docs-preview/pilots-17` and `conda run --no-capture-output
  -n frameit_env python docs/check_publication.py build/docs-preview/pilots-17`
  passed. Targeted Ruff F, `bash -n` on both launchers and `git diff --check` passed.
  All 26 YAML code blocks parsed; corrected output fragments passed the current
  resolver. Local file/fragment checks passed for 34 HTML pages and 2090 links.
- Final rendered review: **31 topic pages at 320/390/768/1200 px** (124 placements),
  correct name/footer and current logo on each page, no page overflow or broken
  images. All **8 figures/32 placements** fit; all **44 SVG labels** and drawings
  fit their viewBoxes. Full-size figure targets returned HTTP 200. New logo,
  symbol and glyph bounds fit; the served wordmark contains seven glyph paths and
  no live text. Independent FreeType advances agree within 0.2 px with the export.
- Fresh-context read-only review of the plotting/prose correction found no
  Critical/Important defects and one
  leftover plotting-setting cleanup, addressed above. Retained explanatory images,
  removed APIs and historical records were reviewed as intentional scope choices.

The live `pilots-17` installation preview remains available. Earlier screenshots
were inspected; the final logo screenshot attempt reported a non-visible window,
so latest-logo review is rendered DOM/geometry, not a claimed pixel capture or
human approval. Fresh installation, hosted CI, real HPC jobs, keyboard traversal,
paginated print and scientific/release sign-off were not run here. Existing data,
unrelated `opencode.json`, font files and supplied originals were not modified.

## Task 8 reader guides — first page group

The maintainer approved `5fb4b57` and said "Approved. Proceed." Native execution
continues from Task 8. The current wording, logos, site-neutral HPC guidance and
plotting removal remain binding; no scientific/release acceptance is inferred.

- Added six task routes (fields/levels, moving regions, scalars/vectors, polar,
  coupled inputs, storage/resources), three linked concepts and phase-oriented
  troubleshooting. Existing method pages, equations, figures and URLs remain.
  Navigation separates tasks/concepts from detailed reference; README stays short.
- Five editable SVG schematics clarify location/basis/motion, time association,
  independent source support, missing/zero and compute chunks/storage shards.
  They contain labels, alt text/captions and no new rendering dependency.
- `conda run --no-capture-output -n frameit_env python -m pytest -q
  src/frameit/testing/numerical/test_templates.py
  src/frameit/testing/numerical/test_documentation_example.py` → **73 passed,
  3 known warnings**, normal exit. All five new contextual YAML fragments passed
  the current resolver against their actual generated starters.
- Exact inspect/init/validate/resolved-config/dry-run/run routes were replayed on
  compact instructional inputs in fresh `build/rc/task-8-guides-02` directories:
  polar NetCDF, prescribed moving centres and bounded synchronous Zarr. All exited
  normally with completed/complete status. Fresh readers importing no FrameIt
  checked axes, units, quality arrays, source zero/NaN, moving centres and Zarr
  values. Source SHA-256 values were unchanged. No real-producer claim follows.
- The first polar replay correctly rejected a 1000 m step finer than the resolved
  1076.76 m native spacing. The guide now requests 1500 m, giving radii 0/1.5/2 km.
  No validator, sampling method or scientific default was changed to fit the guide.
- Strict Sphinx `handbook-01` found 14 short heading underlines; corrected at
  source. Fresh `handbook-02/03` strict builds and publication checks passed;
  **7 documentation tests** passed. Rendered inspection covered 12 topic/index
  pages at four widths (320/390/768/1200), with no overflow or broken images.
  All five new SVG drawings and **57 labels** fit their viewBoxes. Screenshot
  capture remains blocked by the invisible desktop window; no pixel/human check
  is claimed. The live `handbook-03` polar guide remains available for feedback.

This page group changes documentation only. No runtime, output-schema, scientific
default, dependency or logo changes. Reference/ordinary-reader completion follows
in the second Task 8 page group; Task 8 is not yet marked complete.

## Task 8 reference and reader completion

- Completed the current reference's polar defaults/constraints, input/SURFEX and
  time-policy links, null/omission/precedence explanation and explicit overwrite
  distinction (runtime true; generated starters false). Detailed tracker/FA
  specifications remain canonical rather than copied into onboarding.
- Extended ordinary-reader guidance with the exact guided scalar check, native
  source/vertical/time distinctions, polar quality flags, lossless storage/dtypes
  and an editable final-status/provenance schematic. Numerical algorithms,
  defaults, source data, configuration admission and output schemas are unchanged.
- `conda run --no-capture-output -n frameit_env python -m pytest -q
  src/frameit/testing/numerical/test_configuration_v2_1.py
  src/frameit/testing/numerical/test_zarr_export.py
  src/frameit/testing/numerical/test_documentation_example.py` → **167 passed,
  587 known warnings, 41.47 s**, normal exit. The exact new reader snippet also ran
  in a fresh process without FrameIt against the guided first-run products.
- Strict Sphinx `handbook-04`, its publication check, **7 docs tests** and diff
  check passed. All **44 HTML pages / 3065 local links and fragments** resolve;
  **306 previous topic anchors** and their URLs remain. Final rendered review:
  **41 topics × four widths = 164** checks, **14 unique figures / 68 placements**,
  **10 SVG drawings / 113 labels**, no overflow, clipping or broken images.
  One long browser call timed out after page checks; state was inspected before
  a separate completed drawing/label pass. No timed-out return is counted as a pass.
- The complete reading path now separates first run, quick reminder, tasks,
  concepts, reference/troubleshooting and method detail. The live `handbook-04`
  output page remains available. Actual desktop screenshots, real keyboard input,
  print pagination, unfamiliar-reader and scientific/release approval remain
  unrun; DOM/geometry checks are not human acceptance.

## Task 9 candidate CI and local links

- Added standard-library `check_local_links(artifact)` to the existing publication
  checker. It validates HTML href/src targets, downloads, URL-encoded paths and
  HTML fragments inside the artifact; missing assets, escaped paths and file URLs
  fail. External URLs are not fetched. Native scientific identifiers are not
  mistaken for links or development labels.
- RED: two new link tests found the absent checker; the artifact integration test
  accepted a broken target. GREEN: **9 documentation tests**, actual `handbook-05`
  and fresh strict/publication `candidate-ci-01`, targeted Ruff F and diff checks.
- Existing docs workflow failed the local `dev_md` trigger assertion before
  changes. It now builds for main/dev pushes and PRs targeting either, without
  path-based skips. Review artifacts contain only generated public HTML. Pages
  artifact upload and deploy are both guarded to push/main; only that guarded
  deploy job grants Pages/OIDC writes. Runtime core checks now include the current
  schema, every starter command and compact first run; native/full jobs remain.
- Parsed-workflow checks passed for triggers, Python 3.13, unconditional build/core
  gates, upload scope and least privilege. A truth table evaluated the actual
  Pages/deploy expressions: main push true; dev push and pull request false.
  `actionlint`/`zizmor` were unavailable; no hosted CI or repository-protection
  configuration is claimed. Maintainers must require both build/core statuses.
- The contribution guide records these checks. Its rendered `candidate-ci-01`
  page fits at 320/390/768/1200 px with no broken image. The live preview stays
  available. Full `conda run --no-capture-output -n frameit_env python -m pytest -q`
  exited normally: **1186 passed, 4590 known warnings, 2 subtests, no skips,
  556.05 s**. No native shutdown failure occurred in this run.

These are documentation tooling/CI changes, not scientific processing or schema
changes. No environment creation, source-data upload, package publication, hook,
push or deployment was performed.

## Task 10 qualification — native shutdown blocker reproduced and corrected

Revision `550a5ef` was tested with a clean tracked tree, Python 3.13.18 on
Bazzite 44.20261026.0 / Linux x86_64 / local Btrfs. Dependency/native versions
match the recorded reference stack above; `python -m pip check` passed. No
environment, native library or backend selection was changed.

The installed reduced fixture was verified read-only: **9 files / 61,387,047
bytes**, recipe `frozen-ci-1`, manifest version 1, content identity
`5346576eed1ef8e8c488b88c00592ec7c410830a65dad20eb8293a33771084b3`, manifest SHA-256
`2dd8103dbc9c864e1f9440cbe04114b48c2954ca8b7bfd799d926c8b6b80a138`.
Every declared file hash/size and required metadata matched. The supplemental
prescribed track passed its own schema/exact-time check (12:00 only); its new
fingerprint is not misrepresented as a claim by the older manifest. Fixture file
set, sizes and mtimes were unchanged. No full/private source archive was acquired.

`conda run --no-capture-output -n frameit_env frameit run-all-tests --output
build/rc/all-tests-01` completed its internal numerical run (**1186 passed,
4589 warnings**), analytical service (**463 checks**) and reduced matrix
(**24 PASS, one explicitly EXCLUDED UTrack case**). However, the **outer process
aborted at shutdown, exit 134**, after writing `all-tests.json` with exit_code=0.
This attempt is **not a passing qualification**, regardless of those inner results.

Minimal reproduction: a single AROME matrix **plan-only** CLI reported success,
then exited -6. Import audit traced ecCodes initialization during fixture metadata
verification before `SimulationConfig` later initialized pyproj. A fresh-process
controlled differential (same inputs/options; core geometry initialized first)
exited 0. This matches the existing global native-PROJ collision described in
`../runtime-optimization.md`, not corrupt scientific data or failed cleanup.

The small fix moves the already required `Geod` import from configuration
construction to its module import, before matrix inventories. It changes core
initialization order only. No decoder/library substitution, native-stack upgrade,
scientific equation/default, unit convention or output-schema change is made.
A regression executes the real one-case matrix plan and requires normal process
exit and a valid five-file plan, not only a success message. Observed RED (-6)
then GREEN; **203** lifecycle/configuration/catalogue/combined-service checks passed,
583 known warnings, normal exit. Ruff F and diff checks passed.

The fix was committed as **27dc486**. Against that exact clean revision,
`conda run --no-capture-output -n frameit_env env
FRAMEIT_BUILD_REVISION=27dc4860b9f38fa4441fb86c529c0825ef9c3a2d frameit run-all-tests
--output build/rc/all-tests-02` **exited normally with code 0**:

- **1187 numerical tests passed**, 4589 known warnings, 577.98 s. JUnit records
  1189 cases including two dynamic subtests, zero errors/failures/skips. The
  ordinary project command and combined runner collect the same 1187 test IDs.
- **463 analytical checks passed**, zero failures; the existing seven cases,
  error profiles, harmonics and coverage records remain.
- **24 reduced matrix cases passed**, with one explicitly excluded UTrack case:
  the frozen crop does not establish its spatial context/margins. Required cases
  executed; the prescribed case used its exact single-time overlap. This matrix
  checks execution/product contracts, not real-field accuracy against a reference.
- Total combined wall time was 737.26 s. Its separate computation-only matrix
  metric was 29.29 s, not whole-pipeline or throughput performance.
- A fresh xarray/NumPy/netCDF4 process importing no FrameIt reopened **107 matrix
  products plus two analytical products**. It checked literal constant values,
  units, endpoint-exclusive axes, undefined origin directions, changing support,
  schema/time metadata and bounded one-plane readability. Independent coupled
  NetCDF/Zarr value/depth/sigma/bounds/mask oracles also executed in the full suite.
- Post-run fixture content identity, manifest hash, every recorded content hash,
  size and mtime remained unchanged after both attempts.

### Risk-based coverage and safety

| Risk / admitted scope | Executed evidence |
| --- | --- |
| Current schema, CLI precedence, named/composed starters, replay | Configuration, template and first-run suites; current emitted YAML in 24 matrix cases |
| AROME/MNH native/scalar/staggered vectors and tracking | Reduced real-fixture matrix; wind/units/level tests; independent synthetic centroid/multi-field oracles with their documented limits |
| NEMO native depths/components and explicit preceding-hour means | `test_nemo_netcdf.py`, `test_nemo_arome_coupling.py`; source-window/ordinary-reader checks, native bounds/zero/missingness |
| CROCO native sigma/current masks, SEA support and coupled sampling | `test_croco_netcdf.py`, `test_croco_vectors.py`, `test_croco_mnh_coupling.py`, `test_mnh_surfex_support.py`; 1e-12 analytic rotations and independent native samples |
| FA isolation, declarations, gridpoint/cube boundaries | Maintained-stack `test_fa_*.py`, primary/shared-pair suites; actual worker timeout/SIGSEGV and normal parent/child shutdown |
| Optional polar/support and output backends | Scalar/vector/periodic/coverage suites and analytical service; actual optional stack plus simulated missing/invalid dependencies; ordinary NetCDF/Zarr readers |
| Ownership, overwrite, interruption and completion | `test_hpc_execution.py`, `test_zarr_export.py`, coupled failed-write cases; sources/prior products retained under the documented policy |

Additional bounded fault injections used owned synthetic products only. SIGKILL
after payload writing preserved original NetCDF/Zarr bytes; a controlled kill
after Zarr's backup rename retained the prior store in a readable hidden backup
and left the documented final-path visibility gap. Unpublished partial products
remained separate. Fresh readers checked old values/units without FrameIt. This
does not establish fsync durability or an all-products transaction.

The independent NetCDF completion checker accepted a normal compact run and
rejected missing final status, running/incomplete states, stale sizes and missing
products on owned copies. Original run/status bytes were unchanged.

The exact Task 2 workload was remeasured after the fix with the same request,
one synchronous export/Dask/native worker and sequential fresh processes. A
first measurement incurred 696 input blocks and is retained as warm-up, not
silently mixed into the zero-input-block baseline comparison. Three subsequent
warm runs were **3.08/2.84/2.87 s**, RSS **244480/244272/244872 KiB**, input blocks
**0/0/0**, output blocks **1808/1840/2160**. Median **2.87 s / 244480 KiB** versus
baseline **2.95 s / 244232 KiB** shows no material resource trade-off in this
bounded sample; it is not a general speedup or statistical equivalence claim.

External ecCodes-first/pyproj-later code can still expose the incompatible native
stack. No full-domain centroid, independent NOAA execution, unavailable UTrack
weights, arbitrary real ocean producer or all-Linux qualification is implied.

## Fresh implementation review and final fix pass

A read-only fresh-context review covered the 15 implementation commits from the
maintainer's assignment baseline `212fcca` through `27dc486`, including connected
current code. Earlier user branch work was not reset or treated as a new refactor
assignment. No Critical issue was found. Two functional verification gaps were
confirmed and addressed in one fix pass:

- Core CI selected three configuration integration cases requiring polar/GRIB
  dependencies and frozen data absent from a core checkout. They moved unchanged
  to `test_configuration_integration.py`, retained by the required native full
  suite. Function ASTs, all assertions and tolerances are identical. With optional
  imports/fixture reads blocked, the mandatory core set went from **3 failed / 200
  passed** to **200 passed, no skips**. The three native cases separately passed
  with their actual dependencies/fixture. No second development environment was
  created and no required scientific case was converted into a skip.
- The artifact checker treated `/...` URLs as artifact-relative, unlike browsers
  under `/frameit/` or iteration prefixes. Three present-target regression cases
  failed first, then passed after rejecting root-relative local URLs. **10 docs
  tests** and the actual artifact pass. The reviewer labelled this Minor; it was
  regraded as a functional publication false-pass rather than visual polish.

Hosted CI still needs actual fixture provisioning and an authorized push; these
local checks are not hosted results. Final verification of the fix pass at
**63faa897aa1c8badd33a7bec2aa0ff59f48a5b06** completed with normal exit 0:

- `conda run --no-capture-output -n frameit_env python -m pytest -q`:
  **1187 passed, 4590 known warnings, two subtests passed, no skips, 506.39 s**.
- `conda run --no-capture-output -n frameit_env python -m unittest discover -s docs -p test_check_publication.py`:
  **10 tests passed**, no skips.
- `conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/final-review-02`
  and `conda run --no-capture-output -n frameit_env python docs/check_publication.py build/docs-preview/final-review-02`:
  strict build and publication/local-link checks passed.
- Targeted Ruff F and `git diff --check` passed. The Task 10 ledger receipt
  retains the complete commands and log. The later review fixes changed tests,
  CI and documentation tooling, not the scientific runtime qualified at `27dc486`.

Task 10 is complete within its bounded engineering scope. There is no second
review pass, scientific sign-off, artifact qualification or frozen RC claim.

## Tasks 11–12 human and artifact gates — open

Reference identities and abstracts were checked against publisher-deposited
Crossref records for Nguyen/Molinari/Thomas (2014), Marchok (2021), Ullrich/Taylor
(2015), Fischer et al. (2022), Ryglicki/Hodyss (2016), Zhao et al. (2019) and
Raynaud et al. (2024). Springer's publisher record verifies Karney (2013),
`10.1007/s00190-012-0578-z`. Direct AMS article retrieval returned 405; registered
metadata/abstracts do not verify every equation, method departure, threshold or
community-adoption claim. Required detailed scientific review remains open.

Before an RC freeze, obtain actual human scientific/technical scope review and an
unfamiliar reader's unassisted first run/navigation feedback. Existing experimental
and beta methods remain labelled; no method was promoted, silently removed or
scientifically approved by the agent or engineering reviewer. Full-domain native
centroid/NOAA/real-ocean evidence gaps require their documented data and review.

### Scientific/technical review request — pending

Please review revision `63faa89`, the support/evidence matrix above, and the
method records in `docs/source/tracker/`, `docs/source/polar_projection/` and
`docs/source/user_guide/ocean_netcdf.rst` against `AGENTS.md` section 6:

- For each supported scientific claim, check the primary method, evidence of
  community use, actual implementation/departures, independent oracles/tolerances
  and applicable regimes. Include core interpolation, vector/unit transformations,
  time association and native depth/sigma/support semantics, not only trackers.
- Resolve the full-domain centroid/native-adaptation and independent NOAA evidence
  gaps explicitly. Retain experimental/beta labels and record unavailable UTrack
  weights; passing software checks do not close these gaps.
- Return the reviewer/role, date, revision, reviewed claims, evidence consulted,
  required corrections and a per-claim scope decision. A decision to restrict or
  defer a claim needs explicit maintainer review; it is not silent removal.

### Unfamiliar-reader and final reading request — pending

Ask a graduate-level researcher or intern unfamiliar with FrameIt to follow
**Your first run** through its ordinary-reader check in a new directory, using
only the documentation and without maintainer assistance. Then ask them to find
one deeper task from the navigation without repeating onboarding.

Record the revision, environment/installation used, commands, output/status
interpretation, guessed steps, blocking errors and confusing choices or figures.
Distinguish reuse of an existing environment from a fresh installation. Ask for
page-specific desktop/narrow feedback, including labels/logos and real keyboard
navigation; report print pagination separately if it is actually checked.

No human reviewer/reader result has been received. These requests are a handover,
not acceptance receipts. Record actual feedback and resulting corrections before
checking Task 11 complete; leave Task 12 unstarted meanwhile.

This evidence-only handover changes no public pages, commands, scientific claims
or executable files. A fresh strict `human-review-01` build, publication check and
10 documentation tests passed; first-run and coupled-task pages loaded with
intact images at desktop/narrow widths. This is not a human reading receipt.

Version remains 1.1.0 until Task 12. Wheel/sdist, source-data redistribution audit,
fresh reference installation, final candidate metadata, hosted CI and release
freeze are uncompleted. In particular, local ignored fixture availability does
not authorize redistributing it in an artifact; `build` is not installed in the
current reference environment. Do not substitute another runtime or claim a
fresh installation from this existing prefix. Real keyboard input, screenshots,
print pagination and final human reading acceptance remain unrun.

The live public preview and persistent plan ledger remain available. No push,
main merge, remote tag, package publication or documentation deployment occurred.

## Maintainer reading-feedback corrections — 2026-11-06

Actual editorial feedback was received after `c4559c2`; the preceding pending
requests describe that earlier handover, not the absence of this feedback.
Independent scientific approval, an unfamiliar reader's unassisted run and final
human reading acceptance remain separate open gates. Task 12 has not started.

### Changes and compatibility

- Four expandable parent sections: Start here, Task guides, Reference, Development.
  Inactive branches are retained so the existing RTD theme provides real controls.
  Existing nonexperimental topic URLs remain; experimental comparison records
  moved byte-for-byte to `docs/development/polar/`, outside public search/downloads.
- Public `fields_2d` selects fields without a selectable vertical axis. Extraction,
  explicit polar selection, wind declarations, source-local inputs, starters,
  examples, catalogue emission and replay use that name. Old public `surface` is
  rejected actionably. Internal groups, native GRIB identifiers, source IDs and
  `.surface` product names/metadata are unchanged; no scientific kernel changed.
- The full annotated key reference covers the current schema and open maps. It is
  explicitly non-runnable, with alternatives and dedicated contract links. Plain
  explanations distinguish native snapping/rounded widths, levels, time support,
  sampling, basis rotation and frame motion. Six tracker pages end in limitations;
  centroid troubleshooting follows the method, and two method schematics were added.
- HPC now uses `environment.yaml`/`frameit_env`; the extra recipe is removed.
  Accepted installation/Quick start structure, supplied artwork and credits remain.
- Standalone scripts/configurations in `example/plots/` generate five new PNGs.
  They import no FrameIt, add no runtime dependency/diagnostic and draw no grids or
  graticules. Captions and `reference/illustrations.rst` record data, assumptions,
  units, temporal support, display limits and regeneration commands.

### Real-data scope and scientific limits

The maintainer named the two BATSIRAI Meso-NH diagnostic files and explicitly
selected **Derived rain-only dBZ** after read-only headers found no reflectivity.
Only horizontal fields/coordinates were read. `ACPRR` is rainfall amount in mm;
the 2022-02-01 00:10–00:20 increment has no negative finite values. The external
illustration uses `R=(A2-A1)/(1/6 h)`, `Z=200 R**1.6`, then `10 log10(Z)` with
the documented units. Zero rain is `-inf`, missing remains NaN, and reset-like
decreases fail. The −10 dBZ display limit is not a data mask or physical zero.

This is not instantaneous model reflectivity, ice scattering, a locally calibrated
retrieval, a validated FrameIt method or evidence of track accuracy. Crossref
verifies the Marshall/Palmer (1948) publication identity; it does not validate these
constants or their applicability to BATSIRAI. The primary equations and local
microphysical applicability were not independently established here.

Both small FrameIt runs completed with complete tracking. Native spacing is
3000 m; requested 500×500 km crops have 167×167 points. The fixed centre is the
first source MSLP minimum (-16.342215392786485°, 62.15487544109405°); the fixed polar
product has 43 radii at 6 km spacing and 180 azimuths. Rainfall amounts are sampled
before the nonlinear estimate. Moving fixes are `(380,732)` then `(380,731)`:
only one grid point apart, with no artificial trajectory extension. Source metadata
describes `UM10/VM10` as zonal/meridian 10-m winds in m/s, declared Earth-relative.

Ordinary netCDF4/xarray readers importing no FrameIt checked status, axes, units,
geography and tracks. Twenty independent native-window value/geography/metadata
assertions match exported rainfall to the raw source. Source sizes/mtimes were
unchanged across those checks; no complete-archive checksum/identity claim is made.
The actual instructional workflow also completed, its source SHA-256 unchanged;
its separate plot retains dimensionless values, valid zero and missing samples.

### Verification and review

All Python work used Conda `frameit_env`, Python 3.13.18. No environment was created
or upgraded. Commands and complete logs remain in the ignored plan workspace.

- `conda run --no-capture-output -n frameit_env python -m pytest -q` → **1201
  passed, 4604 known warnings, two subtests, no skips, normal exit 0, 527.99 s**.
  Subsequent review fixes affected documentation prose/example indentation and a
  documentation parsing test only, not the tested numerical implementation.
  The earlier full run's six stale-fixture failures were corrected without
  changing independent numerical assertions; focused verification passed 297 tests.
- Public group regressions observed RED→GREEN. Six approximation checks passed;
  two CLI checks reproduced time-coordinate mismatch, then passed after the fix.
  All eight plot tests are included in the full run and test overwrite refusal.
- `conda run --no-capture-output -n frameit_env python -m unittest discover -s docs
  -p test_check_publication.py` → **13 passed**, no skips. The new UTrack example
  parsing regression was observed failing before the indentation correction.
  All **32** public YAML code blocks parse; fragments are not called standalone runs.
- `conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b
  html docs/source build/docs-preview/feedback-04` and
  `conda run --no-capture-output -n frameit_env python docs/check_publication.py
  build/docs-preview/feedback-04` → **passed**. Strict warnings were fixed at source,
  not suppressed. Targeted Ruff F and `git diff --check` passed.
- Rendered review at 320/390/768/1200 px: **51 topics / 204 placements**, **80 image
  placements**, no page overflow or broken/clipped images. All **12 SVG drawings /
  120 text labels** fit their viewBoxes. All four parent controls expand/collapse;
  each tracker ends in Known limitations. The three final review-corrected pages
  were rechecked at all widths in `feedback-04`. A timed-out image-decode helper
  was inspected/removed and the full successful measurement rerun; no timeout is
  counted as a pass. Final live pages are open in the GUI; pixel capture failed
  because the desktop window was not visible. DOM checks are not human acceptance.
- One fresh-context read-only review found no Critical issue, two Important
  (three stale public group references, malformed UTrack YAML) and one Minor.
  Both Important findings were verified and corrected in one pass. **Deferred
  minor:** an invalid explicit polar subset can still name internal `surface`
  in its error path; rejection and accepted/generated configuration are correct.

### Scope rulings and remaining gates

The review's set-aside areas were resolved explicitly: scientific Z–R/track
validity is not granted (risk: unsuitable downstream scientific use); pre-base
numerical/UTrack behavior is preserved (existing limits remain); scripts stay
bounded to their named examples (other producers/calendars/counters/meshes need
adaptation); real-source regeneration is checked but HPC performance/fresh installs/
artifacts stay open (platform/artifact-only defects may remain); rendered bounds
do not replace human visual/keyboard/print/scientific/unassisted-reader acceptance
(usability or validity gaps may remain); unchanged experiments are relocated, not
scientifically promoted (their validation debt remains). Detailed rulings stay in
the plan ledger. No new algorithm/default or output schema is scientifically approved.

Keep the preview and plan workspace for feedback. No push, main merge, publication,
deployment, full qualification repeat, private-source upload, production job or
artifact/fresh-environment qualification was performed by this correction.

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
