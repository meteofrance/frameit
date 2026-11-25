# Terminal Report Responsiveness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this inline follow-up. Steps use checkbox syntax for tracking.

**Goal:** Keep the brand moving during real metadata reads and avoid redundant Inspect table work.

**Architecture:** Textual still owns the report lifecycle. Its existing worker calls a private, reusable spawned child for live read-only preflight and projection. Local presentation reuses cached Textual visuals and only rebuilds rows for a changed search result.

**Tech Stack:** Python 3.13 in `frameit_env`, Textual 8.2.8+, standard-library multiprocessing, pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-terminal-responsiveness-design.md`

## Global Constraints

- One operation at a time. Cancel cooperatively and preserve completed versus cancelled outcomes.
- No new flags, dependencies, scientific methods, backend parallelism, report keys, exit codes or changes to non-interactive and historical reports.
- No production processing, downloads, push, merge, or full-suite rerun.

## Review Focus

- Child check blocked in native code: keep painting and accept Ctrl+C, then wait for the owned operation.
- Helper exit or failure: do not report completion; retry can launch another child.
- SIGTERM while working, normal quit while idle: restore the TTY and reap the owned helper.
- Supported reader warnings: route the same warning text without leaking native stdout/stderr into the terminal.
- Queued search with duplicate names and a subsequent source refresh: preserve field identity and rebuild when rows or recorded metadata change.

### Task 1: Isolate live checks

**Files:** `src/frameit/report_check.py` (new); `src/frameit/cli.py`, `src/frameit/report_tui.py`, `src/frameit/{inspect,validate}_tui.py`; `src/frameit/testing/numerical/{test_report_process,test_validate_tui}.py`.

**Interfaces:** `collect_projection(collect, notify, is_cancelled) -> dict`; `ReportProcess(collect).read(notify, is_cancelled, warn) -> dict`, `.close()`. Pass `isolate=True` only from the two live TUI builders; retain injected collectors in unit tests and leave saved/non-TTY builders alone.

- [ ] Add a RED regression for child PID reuse, progress, warning text and projection parity. Exercise cancellation at a controlled native boundary, unexpected exit then retry, and clean exit.
- [ ] Use a private `spawn` process and a single duplex pipe. The child reads one request at a time; the wait loop forwards actual progress and warnings, sends cooperative cancellation, and waits for a final outcome. Discard late cancellation before the next request. Suppress native output in the child and keep the terminal restored on shutdown.
- [ ] Reuse `ReportApp`'s guarded worker and elapsed/view restore behavior; share progress throttling with in-thread checks. Exercise a real PTY SIGTERM with the child active.
- [ ] Run the process and motion regressions in `frameit_env`. Confirm schema-only, sampled success, failed validation, warning and exit paths.

### Task 2: Cheaper motion and Inspect search

**Files:** `src/frameit/report_motion.py`, `src/frameit/inspect_tui.py`; `src/frameit/testing/numerical/{test_report_motion,test_inspect_tui}.py`.

- [ ] Add RED tests for elapsed-time frame selection, duplicate-frame skipping and a burst of `Input.Changed` events that ought to rebuild the table at most once.
- [ ] Render cached Textual `Content`, with coalesced colour spans and 48 phases over two seconds. Keep the timer stopped when the logo is hidden or reduced motion is selected.
- [ ] In the search handler, process only the current input value. If the ordered native field identities are unchanged, retain the existing table and field presentation. Still update the search/count hints. Rebuild on source/report changes.
- [ ] Run the affected Inspect/Validate/motion tests.

### Task 3: Verify and hand over

- [ ] Repeat the same real read-only cases (AROME/NEMO, Meso-NH/CROCO and SURFEX) and the synthetic 2,400-row search. Record logo gap, wall time, memory and search timings, including cold and warm checks.
- [ ] Check exact CLI output/status and canonical report parity against `e5e681c`. Verify editor resume, cooperative cancellation, compact mode and reduced motion.
- [ ] Build/check affected documentation, and show actual before/after motion in a live OpenCode preview if connected. Record the owned preview process and URL away from the repo.
- [ ] Review the combined diff, run the focused gate and commit locally.
