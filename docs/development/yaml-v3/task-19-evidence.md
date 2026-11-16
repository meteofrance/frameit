# Task19 — final permitted evidence, qualification blocked

This is not a completed qualification or source/test/asset freeze.
All commands use Conda `frameit_env`, Python3.13, source-selected
`PYTHONPATH="$PWD/src"`, `PYTHONDONTWRITEBYTECODE=1` and `TMPDIR=/tmp/opencode`
unless the wheel-build command has no source-import requirement. The approved
local fixture is selected with
`FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01"`.

Final permitted checks were read on17 November. Reviewed increments are local
commits `95c0f31`, `5f82964`, `6426e40`, `d82ef1f`, `bd882c2` and `2095dd8`.
Final checks121–130 used their reviewed runtime source and published prose;
subsequent edits are internal handover records only.

## Contract matrix

| Contract / focus | Current evidence | Remaining qualification |
|---|---|---|
| C1 source identity, inventories and ambiguity | Connected inventory/reader/report tests in thirteen-module95; source-byte guards; reviewed direct-v3 producers and caller conversions | Duplicate physical-source and native-grid caller contracts remain red |
| C2 independent source clocks and explicit association | Actual analytical native/polar CLI runs; independent checker with and without exported track | Not every real calendar/cycle/producer regime |
| C3 selected fields, levels and native axes | Initial-gap/member/geometry and analytical singleton/interface regressions; producer111 independently checks physical levels | Original AROME spacing and MNH W physical-value/mass-target requests remain blocked |
| C4 explicit scientific operations and defaults | Base polar units/basis opt-ins with default/product isolation; masks and real-input dependencies guarded | Original2.5km AROME request conflicts with current spacing limit; no scientific waiver |
| C5 tracking and scientific optionality | Current v3 binding/execution lanes; unfiltered AROME tracker metadata binding; analytical no-diagnostic run | Direct-v3 callers expose unit/basis/provenance contracts; no human/scientific sign-off |
| C6 polar masks, basis and sampling | Full polar/component modules in95; one/two-file CROCO finite-land masking; dynamic/changing masks rejected | No general real-producer or area-conservation claim |
| C7 output/data contract | Ordinary readers, independent clocks/levels and active crop checks; connected112 includes actual products, MNH replay and required small benchmark | Native-face, merge, track/provenance and other retained caller contracts remain open |
| C8 resource/installation selection | Final Task18 suite122:58 passes, including selected parent/spawn checkout and process/resource guards | No real Slurm execution; no installed-wheel run |
| C9 CLI/provenance/failure | Final122 includes failures, both cancellation transitions, no-clobber and child export; report/CLI modules pass in95 | FA partial-publication expectations and whole-branch gates remain open |
| C10 complete instructional tasks | Approved formulas and native/polar ordinary-reader runs; final Task17 suite121:53 passes; both documentation passes technically closed | New plot rendering and human usability acceptance unavailable |

## Commands and observations

Private evidence prefix:
`.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-resume-6abe753/`.

- `python -m pytest -q` **not run**: the single Task16 full diagnostic is reserved
  for an actual freeze, which known scientific and caller contracts prevent.
- Exact Task16 nine-file command with `--tb=short` and JUnit98:
  **313 passed/four failed**,512 warnings,two passing subtests,168.29s.
  The unchanged AROME spacing request fails; three template-comment mismatches
  were fixed afterward. Entire template module102:74 passed,0.69s.
- Exact Task17 four-file command from the checklist:
  `task17-final-121`:53pass,479warnings,101.12s.
- Exact Task18 two-file command from the checklist:
  `task18-final-122`:58pass,317warnings,62.57s.
- Targeted connected thirteen-module lane `review-connected-current-95`:
  1227pass,2306warnings,268.42s. It is not a whole-repository test run.
- Targeted fourteen-module caller inventory `remaining-callers-red-28`:
  231pass/237fail,2474warnings,30.70s. Node/cause records are in
  `remaining-callers-causes-44.json`; no failures were hidden with skips/xfails.
  These are historical pre-conversion results. Closed worker lanes and six
  downstream selections have87 named failures recorded in
  `caller-failure-inventory-101.json`; this is not a current combined run.
- Producer111:10 passes; connected112:21 passes,165 warnings,58.24s. Fresh
  producer I1–I4 closure confirms independently inventoried clocks/levels,
  per-record crop checks and the prescribed reference-centre handoff.
- Whole CROCO-vector/Zarr modules120:54 passes/five failures,156 warnings,7.94s.
  CROCO24/4, Zarr30/1; all six actual invalid-size cases pass.
  Current failures and cause/disposition are named in `task-16-checks.md`.
  The binding-before-reader failure is explicit red, not reader coverage.
- Restored-preservation104:3 passes/five contract failures. Entire request
  module114:147 passes/two retained rejection conflicts; no skips/xfails.
  Private128 independently parses these completed XML counts/failures.
- Staged-only source105 (no install, no unstaged caller changes):
  63 passed,242 warnings,70.18s. Its JSON records the tested tree and command.
- Runtime129 confirms Python3.13.18 and this source checkout.
  `python -m pip check`130 reports no broken requirements.
- `python -m pip wheel --no-index --no-deps --no-build-isolation . -w
  build/yaml-v3-wheel-01`: build succeeds; archive schema equals the generator,
  all eight templates and instructional generator equal source.
  This is historical archive-content evidence only, not installed execution.
  Later source/template changes make that wheel stale.
- Strict `sphinx-build -q -W --keep-going -b html docs/source
   build/docs-preview/yaml-v3-review-09`123 and publication125 pass.
  Publication units124:13 passes; release126:2 passes/two passing subtests.
  Independent technical confirmation and live1280/320px text checks cover
  the final checker paragraphs; earlier unchanged text coverage is retained.
- Scoped producer `ruff check`127 and15 complete scientific fixture/helper
  AST comparisons117 pass. Reviewers separately checked numerical oracles,
  tolerance keywords, parameter selections and shared signatures.
- `bash -n example/repeat_cases.sh example/slurm/array.sbatch
  example/slurm/frameit.sbatch` and `git diff --check` pass.

### Executed final commands

These show the executed programs and arguments; each Python/Sphinx/Ruff
invocation used the common source-selected environment above. Long logs were
redirected to the matching private numbered `.txt` files, not discarded.

```bash
conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_documentation_example.py \
  src/frameit/testing/numerical/test_polar_qualification.py \
  docs/test_documentation_plots.py docs/test_repository_examples.py \
  --tb=short \
  --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-resume-6abe753/task17-final-121.xml

conda run --no-capture-output -n frameit_env python -m pytest -q \
  docs/test_repository_examples.py src/frameit/testing/numerical/test_hpc_execution.py \
  --tb=short \
  --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-resume-6abe753/task18-final-122.xml

conda run --no-capture-output -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_croco_vectors.py \
  src/frameit/testing/numerical/test_zarr_export.py --tb=short \
  --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-resume-6abe753/downstream-current-120.xml

conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going \
  -b html docs/source build/docs-preview/yaml-v3-review-09
conda run --no-capture-output -n frameit_env python docs/check_publication.py \
  build/docs-preview/yaml-v3-review-09
conda run --no-capture-output -n frameit_env python -m unittest discover \
  -s docs -p test_check_publication.py
conda run --no-capture-output -n frameit_env python -m pytest -q docs/test_release.py \
  --tb=short \
  --junitxml=.superpowers/sdd/CHECKLIST_FOR_AGENTS/task-16-resume-6abe753/release-final-126.xml
conda run --no-capture-output -n frameit_env ruff check \
  src/frameit/testing/catalog.py src/frameit/testing/checks.py \
  src/frameit/testing/polar_benchmark.py \
  src/frameit/testing/numerical/test_v3_catalog_review.py --output-format concise
conda run --no-capture-output -n frameit_env python -m pip check
bash -n example/repeat_cases.sh example/slurm/array.sbatch example/slurm/frameit.sbatch
git diff --check
git diff --cached --check
```

### Cross-component review-focus limits

| Section5 case | Permitted evidence | Unclosed qualification |
|---|---|---|
| Excluded scientific times | Actual selected-reader/payload-guard modules in95 and sparse tutorial121 | Not a new real-producer campaign |
| Different U/V/W grids and singleton levels | Bound operation/region modules in95; separate interface/singleton tasks121 | Native-face and W physical-value contracts remain red |
| Second source clocks/cycles/masks | Analytical sources and independent-clock/optional-track tests121/122 | Duplicate-type fixtures are not reclassified; broader producer regimes remain unqualified |
| Failure before/during export | HPC lifecycle/status tests122; report/CLI95 | Two FA corrupt-transfer tests still conflict with earlier complete-publication expectations |
| Parent/spawn different checkouts | Source-location/resource tests122 | No isolated installed-wheel execution |

## Restrictions and next dependency — Tasks19–21 blocked

Do not install a wheel, repair the environment, run a production/cluster job,
download data, start a benchmark campaign or run standalone image/plot checks.
The wheel build did not install packages. No generated PNG was opened.

Resolve Task16's preserved-request/catalogue constraints and give explicit
disposition to retained caller contracts without changing fixtures, quantities,
clocks or numerical assertions to obtain green results. Only then freeze and use
the one full diagnostic. The existing wheel/archive evidence is stale and
cannot establish current installed behavior.

Task17's new plotting portion remains restricted. Task20's two full passes,
technical closure and permitted text checks are committed, with44 nonblocking
recommendation groups plus optional subparts explicitly deferred.

Task21's separate final whole-branch/full-documentation reviews have not been
dispatched against the knowingly incomplete, unfrozen branch. No actual human
usability observation or acceptance was received. Those gates follow the
scientific-contract disposition, reviewed repairs and permitted qualification;
bounded reviewer approvals are not substitutes.
