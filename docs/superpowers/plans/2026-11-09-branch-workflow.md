# Branch workflow implementation plan

> **For agentic workers:** Use `executing-plans` to implement this checklist inline.

**Goal:** Replace retired development branches with `develop` and enforce the approved release workflow.

**Architecture:** Keep `main` as the release line and `develop` as the integration line. Use temporary `feature/*` branches, existing GitHub Actions checks, and GitHub branch rules; add no runtime functionality or dependencies.

**Tech stack:** Git, GitHub CLI/rulesets, GitHub Actions, pytest/PyYAML in Python 3.13 `frameit_env`.

**Spec:** The approved design below, confirmed by the maintainer in this conversation on 2026-11-09.

## Approved design and constraints

- Use `feature/* -> develop -> release PR -> main -> tag vX.Y.Z`.
- Create `develop` from the merged `main`; delete retired `dev` and merged `dev_md` locally/remotely where permissions allow.
- Require PRs and successful documentation/runtime CI on `develop` and `main`, with zero required approvals for solo maintenance.
- The maintainer authorizes publishing these changes through a feature PR into `develop`, but no release, tag, or merge into `main`.
- Preserve `ci-fixtures-v1`, unrelated worktrees, and the untracked `opencode.json`.
- Change only agent instructions, active CI references, maintainer notes, and a focused workflow regression test. Historical records retain their original branch names.
- No scientific methods, configurations, outputs, dependencies, or published documentation change.

## Review focus

- Missing admin permission must be reported; never claim that unenforced rules are active.
- A retired branch that has gained new work must not be deleted without rechecking its tip.
- Documentation checks must run for PRs targeting `develop` and `main`; deployment remains main-push-only.
- Required checks must use actual job names and exclude the intentionally skipped PR deployment job.
- Feature PRs target `develop`; release PRs preserve it, and hotfixes must return to it.

## Task 1: Establish the development branch and protection

**Interfaces:** GitHub refs and rulesets; produces `origin/develop` based on current `origin/main`.

- [ ] Verify merged tips, preserve unrelated work, and create local `develop` plus `feature/branch-workflow` from it.
- [ ] Apply PR/no-force-push/no-deletion rules and existing CI contexts to both long-lived branches, with zero approvals; record permission failures.
- [ ] Publish `develop` at the verified main SHA. Recheck and delete `dev_md`; remove retired `dev` and its obsolete rule only with sufficient permission.
- [ ] Verify live refs/rules using `gh api`; inspect local refs with `git branch -avv`.

## Task 2: Update instructions and CI, then publish the feature PR

**Files:** `AGENTS.md`, `.github/workflows/docs.yml`, `docs/development/ci.md`, `docs/test_repository_examples.py`.
**Interfaces:** Existing documentation/runtime workflow events and job names; no runtime API changes.

- [ ] Add `test_documentation_ci_targets_develop_and_main` and `test_documentation_deployment_is_main_push_only` to the existing repository checks.
- [ ] Run the new tests in `frameit_env`; observe the missing-`develop` assertion fail while the deployment guard already passes.
- [ ] Replace active docs workflow/maintainer-note `dev_md` references with `develop`; document the existing required check names.
- [ ] Add agent rules for local feature branches from up-to-date `develop`, focused commits, authorized feature PR publication, release-only main PRs/tags, solo self-review, and hotfix synchronization.
- [ ] Run focused repository/publication tests and review the complete diff. Record `Docs: no user-facing impact because only agent/maintainer policy and CI targeting change`.
- [ ] Commit only task-related files, request a bounded read-only whole-change review, and publish a feature PR into `develop`.
- [ ] Verify hosted checks, merge the approved bootstrap PR if all pass, remove its temporary branch, and leave the checkout on `develop`. If permissions block a step, report the exact remaining action.
