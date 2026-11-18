# Maintainer CI notes

These repository-only notes describe CI operations, not user requirements.

## Versioned documentation support

`FRAMEIT_DOCS_CHANNEL=main` or `FRAMEIT_DOCS_CHANNEL=develop` enables the
Sphinx version links; development pages also show an unreleased-content warning.
Unset it for standalone HTML without cross-version links.

The publication layout is stable HTML at the existing root and development HTML
under `develop/`. `python docs/check_doc_versions.py <site-root>` checks both
trees and their navigation. For development content, run
`python docs/check_publication.py <site-root>/develop --site-root <site-root>`;
the site-root option changes link resolution, not content/branding policy.
Do not apply development's forbidden-content rules to old stable documentation.

Presentation/checker support is staged separately from the publisher. This
support change does not enable deployments from `develop`. The combined
publisher must first replace the legacy root-only workflow on `main` through
the explicitly approved docs-only PR route, without merging unrelated
development changes. Drain old deployment runs before the combined site goes
live; then integrate that publisher into `develop`. Publishing these steps
requires separate maintainer authorization. Keep feature branches local.

## Current workflow

`Documentation / build` runs strict Sphinx and publication/link checks on
`dev_md`/`main` pushes and pull requests targeting those branches. It uploads
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

Keep build/core checks required in repository branch-protection settings;
a skipped check is not a pass. Run local equivalents in `frameit_env` before
committing. Hosted results require an authorized push and an actual completed job.
