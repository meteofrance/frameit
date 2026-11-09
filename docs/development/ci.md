# Maintainer CI notes

These repository-only notes describe CI operations, not user requirements.

`Documentation / build` runs strict Sphinx and publication/link checks on
`develop`/`main` pushes and pull requests targeting those branches. It uploads
only the public HTML artifact. Pages upload/deployment is restricted to a push
on `main`; candidate branches and pull requests have no Pages write permission.

`Batch runtime / core-batch` checks advertised starter commands, the current
schema and the compact first run on Python 3.13 without GRIB/FA/ESMF dependencies.
Native-stack and full numerical checks remain separate jobs in
`.github/workflows/runtime.yml`. Real-fixture/polar configuration integration
tests remain mandatory in the native full suite, not the core-only job.

The native full job downloads the approved data-only fixture at a pinned commit,
verifies all nine SHA-256 hashes, and sets `FRAMEIT_CI_DATA_ROOT` explicitly.
See `docs/source/user_guide/matrix_testing.rst` for fixture retrieval instructions.
It installs Matplotlib only for downstream illustration tests; plotting is not
a core runtime dependency. The isolated FA job creates its temporary-output
parent before invoking pytest.

## Branch rules and releases

Use `feature/* -> develop -> release PR -> main -> tag vX.Y.Z`. Feature PRs
target `develop`; release PRs merge `develop` into `main` with a merge commit.
Keep both long-lived branches after a release. The separate `ci-fixtures-v1`
branch holds data only and is not part of this merge flow.

Configure GitHub rules for both `develop` and `main` to require PRs, block
force-pushes/deletion, and require these GitHub Actions check names:

- `build` (Documentation)
- `core-batch (3.13)` (Batch runtime)
- `fa-coupling`
- `fa-spectral-candidate`
- `fa-epygram-cubes`

Require branches to be up to date before merging. Zero required approvals is
acceptable for solo maintenance; the maintainer still reviews the diff and
completed CI results. Do not require `deploy`: it intentionally skips PRs and
development pushes. A skipped required check is not a pass.

Changing rules requires repository administration permission. Workflow files and
these notes do not enforce branch protection: inspect the live GitHub rules after
an administrative change. Do not weaken protection to merge or delete a branch.

Run local equivalents in `frameit_env` before committing. Hosted results require
an authorized push and an actual completed job. A release/tag is a separate
maintainer decision, not an automatic consequence of a successful feature PR.
