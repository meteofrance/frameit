# Maintainer CI notes

These repository-only notes describe CI operations, not user requirements.

## Versioned documentation publication

`FRAMEIT_DOCS_CHANNEL=main` or `FRAMEIT_DOCS_CHANNEL=develop` enables the
Sphinx version links; development pages also show an unreleased-content warning.
Unset it for standalone HTML without cross-version links.

The publication layout is stable HTML at the existing root and development HTML
under `develop/`. `python docs/check_doc_versions.py <site-root>` checks both
trees and their navigation. For development content, run
`python docs/check_publication.py <site-root>/develop --site-root <site-root>`;
the site-root option changes link resolution, not content/branding policy.
Do not apply development's forbidden-content rules to old stable documentation.

Each `main`/`develop` push or manual run on those branches resolves both source
revisions after entering a single publication queue. Separate jobs install each
branch's own package and documentation requirements on Python 3.13. Both strict
builds must succeed before a combined artifact can be checked/uploaded; active
publications are not cancelled. The Actions summary records both source SHAs.
Failed builds/checks leave the live site untouched.

Pull requests targeting main build the proposed merge revision plus the
development tip but cannot upload a Pages artifact or deploy. Only the deploy
job requests Pages/OIDC write permission. Cross-site local links are checked on
the complete artifact, while development's content/brand checks stay scoped to
the development tree. No runtime/scientific/schema/package changes are included.

### Approved rollout and rollback

1. With separate push authorization, publish the presentation/checker support
   on develop first, without its publisher trigger change.
2. Publish the selected main bootstrap through the explicitly approved docs-only
   PR route, without unrelated develop changes. Inspect actual candidate checks.
3. Drain queued/active legacy root-only deployments before merging that main
   PR. Cancelling hosted runs requires authorization.
4. Verify the new main publication, then bring its docs-only history back into
   develop through a local feature branch. Retain development content, styling
   and accessibility fixes. Verify/integrate locally, then push only when
   authorized. Both branch push triggers can now refresh the complete site.

Keep feature branches local. No Pages allowlist or branch-protection changes are
needed. The first live development site appears after the main bootstrap.
This publisher commit is prepared locally until that bootstrap is released.

Use absolute import paths and matching scratch package targets in `frameit_env`
for local checks. Verify installed distribution metadata as well as import
location; ignored egg-info in a reused worktree can contain another branch's
version. Check generated HTML titles against each branch's package version.

If a faulty complete site is deployed, obtain authorization to redeploy a
retained verified complete artifact or publish a focused correction. A normal
rerun resolves fresh branch tips and may not recreate an old site's sources.
Do not restore the root-only legacy workflow as a rollback shortcut.

## Runtime checks (unchanged)

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

Keep build/core checks required in repository branch-protection settings;
a skipped check is not a pass. Run local equivalents in `frameit_env` before
committing. Hosted results require an authorized push and an actual completed job.
