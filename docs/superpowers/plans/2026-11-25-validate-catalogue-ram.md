# Validate Catalogue and RAM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Have full `frameit validate` explain safe metadata repairs and recommend RAM for the same proposed run.

**Architecture:** An optional validation observer retains per-record provenance and checks exact indexed catalogue matches after preflight. A separate estimator uses successful bound plans; existing reports render both without passing advice back to execution.

**Tech Stack:** Python 3.13 in Conda `frameit_env`, stdlib SQLite, LZMA and hashes, existing NumPy/xarray metadata, PyYAML and Textual.

**Spec:** [Validate design](../specs/2026-11-25-validate-catalogue-ram-design.md), supplied `FRAMEIT_VALIDATE_CATALOG_LOOKUP-TABLE.md`, and the packaged release manifest.

## Global Constraints

- Start on the local `develop` fork; finish catalogue work before RAM work, with focused local commits and no push.
- Catalogue release `0.2.0`, format `2`, 56,685 records; trust only the pinned package and preserve all eight row types.
- Only propose `units`, `long_name`, and `standard_name`. Never change native/configuration metadata, `run`/`inspect` behavior or validation clearance.
- No new dependencies, config keys, payload reads, remote calls, or report-envelope/version changes.
- Run tests as `conda run --no-capture-output -n frameit_env env PYTHONPATH=src python -m pytest ...`; build and check published documentation for both commits.

## Review Focus

- Unknown or contradictory per-file producer evidence cannot yield a shared YAML repair (Task 2).
- An otherwise eligible value cannot be proposed if the actual unit consumer rejects it (Task 2).
- Invalid hashes, row types or IDs and a corrupt/concurrently written cache cannot replace an original validation error (Tasks 1–2).
- An unknown competing candidate or an existing conflicting unit/CF name cannot be treated as absent (Task 2).
- Native eager decode, output workers and unbound/unknown shapes cannot look like zero memory (Task 3).

### Task 1: Verified catalogue index

**Files:** `src/frameit/core/metadata_catalogue.py`, `src/frameit/catalogue/frameit_metadata_catalogue-0.2.0.{jsonl.xz,manifest.json}`, `pyproject.toml`, `src/frameit/testing/numerical/test_metadata_catalogue.py`.

**Interface:** `open_catalogue()` is a context manager returning an index with `lookup(producer, version, name, namespace=None)` and `header`. It raises `CatalogueError` on optional-assistance failure; the next task owns reporting.

- [ ] Add cold/warm, concurrent, corrupt-cache and malformed-release tests. Assert the published manifest's three hash scopes, `len(rows) == 56685`, lossless nested records, case-sensitive exact `THT`, and `EXPLAIN QUERY PLAN` using `field_lookup`. Test duplicate integer IDs, unknown body types and unsupported format with compact synthetic releases.
- [ ] Run `... pytest -q src/frameit/testing/numerical/test_metadata_catalogue.py` and confirm the index is not implemented.
- [ ] Bundle exactly the verified two assets. Implement streamed JSONL-to-SQLite validation, an out-of-tree cache keyed by content hash and schema, a same-directory temporary build and atomic replacement. Reuse only verified read-only caches with matching release identity. Benchmark cold construction and warm indexed exact queries separately.
- [ ] Rerun the index tests. Include this work in the catalogue integration commit after Task 2 so the assets have a consumer and documentation.

### Task 2: Catalogue advice in validation

**Files:** `src/frameit/core/catalogue_diagnostics.py`, `src/frameit/core/preflight.py`, `src/frameit/core/coupled.py`, `src/frameit/processing/requests.py`, `src/frameit/core/reports.py`, `src/frameit/utils/diagnostics.py`, `src/frameit/testing/numerical/test_validate_catalogue.py`, and the configuration/troubleshooting docs.

**Interface:** `CatalogueAdvice` is created only by normal `collect_preflight(command="validate")`. It observes per-file NetCDF identity, selected records, and existing operation constraints, then adds `facts["metadata_catalogue"]` and existing-format warnings. The pure `propose` resolver accepts indexed candidates, verified context, observed attributes, missing keys, and unit-admission checks.

- [ ] Add tests: verified root Meso-NH 6.0.0 `THT` proposes `K` for a selected conversion and retains its original error; applying the declaration makes both validation and execution accept it. Guard payloads, config/input bytes, exit status and JSON envelope. Cover distinct-file disagreements, unknown version/case, unselected fields, schema-only/offline isolation, and optional catalogue failure. With real catalogue rows test TSERIES vs ZTSERIES, LES, CCLOUD, CROCO `u`/`aice`/`vortuw_nbq`, NEMO `ttrd_totad`/XIOS and AROME reference-only. Test empty competitors, typed flags, and `K` rejected by an incompatible target unit.
- [ ] Run `... pytest -q src/frameit/testing/numerical/test_validate_catalogue.py` and see the absent proposal/resolver fail.
- [ ] Capture evidence at the selected-field boundary, preserving partial inputs even if binding stops. Identify Meso-NH releases from audited native version headers and root from the actual reader, not a vertical selector; require real evidence for other namespaces and bindings. Use existing declaration and unit checks, per-record observations, and safe intersection for one YAML selector. Add `[W1306]` for proposals and `[W1307]` for unavailable assistance; put exact YAML in findings and only a summary in text, full details in JSON.
- [ ] Rerun Tasks 1–2 and the report/regression tests. Build wheel/sdist and check their installed resources offline; build strict docs and inspect their rendered pages. Commit catalogue code, assets, tests and docs.

### Task 3: RAM estimate

**Files:** `src/frameit/core/memory_estimate.py`, `src/frameit/core/preflight.py`, `src/frameit/core/reports.py`, `src/frameit/validate_tui.py`, `src/frameit/testing/numerical/test_validate_memory.py`, and the storage/resources and HPC guides.

**Interface:** `estimate_run_memory(facts)` returns a JSON-safe `data.plan.memory_estimate` with `status`, `estimated_peak_rss_bytes`, `estimated_median_rss_bytes`, `recommended_allocation_bytes` and assumptions/workload components. A shared `memory_summary` renders the additive facts in text and the TUI.

- [ ] Test a compact bound native request (and a payload guard), increasing shapes/workers, synchronous versus spawned export, eager record decode, polar target growth, and an unknown/unbound request. Assert positive `median <= peak < recommendation`, whole-GiB headroom, and no report addition in schema-only/inspect. Exercise JSON, text and terminal overview, including old saved reports.
- [ ] Run `... pytest -q src/frameit/testing/numerical/test_validate_memory.py` and confirm the estimate is absent.
- [ ] Model live memory by phase using bound dimensions/dtypes, available chunk settings, selected times/support, eager readers, active preparation/tracker and polar targets, and worker-count/staging overhead capped by concurrent exports. Use the maximum phase budget and the median of typical phase budgets; round 1.5× estimated peak up to whole GiB. Explain shared RSS, unknown backend costs, unresolved crop extent and why the median is not time-weighted. Return unavailable on missing binding or sizes, not a nominal recommendation.
- [ ] Rerun the focused and full test suites. Compare the estimate with compact actual `run` measurements; do not infer production calibration. Build strict docs, run the publication check, inspect the rendered pages, and commit locally.
