# Remaining public entry points

Documentation step 4, 2026-10-28; starting checkout `0abea33`. Root `AGENTS.md`,
both maintainer plans, the content map, current README/docs/CLI, changelog,
examples, installation comments, templates/presets, documentation configuration
and workflow were inspected. Starting tracked tree was clean; unrelated untracked
`opencode.json` was preserved. The full documentation rework still awaits step 5.

## Changes and scope

- `CHANGELOG.md`: replace unreleased FA stage narratives and superseded admission
  statements with current environment/reader/coupling/cube behavior, compatibility
  and explicit limits. Current topic links replace roadmap dependencies. Actual
  software versions (including Python 3.13, EPyGrAM 2.1.0, ctypesForFortran 1.3.0
  and ecTrans 1.6.0) and field/schema identities retain their meaning. Everything
  from the unrelated wind-method comparison onward, including dated releases and
  meaningful historical software/schema versions, remains unchanged.
- `src/frameit/io/fa_contracts.py::SPECTRAL_GATE`: only the explanation/reference
  changes to “Spectral FA support and limitations in the user guide”. The gated
  failure prefix, encoding-qualified coefficient-contract requirement and
  independent native-grid reference requirement remain exactly the same.
- Developer index/content map: record this audit and the remaining acceptance task.

Before editing the constant, both callers (`native_descriptor` and
`fa_worker._describe`) and existing spectral/contract tests were searched/read.
The worker still rejects selected spectral records before physical reads or
library transform discovery, and the parent still rejects coefficient-shaped
responses. No fallback, numerical method, admission/classification, provenance key,
schema, dependency or test oracle/tolerance changes. Human-readable reason text
in errors/descriptors is the intended compatibility-visible change.

README/example/install references were already cleaned by the preceding tasks;
they need no further edits. Four referenced FA examples were schema-validated
again. Required numerical/scientific distinctions remain in current public topics.
Private module/helper docstrings and implementation comments mentioning P0/C1,
and explicit developer probes/test/catalogue names, remain evidence rather than
ordinary installation/runtime instructions. No current autodoc/viewcode page or
normal CLI path publishes those private descriptions. Actual C0/C1 type codes,
SFX.TG1P1/WG1P1 identities and C2 mathematical smoothness are not replaced.

All fourteen frozen RST records and `entry_points_history.md` are unchanged from
`0abea33`. The original changelog FA passages are already frozen there; no evidence,
citations, failed attempts or raw dependency/verification ledgers are discarded.
Package/test catalogue names and contents remain unchanged.

## Observed checks

Local tools import this checkout's `src/`: Python **3.13.16**, FrameIt **1.1.0**,
pytest **9.1.1**, Ruff **0.17.1**, Sphinx **8.1.3**, RTD theme **3.1.0**. `/tmp`
was full, so fresh designated outputs and `TMPDIR` use ignored `build/`; unrelated
temporary work was not removed. No environment installation/upgrade was performed.

### Existing failure/boundary cases — 6 passed in 0.53 s

```sh
TMPDIR="$PWD/build" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
/tmp/opencode/frameit-hpc-venv/bin/python -m pytest -q \
  src/frameit/testing/numerical/test_fa_spectral.py::test_spectral_facts_preserve_native_words_without_inventing_dimensions_or_meaning \
  src/frameit/testing/numerical/test_fa_spectral.py::test_selected_spectral_rejected_before_payload_or_library_discovery \
  src/frameit/testing/numerical/test_fa_spectral.py::test_coefficients_cannot_masquerade_as_gridpoint_values \
  src/frameit/testing/numerical/test_fa_contracts.py::test_descriptor_json_unknown_meaning_and_native_fact_precedence \
  --basetemp build/entry-point-failure-tests-20261028 \
  -o cache_dir=build/entry-point-pytest-cache-20261028
```

The representation test covers spectral, unknown and blocked-gridpoint transfers.
These are existing synthetic/failure contracts, not new native FA or real-field
qualification. No assertion or numerical bound was weakened or updated.

### Changed-file lint and fresh strict docs — passed

```sh
/tmp/opencode/frameit-hpc-venv/bin/ruff check --no-cache src/frameit/io/fa_contracts.py
TMPDIR="$PWD/build" LC_ALL=C LANG=C \
/tmp/opencode/frameit-hpc-venv/bin/sphinx-build \
  -q -W --keep-going -b html docs/source build/docs-public-entry-points-20261028
git diff --check
```

Ruff reported `All checks passed!`; Sphinx exited 0 without warnings. The output
directory was checked absent before building. Final staged diff checks and the
local commit are reported at handoff.

### Example/schema and visible-string audit — passed

```sh
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/arome_fa_native_cubes.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/coupled_arome_fa_polar.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/coupled_cyclone_polar.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/coupled_fa.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python build/check_public_entry_points.py
```

All four direct validations printed `OK: schema validated`. The task-local
one-off checker (ignored `build/`, not a new package/CI dependency) passed:

- Only `SPECTRAL_GATE` differs in the Python AST; original prefix and both evidence
  requirements remain. Callers, tests and all other runtime code are unchanged.
- Fourteen frozen pages/excerpts and unrelated release/version history are intact.
- **25** tracked README/release/example/install/template/preset text surfaces are
  stage-free; new/existing local Markdown topic links resolve.
- **12** ordinary CLI help surfaces (root, all commands and both config leaves),
  an observed deprecated-native warning and an invalid-backend failure are stage-free.
- Full generated AROME/Meso-NH configurations and their schema-only validations
  pass, using owned temporary files; no dataset or native decoder is opened.
- **29** public RST sources and **31** fresh HTML pages plus search/source downloads/
  inventory exclude removed stage records, catalogue/archive routes and FA viewcode
  re-entry. Public sources are unchanged from the reviewed topic-guide task, retaining
  legitimate native type/field IDs and mathematical conventions.

`conf.py` still builds only `docs/source`; developer records remain outside it.
The workflow still builds `make -C docs html` with Python 3.12 and uploads only
`docs/build/html`. No archive-copy step, orphan suppression or broad source waiver
is added. CI freshness/strictness enforcement and hosted artifact acceptance remain
the final task; local checks do not establish that hosted CI has run.

## Next task and remaining gaps

Step 5: complete publication acceptance against the current checkout and actual
CI artifact contract, including fresh strict build, HTML/navigation, search,
downloaded source, inventory and ordinary CLI/configuration entry paths. The
developer evidence must remain inspectable outside publication.

Hosted/Python-3.12 CI, reference Sphinx 9.2.0, fresh Conda creation, full/native
numerical or lifetime suites, real-data decoding, production runs, browser visual
checks, external link fetching and independent scientific revalidation were not
run. No bulk/private data or uploads were used. Existing producer/scaling/units/
support/Earth-model/spectral evidence gaps remain explicit; passing these wording
and failure-contract checks is not scientific approval.
