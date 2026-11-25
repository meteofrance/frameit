# Validation Guide and RC4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show readers where to find estimated RAM, check the estimate on real inputs, and integrate a verified `2.0.0rc4`.

**Architecture:** Keep the existing TUI, CLI and 1.5× headroom policy. Capture the TUI from the public tutorial and compare validation and execution with identical bounded pilot configurations.

**Tech Stack:** Sphinx, Textual, Linux process RSS, Git, Python 3.13 `frameit_env`.

**Spec:** [Validation guide and 2.0.0rc4 check](../specs/2026-11-25-rc4-validation-handoff-design.md).

## Global Constraints

- Keep all original data read-only; keep real paths and products out of Git.
- Use one selected native time/field, one CPU, synchronous export per pilot.
- Verify before merging. Push only `develop`, not the local tag or feature branch.

## Review Focus

- The screenshot must show the actual RAM section, not imply that it measures a run.
- Removing the progress section must not leave broken documentation references.
- The five pilot measurements must compare the same estimate and actual workload.
- The full suite must use the approved fixture with checked hashes, not substitutes.
- The tag must name the verified versioned commit; publication is branch-only.

### Task 1: TUI-first storage guide

- [ ] Capture Textual's Overview from `example/tutorials/storage-and-resources.yaml` and the generated fixture. Keep the screenshot, alt text and the capture recipe.
- [ ] Edit `docs/source/task_guides/storage_and_resources.rst` and fix the affected HPC and troubleshooting references. Remove the four requested sections; show the interactive command, the RAM overview, and then the CLI alternative.
- [ ] Run strict Sphinx and `docs/check_publication.py`. Inspect the rendered guide and links in OpenCode at desktop width and 320 px. Commit the docs together.

### Task 2: Native-input RSS checks

- [ ] For each requested family, confirm a native field, units, and first time from local headers. Keep the exact YAML, output and logs in fresh scratch paths.
- [ ] Run `frameit validate --json`, then run the identical request and sample local process-tree RSS. Verify success and output metadata. Record estimated and sampled peak/median and recommended allocation in the internal design notes.
- [ ] Investigate estimates below the measured peak. Do not tune the margin to these measurements or claim production validation.

### Task 3: RC4, verification and integration

- [ ] Update package, fallback and citation versions, changelog and `docs/test_release.py`. Verify the release test and installable artifacts.
- [ ] Export `ci-fixtures-v1` into scratch, verify `SHA256SUMS` and use `FRAMEIT_CI_DATA_ROOT` for the complete pytest suite in `frameit_env`. Run strict docs/publication checks on the final candidate.
- [ ] Commit locally. Confirm clean/up-to-date `develop`, verify the merged tree, tag `v2.0.0rc4` there and push `refs/heads/develop` only. Verify local tag and remote branch SHAs.
