# Documentation publication

The documentation workflow builds `main` and `develop` with each branch's own
package and Sphinx requirements on Python 3.13. Stable pages keep the existing
site root; development pages live under `develop/`. The existing RTD theme shows
links to each version's home page, and development pages warn that their content
is unreleased. Leave `FRAMEIT_DOCS_CHANNEL` unset for standalone local builds.

Pushes to either branch, and manual runs on either branch, resolve current source
revisions after entering one shared publication queue. Active publications are
not cancelled. Both HTML trees must build and pass checks before a single
complete Pages artifact is uploaded. The Actions summary records both revisions.
Failed builds/checks leave the live site untouched.

Pull requests targeting `main` build the proposed merge revision plus the
development tip, but cannot upload a Pages artifact or deploy. Only the deploy
job requests Pages/OIDC write permission. Runtime CI, scientific processing,
package versions and output contracts are not changed.

## Local checks

Use Python 3.13 in `frameit_env`. When using a shared editable environment,
verify the source import and installed distribution version for each branch;
use absolute source paths and separate scratch package targets, not another
Conda environment or a replacement shared editable installation.

Build main with `FRAMEIT_DOCS_CHANNEL=main` at the preview root, and develop
with `FRAMEIT_DOCS_CHANNEL=develop` under its `develop/` subdirectory. Use strict
Sphinx (`-q -W --keep-going`) with each branch's declared requirements. Run
`python -m unittest discover -s docs -p test_doc_versions.py` on both sources.

For the complete HTML, run `python docs/check_doc_versions.py <site-root>`.
Using development's checkout, run
`python docs/check_publication.py <site-root>/develop --site-root <site-root>`,
then `check_local_links` on the whole site. Development-only content/branding
rules apply to development, not old stable pages. Inspect root, nested and
search pages at desktop and 320 px in a loopback preview.

## Approved staged rollout

1. With push authorization, publish development's presentation/checker support
   first, without enabling its new publisher.
2. Publish this selected main documentation change through the explicitly
   authorized docs-only PR route. Do not merge unrelated development work.
   Inspect actual successful candidate checks.
3. Drain queued/active legacy root-only deployment runs before merging the
   main bootstrap. Cancelling hosted runs requires authorization.
4. Merge the authorized PR. The new main workflow can publish both versions;
   verify the actual deployed pages and revision summary.
5. Bring that main change into develop through a local feature branch,
   retaining development content, styling and its existing accessibility
   override. Verify and integrate locally, then push only with authorization.
   Both branch push triggers now refresh the complete site.

Keep feature branches local. Do not change branch protections or the Pages
allowlist as part of this rollout. The first live development documentation
appears after the main bootstrap, avoiding the legacy overwrite transition.

If checks fail, do not bypass them or deploy only one tree. If a faulty complete
site has deployed, obtain authorization to redeploy a retained verified complete
artifact or publish a focused correction. Rerunning the normal publisher resolves
fresh branch tips and does not necessarily recreate an old site's sources.
Never restore the root-only legacy deployer as a rollback shortcut.
