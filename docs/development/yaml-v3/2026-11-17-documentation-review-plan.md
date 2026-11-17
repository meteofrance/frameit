# Analytical tutorials and pressure groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the maintainer's documentation review with runnable analytical tutorials and unit-independent pressure-group names.

**Architecture:** Reuse the existing instructional NetCDF generator and ordinary execution API. Normalize producer pressure identifiers at adapter boundaries; retain pressure units and reject ambiguous providers. Use a small, progressively enhanced HTML tab pattern, not another Sphinx dependency.

**Tech Stack:** Python 3.13, NumPy/xarray, existing FrameIt adapters and CLI, Sphinx, Matplotlib, vanilla JavaScript/CSS.

**Spec:** Maintainer review and explicit “Proceed with generated NetCDF” in this session; requirements below capture that instruction, not a separate human design approval.

## Requirements

- FrameIt pressure keys, dimensions and qualified references become `isobaric`; native GRIB identifiers remain only where the external format requires them.
- No real-event names, data descriptions, figures or downloads in published documentation; remove `reference/illustrations`.
- Every task tutorial uses locally generated analytical inputs, offers API/CLI tabs for FrameIt operations, and includes a minimal standalone plotting script and its output figure.
- First task generates all tutorial fixtures through `frameit generate-tests-fixtures`; clearly label them instructional only.
- Comment only task-relevant YAML keys; end each task with a short real-input adaptation section.
- Replace ambiguous “saved” wording with input-dataset terminology.
- Shorten field selection as requested; explain physical versus boundary/halo levels; move roundoff and selection-grid details into Reference.

## Global Constraints

- All development/data/build/test commands use Conda `frameit_env`, Python 3.13.
- No environment installation/repair, production run, source-data modification or external upload.
- Diagnostics remain opt-in; preserve scientific values, units, masks, time selections and interpolation policies.
- No public compatibility alias for the renamed pressure group. Document the new interface in current configuration/output pages.
- Preserve real-case regression fixtures and private scientific evidence; publication removal does not delete source data.
- Do not run the reserved whole-branch diagnostic or a benchmark campaign.
- Use compact end-to-end checks, strict Sphinx/publication checks and live desktop/narrow GUI review.
- One fresh bounded review before local focused commits; never push or merge.

## Review Focus

- GRIB pressure in Pa versus hPa: retain units and values; no accidental pressure scaling or provider merging.
- Existing output directories: fixture/plot commands must refuse overwriting unrelated data.
- Copied tutorial scripts: paths must resolve without a developer checkout or private dataset.
- Disabled JavaScript and keyboard navigation: both code alternatives stay readable, enhanced tabs remain accessible.
- Publication artifacts: removed data/figures must not survive as orphan `_static` or downloadable files.

---

### Task 1: Canonical pressure group

**Files:** pressure adapters/preflight/readers, connected trackers/exporters/catalogue/templates, `src/frameit/testing/numerical/test_isobaric_group.py`, affected existing tests and examples.

**Interfaces:** native `typeOfLevel` remains an external locator; all admitted FrameIt pressure groups/dimensions use `isobaric`, with coordinate units carrying Pa/hPa.

- [x] Add real compact GRIB and NetCDF regressions for inspected/requested/exported `isobaric`, pressure-unit selection and native decoder locators; run RED.
- [x] Normalize at existing adapter boundaries and update every active consumer, test expectation, configuration and output description without changing field payloads or tolerances.
- [x] Run new regressions plus connected grouped/GRIB/FA/tracker/export tests; investigate failures before changing expectations.

### Task 2: Generate all instructional inputs

**Files:** `src/frameit/testing/documentation_example.py`, `src/frameit/cli.py`, `src/frameit/testing/numerical/test_documentation_example.py`, tutorial YAML under `example/tutorials`.

**Interfaces:** `create_task_fixtures(directory: Path) -> dict[str, Path]`; CLI `frameit generate-tests-fixtures --output tutorial-data` calls it. Existing generator APIs remain usable.

- [x] Test CLI/API fixture generation, declared dimensions/units/masks, ordinary reader reopening and no-overwrite behavior; run RED.
- [x] Reuse existing analytical formulas for stationary, translating, missing and interface examples; add only the small fields/coordinates required by field selection.
- [x] Run generator/CLI tests and execute compact tutorial configurations with diagnostics explicitly selected only where taught.

### Task 3: Concise analytical tutorials and equivalent API/CLI

**Files:** `docs/source/task_guides/*.rst`, new fixture-first guide, `example/tutorials/*.yaml`, `example/plots/*`, `docs/source/_static`, `docs/source/conf.py`, `docs/test_tutorials.py`.

**Interfaces:** tutorials consume Task 2's stable paths; plotting scripts use xarray/Matplotlib without importing FrameIt; figures show actual generated outputs.

- [x] Add end-to-end tutorial/plot checks exercising generated datasets and output metadata/values; run RED for missing configurations/scripts.
- [x] Rewrite all task guides around concise complete requests with focused YAML comments, API/CLI operation tabs, output interpretation and one short final real-input section.
- [x] Keep mathematical/selection details in a Reference page, with task links instead of duplicated exposition.
- [x] Add dependency-free accessible tabs with readable no-JavaScript fallback; verify keyboard interaction in the live browser.
- [x] Generate tutorial figures from actual outputs, never from private/real producer data.

### Task 4: Publication cleanup

**Files:** real-case sections throughout `docs/source`, reference navigation, obsolete source figures/download links, `docs/check_publication.py`, `docs/test_check_publication.py`, affected documentation tests.

**Interfaces:** only instructional/analytical figures and examples enter the published HTML/download/static tree.

- [x] Add a publication regression rejecting real-case text/assets in the rendered artifact; run RED.
- [x] Delete the illustrations page and real-data figure assets, remove references/downloads, retain unrelated regression data, and replace “saved” wording where it means input levels.
- [x] Run strict Sphinx and publication checks plus affected documentation/example tests; inspect changed rendered pages at desktop and 320px.

### Task 5: Review and handover

- [x] Review the complete diff and execute the connected tests unfiltered within the authorized resource scope; record exact results and unavailable checks.
- [x] Obtain one fresh bounded code/documentation review; address important findings in one verified fix pass.
- [x] Assess docs impact, stage only task-related files, and create focused local commits after verification/review.
- [x] Keep the owned loopback preview available; hand over URL/server restart command, commit IDs, compatibility impact and remaining limitations.

## Verification outcome

The scoped review-fix suite passes55 tests and40 subtests. The final unfiltered
reader/group/tracker lane has684 passes and six failures matching independently
reproduced baseline node IDs. Wider connected checks retain29 confirmed baseline
failures in total; no green whole-suite claim is made.

Strict Sphinx/publication iteration05, desktop/narrow GUI checks and rebuilt
plot downloads pass. No introduced Ruff diagnostic remains. See `STATE.md`
for the scoped result and this session's private handover for exact commands,
review closure, local commit ID and retained preview ownership.
