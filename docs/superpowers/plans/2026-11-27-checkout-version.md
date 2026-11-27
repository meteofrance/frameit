# Checkout Version Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Report the imported code's version and offer an explicit pip metadata refresh.

**Architecture:** Resolve source identity once through `frameit._version`.
Keep installation verification and pip calls on the explicit command path.

**Tech Stack:** Python 3.13, tomllib, importlib.metadata, pip, pytest, Sphinx.

**Spec:** `docs/superpowers/specs/2026-11-27-checkout-version-design.md`

## Global Constraints

- Base the topic branch on `develop`; commit locally.
- Use Python 3.13 `frameit_env` for checks.
- Exercise the installer with isolated metadata or a disposable test environment.

## Review Focus

- Stale installed and source-tree metadata disagree with the live checkout.
- The launch directory contains a different `pyproject.toml`.
- Installed metadata is ambiguous or points to another checkout.
- pip fails, or succeeds without updating the version reported by `pip show`.

### Task 1: Read-only version resolution

**Files:** `src/frameit/_version.py`, `src/frameit/cli.py`,
`docs/test_release.py`, and `src/frameit/testing/numerical/test_hpc_execution.py`.

- [ ] Test checkout `rc4` with installed `rc2`, the unrelated-directory CLI
  output, runtime provenance, and wheel metadata and fallback.
- [ ] Run the release and CLI info tests and observe the stale-version failure.
- [ ] Implement `source_project() -> tuple[Path, str] | None` and use
  `frameit.__version__` in the CLI. Rerun the tests.

### Task 2: Explicit installer refresh

**Files:** `src/frameit/_install.py`, `src/frameit/cli.py`,
`src/frameit/testing/numerical/test_refresh_install.py`, and the installation guide.

- [ ] Test the CLI using real `direct_url.json` fixtures and a controlled pip
  boundary: commands, guard failures, pip errors, and version confirmation.
- [ ] Run `test_refresh_install.py` and observe that the command is missing.
- [ ] Implement `refresh_editable_install() -> str` and wire the CLI command.
- [ ] Run the focused tests and verify strict Sphinx, publication, and the
  rendered installation page. Review and commit the change.
