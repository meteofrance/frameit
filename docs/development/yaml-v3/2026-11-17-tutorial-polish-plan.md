# Tutorial polish and final reviews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Task 21 explicitly requires separate fresh technical and documentation reviewers.

**Goal:** Resolve the six failures honestly, make the tutorials copyable and visually useful, simplify Reference, then execute Task 21's reviews.

**Architecture:** Reuse the existing request/read/provenance boundaries and analytical generator. Keep the coupled instructional scenario separate from the existing fixtures. Render the same standalone plotting sources inline with Sphinx.

**Tech Stack:** Python 3.13, existing NumPy/xarray/Matplotlib, Sphinx, current browser preview.

**Spec:** `2026-11-17-tutorial-polish-design.md`, the maintainer's request/quantity selection, and Task 21 in `CHECKLIST_FOR_AGENTS.md`.

## Global Constraints

- Work in the existing isolated `feature/yaml-v3` worktree; base `e40998aa001562b98a9a27dde62cd18d4e7e65d4`.
- Use `frameit_env` Python 3.13 and absolute source `PYTHONPATH` for every development/data/test/build command.
- No installations/environment repair, reserved full diagnostic, production/HPC runs, benchmark campaigns, push or merge.
- Preserve scientific quantities, masks, clocks and tolerances; declared instructional signals are not scientific validation.
- Diagnose all six failures against current contracts; do not weaken tests or restore retired behavior just for green output.
- Keep diagrams/plots analytical; retain ordinary-reader and no-overwrite checks.
- Keep each new preview iteration, serve only public HTML, and retain final preview ownership privately.
- Task 21 human acceptance and unavailable qualification evidence cannot be supplied by an agent.

## Review Focus

- Native copies with unused wind declarations must retain original values and basis metadata.
- Partial Meso-NH projection declarations must use selected source geometry and record actual overrides.
- Mixed per-file scientific definitions must fail actionably rather than merge under one misleading label.
- Copy-pasted plotting snippets must work without checkout/private paths and refuse overwrites.
- Circular and coupled figures must retain units, clocks, basis, missingness and honest instructional labels.

## Task 1: Classify and resolve the six failures

**Files:** `src/frameit/testing/numerical/test_wind_preflight.py`, `test_multifield_vortex.py`; connected Meso-NH metadata/tracker/operation/provenance code discovered by tracing callers.

**Interfaces:** keep the existing selected-source pool, `selected_mnh_metadata()`, tracker support and execution/provenance APIs.

- [x] Reproduce the exact six failures plus neighboring passing parameter cases; record each expected behavior and its contract evidence.
- [x] For real defects, add/extend minimal read-through/provenance regressions and observe RED before changing shared code.
- [x] For obsolete assertions, retain equivalent current-contract coverage: unchanged native values/metadata; declared conversions; actionable incompatible-definition rejection.
- [x] Apply only the shared root-cause fixes; run the complete two failing modules and connected source-binding/operation tests unfiltered.

## Task 2: Copyable tutorials and revised analytical figures

**Files:** `src/frameit/testing/documentation_example.py`, `test_task_fixtures.py`, `test_documentation_example.py`, `docs/test_tutorials.py`, `example/tutorials/coupled-inputs.yaml`, `example/plots/plot_*.py`, affected task guides and analytical-input reference.

**Interfaces:** retain `create_task_fixtures(Path) -> dict[str, Path]`; add dedicated coupled input paths. Existing fixture formulas/times stay unchanged. The coupled plot consumes both independent exported products.

- [x] Add RED tests for three coupled times, fixed geography, moving air temperature/wind and a persistent SST trail; independently check known values/units and masks.
- [x] Generate dedicated coupled fixtures with explicit formula metadata; select the 10 m height by values/units.
- [x] Make moving-region ticks sparse and one-decimal. Render polar fields on circular axes with north-zero/clockwise angles; preserve the plotted physical quantity.
- [x] Produce the coupled 2×3 plot with row-shared scales, wind arrows/key, actual timestamps and matched geographical limits.
- [x] Show minimal plotting source inline on every task; retain optional download links only beside visible code. Remove fixture-generation adaptation text.
- [x] Execute all copied snippets on generated inputs, test explicit-suffix/no-overwrite behavior and inspect plotting axes/values. Generate fresh analytical SVGs.

## Task 3: Plain Reference and complete documentation verification

**Files:** published Reference pages and their canonical linked configuration/output/input/method pages; CLI/example/caption text only where needed for consistency.

**Interfaces:** preserve public keys, defaults, scientific meanings, anchors and reader requirements.

- [x] Inventory every Reference destination and read it, not a sentence-score sample.
- [x] Lead with the rule/example; remove repetition and implementation narration while preserving consequential assumptions/limits.
- [x] Run strict Sphinx/publication and connected documentation checks in a new iteration; inspect changed pages at1280/320px, every figure's drawing bounds, tabs and no-JavaScript fallback.

## Task 4: Task 21 whole-branch reviews and handover

**Files:** `docs/development/yaml-v3/STATE.md`, this plan, private review inventory/reports/handover; fixes only where review demonstrates a defect.

**Interfaces:** review the entire branch from its recorded baseline, not just this task's diff. Complete documentation review includes README, published pages, CLI help/errors, canonical examples, captions and alternative text.

- [x] Freeze a revision/evidence inventory after Tasks 1–3; dispatch fresh independent technical and full-documentation reviewers.
- [x] Reproduce accepted findings, fix them with focused tests, and have the original reviewers verify closure as Task 21 requires.
- [x] Run affected tests and final strict/publication/rendered checks against the final revision; record skipped/unavailable gates.
- [x] Commit focused task changes locally, preserve unrelated work, and record exact commit IDs and preview restart details.
- [x] Hand over the documented human walkthrough request; leave Task 21 blocked where observations or qualification evidence are missing.

Final review notes: original T1–T4 and D1–D11 are closed by their respective
reviewers. Follow-up T3-R1 and N1 were also reproduced/corrected and independently
closed. Expanded source checks remain1462 passes/19 baseline-reproduced failures;
the final connected lifecycle follow-up passes266 tests. No full/installed or
human acceptance is inferred. The original incompatible W-value catalogue stays
invalid rather than receiving substituted selectors or scientific values.

Local delivery: runtime/guidance `3a3d3ff611533f3b54400fe98a724f2c7d58afbe`;
tutorials/Reference `def3c6a79110af9c2e072369cd2b576f36897a49`. The internal
closure-record commit accompanies this plan; its ID and preview ownership/restart
details are retained in the private session handover.

Maintainer request for handover: report actual observations for sparse times and a
singleton level,another physical source,polar-only output,reopening a product and
repairing an error. Preparing this request is not human acceptance; the main
Task21 human-observations checkbox remains unchecked.
