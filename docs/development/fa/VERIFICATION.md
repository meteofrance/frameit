# Inventory/evidence-freeze verification

Date: 2026-10-28. Application baseline:
`9b11d602c4fb05fb2adf74b699439de6a0b8625b`. Results here belong to this
documentation task; counts in archived pages belong to their original runs.

## Starting work and requirements inspected

`git status --short --branch`, `git diff`, `git diff --cached`, their `--stat`
forms, `git log --oneline -10` and `git ls-files` showed branch `dev_md` ahead
of `origin/dev_md` by 25 commits, no staged/unstaged tracked changes, and existing
untracked `opencode.json`. That unrelated file is excluded from this task.
Root `AGENTS.md` is the only applicable repository instruction file found; no
separate contribution guide was found. Both requested external maintainer plans
were accessible, as was their ordered implementation-prompt companion.

Read README, Sphinx index/configuration, documentation requirements/Makefile,
docs/runtime workflows, package/environment declarations, all frozen source pages,
and the relevant current CLI/schema/FA launch/default/alias code. Existing
environment and migration tests were read as test specifications, not as prior
passing results. No historical suite count was reused as current support.

Documentation CI currently uses Python 3.12, `sphinx==8.1.3` from
`docs/docs-requirements.txt`, `sphinx-rtd-theme`, `pip install .` and
`make -C docs html`, uploading `docs/build/html`. It is not currently a strict
build. `conf.py` gets the release from installed package metadata; enabled
autodoc/autosummary/viewcode extensions do not themselves publish every module.
The reference environment separately declares Sphinx 9.2.0.

## Observed commands and results

Local documentation/check interpreter: `/tmp/opencode/frameit-hpc-venv/bin/python`,
**Python 3.13.16**, installed FrameIt **1.1.0**, Sphinx **8.1.3**, RTD theme
**3.1.0** (queried with `importlib.metadata.version`). The default `/usr/bin/python`
had no FrameIt or Sphinx metadata; no installation/upgrade was performed.

1. CLI observation, exit 0 for both:

   ```sh
   /tmp/opencode/frameit-hpc-venv/bin/python -m frameit --help
   /tmp/opencode/frameit-hpc-venv/bin/python -m frameit inspect --help
   ```

   Normal help contains no roadmap label; `--fa-backend` describes the default
   and deprecated alias, and `--fa-python` is explicitly optional.

2. Existing lightweight schema/replay/default/CLI tests, **7 passed in 0.55 s**:

   ```sh
   OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
   /tmp/opencode/frameit-hpc-venv/bin/python -m pytest -q \
     src/frameit/testing/numerical/test_fa_migration.py::test_old_yaml_acceptance_all_settings_and_resolved_replay \
     src/frameit/testing/numerical/test_fa_migration.py::test_init_and_inspect_use_maintained_default_and_report_legacy_alias \
     --basetemp /tmp/opencode/frameit-docs-freeze-tests-20261028 \
     -o cache_dir=/tmp/opencode/frameit-docs-freeze-pytest-cache-20261028
   ```

   This verifies schema replay, YAML-relative explicit interpreter selection and
   default/alias inspection/template handling. It is not a native reader, numerical
   method, clean-install or native-process teardown qualification.

3. Initial fresh strict public build, exit 0 with no warnings:

   ```sh
   LC_ALL=C LANG=C /tmp/opencode/frameit-hpc-venv/bin/sphinx-build \
     -q -W --keep-going -b html docs/source /tmp/opencode/frameit-docs-inventory-20261028
   ```

   A second fresh build after archive creation, using the same command with output
   `/tmp/opencode/frameit-docs-freeze-20261028`, **failed** copying static assets
   and source downloads with `OSError(28, 'No space left on device')`. It is not
   a successful artifact. `df -h build /tmp/opencode` showed `/tmp` at 100%, versus
   about 1.3 TiB available on the checkout filesystem. Unrelated temporary files
   were preserved. The new retry destination is ignored (`git check-ignore
   build/docs-freeze-20261028`), with existence checked before building:

   ```sh
   TMPDIR="$PWD/build" LC_ALL=C LANG=C \
   /tmp/opencode/frameit-hpc-venv/bin/sphinx-build \
     -q -W --keep-going -b html docs/source build/docs-freeze-20261028
   ```

   **Retry: exit 0, no warnings.** The artifact contains all six original stage
   HTML pages, their `_sources` downloads, search entries and `objects.inv` entries,
   confirming why source removal and a fresh artifact are required in step 3/5.
   These are observed outstanding cleanup items, not final-publication acceptance.
   No frozen developer record or notice is present anywhere in the fresh public
   HTML/JS/text artifact, and no FA contracts/adapter viewcode page was generated.

4. A one-off assertion check is run with:

   ```sh
   /tmp/opencode/frameit-hpc-venv/bin/python /tmp/opencode/check_frameit_docs_freeze.py
   ```

   It compares all fourteen full pages against `git show <baseline>:<old-path>`
   after **only** the notice and exact Sphinx-to-relative-link substitutions;
   compares five literal excerpts from four source files byte-for-byte; resolves
   local index/archive links, RST anchors and include targets; verifies the tracked
   diff is confined here; and inspects the fresh HTML/source/search/inventory for
   the expected baseline publication and absence of these frozen copies.

   **Passed:** all 14 complete bodies, all five excerpts, **125** local links,
   RST anchors and include targets; the tracked-change boundary; and the artifact
   observations above. A preliminary link pass stopped before this verification
   file existed; the completed archive passed the rerun. The checker is temporary
   task tooling, not a new package/CI requirement or an archival framework.

   The full-body comparison can also be reproduced from the checkout without
   retaining the temporary checker (standard library only):

   ```sh
   python -c '
   import re, subprocess
   from pathlib import Path
   base = "9b11d602c4fb05fb2adf74b699439de6a0b8625b"
   root = Path("docs/development/fa")
   names = [f"fa_epygram_c{i}" for i in range(6)]
   mixed = ["fa_baseline", "fa_contracts", "fa_geometry", "fa_surface",
            "fa_spectral", "fa_atmosphere", "fa_environment", "fa_inputs"]
   destinations = {n: n + ".rst" for n in names}
   destinations.update({n: n + "_history.rst" for n in mixed})
   for name, destination in destinations.items():
       old = subprocess.check_output(
           ["git", "show", f"{base}:docs/source/user_guide/{name}.rst"], text=True)
       old = re.sub(r":doc:`([^`]+)`", lambda m:
                    f"`{m[1]} <{destinations[m[1]]}>`_", old)
       old = old.replace(":ref:`fa-geometry-method`",
           "`fa-geometry-method <fa_inputs_history.rst#fa-geometry-method>`_")
       notice, body = (root / destination).read_text().split("\n\n", 2)[1:]
       assert f"Frozen developer evidence from {base}." in notice
       assert body == old, destination
   print("14 frozen page bodies preserved")
   '
   ```

5. Inventory used contextual content searches for `P0`–`P7`, `C0`–`C5`,
   `fa_epygram_c*`, `fa_p*`/`fa_c*`, roadmap/increment/stage/phase meanings and
   Sphinx include/autodoc/source routes. An attempted `rg --count` command was
   unavailable (`rg: command not found`); dedicated searches plus candidate-line
   reporting in the one-off checker cover the finite tracked public surfaces.
   [The map](CONTENT_MAP.md) records both actionable references and legitimate
   native IDs/type codes/mathematical terms. No replacement was applied.

6. `git diff --check` passed during creation. Final review covers
   `git diff --cached --check`, `git diff --cached --stat`, the new index/map/check
   record diff and archive-equivalence assertions. The local commit ID is reported
   at handoff; all 18 task files are in `docs/development/fa/`. No pre-existing
   tracked file or catalogue is changed; `opencode.json` remains untracked.

## Limits and handoff

The complete public cleanup is intentionally pending the assigned steps: six
public stage pages, public stage references and included ledgers still exist.
Their removal is scheduled in [CONTENT_MAP.md](CONTENT_MAP.md), not waived.
The index and archives are outside the Sphinx tree and must never gain public
inbound links/includes or be copied into the deployment artifact.

Hosted Pages/runtime CI, Python 3.12 docs, reference Sphinx 9.2.0, fresh Conda
creation, native lifetime/full numerical suites, external link fetching and
publisher/scientific reference revalidation were not run for this freeze. The
scientific evidence gaps retained in the records require their own producer and
maintainer review. No production source, configuration meaning, output schema,
dependency, catalogue, example setting or method is changed.

Next: step 2, the current installation and user-journey rewrite. Later tasks must
reinspect source and this baseline's subsequent diffs before asserting support.
