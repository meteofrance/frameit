# Checkout version and editable-install refresh

After a Git update, the imported source version and pip's installed metadata
can legitimately differ. `frameit info`, the Python version attribute, and
new run provenance should describe the imported code.

Use the imported module's `src/frameit` layout and its FrameIt
`pyproject.toml` as read-only source evidence. Wheel imports use installed
metadata; the existing final fallback still applies. Resolving from the
launch directory would let an unrelated project change the result.

Only `frameit refresh-install` may refresh metadata. Verify a single pip
editable installation in the active interpreter's site-packages, and match
its `direct_url.json` checkout to the imported source. Use the requested
pip flags and verify the version with a separate `pip show` process.
Automatic reinstalls and direct edits to metadata would hide environment
changes and are outside the workflow.

Use Python 3.13 `frameit_env` for checks. Exercise the installer with
isolated metadata or a disposable test environment.
