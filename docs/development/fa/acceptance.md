# Final local documentation acceptance

Step 5, 2026-10-28, starting checkout `206a500`. Root instructions, both external
maintainer plans, current docs/build/deployment contracts and retained developer
index were read. Starting tracked tree was clean; existing untracked `opencode.json`
was preserved. No push/deployment, production run, download or private/bulk dataset
copy was performed.

**Result:** local source/artifact and bounded user-journey acceptance passes.
Hosted Python-3.12 CI, fresh environment creation and browser/external-link checks
remain unrun; this is not scientific approval or universal installation qualification.

Current user entry points: [installation](../../source/getting_started/installation.rst),
[quick start](../../source/getting_started/quick_start.rst),
[FA/coupled inputs](../../source/user_guide/fa_inputs.rst) and
[output interpretation](../../source/user_guide/output_files.rst).
The canonical local rendered entry is `docs/build/html/getting_started/installation.html`.
The intended published URL is `https://meteofrance.github.io/frameit/getting_started/installation.html`;
no claim is made that this unpushed checkout is already deployed there.

## Defects fixed and CI regression protection

- `.github/workflows/docs.yml` now cleans the designated documentation build,
  treats Sphinx warnings as errors and runs `docs/check_publication.py` before
  upload. Python 3.12, `docs/docs-requirements.txt`, package installation and the
  `docs/build/html` upload/deploy responsibilities remain unchanged.
- The standard-library checker inspects public RST, artifact paths/text, downloaded
  sources/search and decompressed inventory for known FA history namespaces/routes
  and roadmap references. It does not ban arbitrary C0/C1/C2/P1 data tokens or
  waive whole directories. Two compact regression tests cover legitimate native
  IDs/smoothness and rejected includes, stale orphan pages, copied notices, search
  and inventory entries. No dependency or publishing framework is added.
- Optional matrix/README guidance now distinguishes an installed complete frozen
  fixture from a fresh Git checkout, which tracks its manifest but not ignored
  GRIB/NetCDF payloads. Package-data declarations do not guarantee payload presence
  in every build. Ordinary processing and schema-only checks need no such fixture.
- Five obsolete `tests/test_*.py` descriptions in matrix/polar guidance now identify
  existing files in the packaged numerical suite. No test/package/catalogue name,
  scientific method, equation, bound or data value is changed.

## Environments actually observed

Documentation CI-version packages locally use `/tmp/opencode/frameit-hpc-venv`:
Python **3.13.16**, FrameIt **1.1.0**, Sphinx **8.1.3**, RTD theme **3.1.0**,
pytest **9.1.1**, Ruff **0.17.1**. This is not a Python-3.12 CI run.

Installed reference walkthroughs activate the existing `build/unified-final-verified`
prefix using `"$CONDA_EXE" run --no-capture-output -p "$PWD/build/unified-final-verified"`.
Its Python is **3.13.18**, with EPyGrAM **2.1.0**, falfilfa4py **1.2.1**,
ctypesForFortran **1.3.0**, ecTrans **1.6.0**, netCDF4 **1.7.2**, h5py **3.16.0**,
Python ecCodes **2.44.0**, ESMPy **8.9.1**, xESMF **0.9.2**, Sphinx **9.2.0**
and pytest **9.1.1**. FrameIt imports this checkout; netCDF4/h5py/ecCodes report
Conda ownership. `python -m pip check` reports `No broken requirements found`.
Package metadata alone is not native/scientific qualification.

The creation/activation instructions match unchanged `environment.yaml`:
Python 3.13, one editable `.[test,grib,polar,fa]` installation, active-interpreter
isolated FA workers and optional explicit override. No fresh solve/create/install
was attempted because downloads were excluded. The existing prefix is reused,
not presented as a fresh installation or a second required environment.

## Fresh strict artifacts and complete inspection

All designated outputs were checked absent before creation. `/tmp` was full;
`TMPDIR` points to ignored `build/`, with unrelated temporary work preserved.
The final prescribed strict command exited **0 without warnings**:

```sh
FRESH_DOCS_OUTPUT="$PWD/build/docs-final-acceptance-reviewed-20261028"
PATH="/tmp/opencode/frameit-hpc-venv/bin:$PATH" TMPDIR="$PWD/build" \
  LC_ALL=C LANG=C sphinx-build -q -W --keep-going -b html docs/source "$FRESH_DOCS_OUTPUT"
/tmp/opencode/frameit-hpc-venv/bin/python docs/check_publication.py "$FRESH_DOCS_OUTPUT"
```

Local `make -C docs clean` was **unavailable** (`make: command not found`), so
GNU make/hosted job success is not claimed. With `docs/build` absent, the exact
Sphinx make-mode backend used by the repository Makefile built the canonical
upload boundary, exiting **0 without warnings**:

```sh
PATH="/tmp/opencode/frameit-hpc-venv/bin:$PATH" TMPDIR="$PWD/build" LC_ALL=C LANG=C \
  sphinx-build -M html docs/source docs/build -q -W --keep-going
/tmp/opencode/frameit-hpc-venv/bin/python docs/check_publication.py docs/build/html
```

The reference Sphinx 9.2.0 build also exited **0 without warnings** in a new directory:

```sh
TMPDIR="$PWD/build" LC_ALL=C LANG=C "$CONDA_EXE" run --no-capture-output \
  -p "$PWD/build/unified-final-verified" sphinx-build -q -W --keep-going -b html \
  docs/source build/docs-reference-acceptance-20261028
"$CONDA_EXE" run --no-capture-output -p "$PWD/build/unified-final-verified" \
  python docs/check_publication.py build/docs-reference-acceptance-20261028
```

Task-local full-artifact/evidence inspection passed:

```sh
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python build/audit_final_documentation.py \
  build/docs-final-acceptance-reviewed-20261028 docs/build/html build/docs-reference-acceptance-20261028
```

For **each** artifact: **31 HTML pages**, **29** source documents with matching
search names/titles and rendered H1s, byte-identical downloaded RST, and **2205**
local link/asset/anchor checks pass. These are link occurrences, not distinct URLs.
Navigation, page text, source downloads, `searchindex.js`, inventory and expected
method anchors were inspected. There are no unexpected HTML pages, removed stage
URLs/stubs/redirects, raw stage catalogue includes, developer records or generated
FA viewcode/autodoc leaks. Legacy artifacts were not reused or cleaned with `-E/-a`.

All five remaining source lines with whole C0/C1/C2 matches have explicit native
type or quintic smoothness meanings. Original SFX.TG1P1/WG1P1 identities, hybrid/
Fourier/Snyder meaning, masks, source units/time/signs and numerical bounds remain
visible. No blanket token/directory waiver hides matches. **25** tracked public
README/release/example/install/template/preset surfaces and **12** current CLI
help surfaces are roadmap-free. All affected local public/maintainer links resolve.

Fourteen complete archived pages plus `entry_points_history.md` are unchanged
from the evidence-freeze commit `35837df`. Catalogue assets retain their original
bytes/names against application baseline `9b11d60`. Archived relative RST links,
include targets and developer-index paths resolve; the maintainer can locate
original references/equations, failed attempts, raw dependency/verification ledgers
and unresolved evidence without publishing them.

## Bounded installed user journey and independent readers

The task-local driver creates only a two-time **17x17 synthetic NetCDF** fixture,
uses the installed CLI and preserves inputs. It initializes a Meso-NH fixed-box
configuration, explicitly selects one scalar, sets a 20-km crop, disables polar,
uses one worker/native thread and fresh owned output roots. Exact commands/stdout/
stderr are retained in its ignored `commands.log`, not this public documentation.

```sh
TMPDIR="$PWD/build" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$CONDA_EXE" run --no-capture-output -p "$PWD/build/unified-final-verified" \
  python build/walk_documented_journey.py
```

The final fresh run under `build/acceptance-journey-verified-20261028` passes:
`--help`, explicit input inspection, `init`, source/product selection, schema-only
validation, metadata preflight, dry-run, synchronous run and completion checks.
Preview creates no products. An ordinary fresh process imports netCDF4/NumPy,
**not FrameIt**, and verifies exact prescribed scalar values, retained NaN versus
valid zero, K units, dimensions and CF/package/product/group metadata. Only the
selected Cartesian scalar plus track are written; available winds/MSLP do not
enable unrequested products. Source bytes remain unchanged.

Expected failures pass: reusing the output root with `--no-overwrite` exits 1
without changing prior final status; ordinary loading of legacy flat YAML exits 1
with the migration instruction. `config migrate ... --launch-directory ...`
preserves declared units/lengths, inventory pattern/native selection and launch-
relative paths; migrated schema/preflight/preview pass without running another
simulation. A one-case plan against an owned empty CI-fixture directory exits 2
with `CI fixture manifest is absent`; it runs no matrix case and downloads nothing.

Default-interpreter isolation/normal native shutdown is independently checked by
the existing compact generated GRIB/SURFEX tests (both synchronous and spawn):

```sh
TMPDIR="$PWD/build" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$CONDA_EXE" run --no-capture-output -p "$PWD/build/unified-final-verified" \
  python -m pytest -q src/frameit/testing/numerical/test_fa_environment.py \
  --basetemp build/acceptance-fa-tests-20261028 -o cache_dir=build/acceptance-fa-pytest-cache-20261028
```

**2 passed in 18.74 s**, no skips. They observe actual FA worker launches through
the same `sys.executable` without an override, keep native FA out of the parent,
reopen products in ordinary readers against prescribed values/masks/indices,
check moving/exact shared coordinates/provenance/replay/source bytes, and require
the outer process to exit normally. This is bounded generated-fixture engine/
isolation evidence, not real-producer science or production-throughput validation.

## Relevant tests, lint and implementation invariance

```sh
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m unittest discover -s docs -p test_check_publication.py
/tmp/opencode/frameit-hpc-venv/bin/ruff check --no-cache docs/check_publication.py docs/test_check_publication.py src/frameit/io/fa_contracts.py
TMPDIR="$PWD/build" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /tmp/opencode/frameit-hpc-venv/bin/python -m pytest -q \
  src/frameit/testing/numerical/test_fa_spectral.py::test_spectral_facts_preserve_native_words_without_inventing_dimensions_or_meaning \
  src/frameit/testing/numerical/test_fa_spectral.py::test_selected_spectral_rejected_before_payload_or_library_discovery \
  src/frameit/testing/numerical/test_fa_spectral.py::test_coefficients_cannot_masquerade_as_gridpoint_values \
  src/frameit/testing/numerical/test_fa_contracts.py::test_descriptor_json_unknown_meaning_and_native_fact_precedence \
  --basetemp build/acceptance-boundary-tests-20261028 -o cache_dir=build/acceptance-boundary-pytest-cache-20261028
git diff --check
```

**2 publication tests pass; Ruff passes; 6 existing failure/boundary cases pass
in 0.55 s.** Four FA YAML examples also pass existing `frameit validate PATH
--schema-only` checks: `arome_fa_native_cubes.yaml`, `coupled_arome_fa_polar.yaml`,
`coupled_cyclone_polar.yaml`, `coupled_fa.yaml`. No assertions/tolerances are changed.

Against `9b11d60`, all runtime source changes are confined to the approved
human-readable `SPECTRAL_GATE` explanation; normalizing that constant yields
identical Python ASTs. Configuration, output schemas, scientific defaults,
dependencies, methods, test oracles and native-isolation code remain unchanged.
The equality check is separate from the bounded numerical agreement above;
neither establishes arbitrary real-world validity or bitwise output identity.

Tooling retries are recorded rather than claimed successful: one test-line lint
warning was wrapped before passing; the first journey checker looked for matrix
diagnostics on stderr although they are logged on stdout, then passed after a fresh
corrected walk; the first HTML-title comparison included the theme's heading-link
icon, then passed after ignoring that UI decoration. No application/scientific
expectation was relaxed to obtain these results. Final diff/staged checks and the
focused local commit are reported at handoff.

## Genuine remaining limits

- Hosted GitHub Pages/runtime CI and its Python-3.12 environment were not run or
  claimed passed; local canonical artifact checks use Python 3.13.16. GNU make is
  absent locally, so only its exact Sphinx backend/path was executed here.
- A fresh Conda creation/solve, network installation, other platforms and arbitrary
  future dependency resolutions remain unverified. Activation/reuse of the existing
  coherent prefix is observed, not clean-install evidence.
- No production datasets/runs, full numerical/real-fixture matrix benchmarks,
  external HTTP-link checking, browser visual testing or independent publisher/
  scientific revalidation were performed. Optional fixture payloads are not newly
  committed/downloaded; no private/bulk data or uploads were used.
- Producer-specific field/scaling/units/support/Earth-model/vertical/vector evidence,
  native-error diagnoses, spectral/interval references and required scientific
  review retain their documented gaps. Documentation acceptance is not scientific
  approval, universal reader compatibility or production resource qualification.
