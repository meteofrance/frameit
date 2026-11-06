# Maintainer CI notes

These repository-only notes describe CI operations, not user requirements.

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
