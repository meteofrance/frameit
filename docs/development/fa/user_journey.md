# Current user-entry rewrite

Step 2 of the documentation plan, 2026-10-28. Starting checkout: `35837df`
(`9b11d60` application implementation plus the evidence-freeze commit).
Both external maintainer plans, root `AGENTS.md`, the content map, current docs,
YAML/package declarations, CLI/schema/preflight/FA launcher and output writer
were reinspected. Starting tracked tree was clean; untracked `opencode.json`
was preserved. No production code, dependencies, catalogue or example settings
are changed.

## Delivered path and evidence retention

| File | User-facing change |
| --- | --- |
| `README.md` | Installation first, explicit inspect/select/check/run/read workflow, current high-level support and limits; stage history links removed. Citation/attribution and optional numerical-method guidance retained. |
| `docs/source/getting_started/installation.rst` | One reference YAML installs FrameIt plus Python-3.13 FA/GRIB/NetCDF/polar stack; editable ownership, fresh named migration, optional interpreter and core/extras explained. |
| `docs/source/getting_started/quick_start.rst` | Schema-only versus metadata preflight versus execution, explicit selections/CLI precedence, completion and ordinary-reader use. |
| `docs/source/user_guide/input_files.rst` | Deliberate inventory/inspection, actual content-detection/explicit-FA contract, source read-only and independent coupled grids. Existing model/wind references retained. |
| `docs/source/user_guide/fa_environment.rst` | Current environment, worker isolation, override/alias migration, actionable troubleshooting and limits. Experiments/test ledgers remain in `fa_environment_history.rst`; public catalogue include removed. |
| `docs/source/user_guide/fa_inputs.rst` | Current FA/coupling contract with descriptive links, explicit units/time/source/scaling, masks, native cube distinctions, resources/failures and unsupported operations. Geometry method/anchor/equations/tolerances retained. |
| `docs/source/user_guide/configuration_file.rst` | Current named-source/FA keys and defaults, exact-time/shared-target policy, interpreter/alias migration and check scope. Existing numerical/wind/level contracts retained. |
| `docs/source/user_guide/output_files.rst` | Present source/vertical products, descriptors/observations, partial/completed status, ordinary-reader example and actual filename/global-version attribute spelling. Wind equations/figures/anchors retained. |

The output-description corrections follow the current exporter: filename tokens
preserve ASCII alphanumerics plus `._-`, and the global package-version attribute
is `frameit_version`. These are documentation corrections, not writer/schema changes.
All fourteen frozen RST records and `entry_points_history.md` remain byte-for-byte
unchanged from `35837df`; no prior qualification count is reused as a new result.
Package/test catalogues retain their names, contents and machine-readable contracts.

The FA overview's example include starts at `schema_version:`. A parsed-YAML
comparison confirms that excluding the development header changes no settings.
Original YAML comments remain assigned to step 4. No public page links to this
developer record or archive. Neutral page paths and the explicit
`fa-geometry-method` / `wind-grid-contract` anchors remain.

Scientific meaning remains explicit: exact-common default with warnings/full
exclusions and selectable strict times; independent grids/masks/products;
source assertions and missing-scaling failure versus justified explicit fallback;
native labels versus physical coordinates; bilinear point sampling without a
conservation promise; selected-only diagnostics/transformations; native-record
point/time bounds versus peak RSS; per-product atomicity and incomplete status.
Real-producer scientific evidence and review remain unresolved where recorded.

## Observed verification

The active checker imports FrameIt from this checkout's `src/`. Local interpreter:
Python **3.13.16**, FrameIt **1.1.0**, Sphinx **8.1.3**, RTD theme **3.1.0**.
`git status --short --branch`, staged/unstaged diffs and `git log --oneline -10`
were inspected before editing. No environment installation or upgrade was run.
`/tmp` was full, so fresh designated outputs and `TMPDIR` use ignored `build/`;
existing temporary files were left alone.

The initial fresh strict build to `build/docs-user-journey-20261028` exited
**0 with no warnings**. After review and a source-prose reflow, the final fresh
build also exited **0 with no warnings**:

```sh
TMPDIR="$PWD/build" LC_ALL=C LANG=C \
/tmp/opencode/frameit-hpc-venv/bin/sphinx-build \
  -q -W --keep-going -b html docs/source build/docs-user-journey-final-20261028
```

One-off documentation assertions (temporary tooling in ignored `build/`):

```sh
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python build/check_user_journey_docs.py
```

Passed: eight entry sources, seven rendered article bodies and their downloaded
sources contain no roadmap labels, stage-page links or evidence/archive routes;
**120** local article links/anchors and README local links resolve; all affected
inline equations/explicit anchors and the detailed exact-common/strict section
are retained; all fourteen frozen pages plus entry-point evidence are unchanged;
both ordinary-reader snippets compile; the new optional-interpreter YAML fragment
passes schema-only validation when merged into a complete single-source FA config;
and the include projection preserves every parsed example setting. The reader
snippets were not executed against a production product.

Each of these existing example checks exited **0**, printing `OK: schema validated`:

```sh
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/coupled_fa.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/conf_example.yml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/coupled_cyclone_polar.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/coupled_arome_fa_polar.yaml --schema-only
```

Template commands were checked in fresh designated paths; all exited **0**:

```sh
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit init arome --full --output build/docs-user-journey-arome-full.yaml
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate build/docs-user-journey-arome-full.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit init mesonh --output build/docs-user-journey-mesonh.yaml
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate build/docs-user-journey-mesonh.yaml --schema-only
```

`python -m frameit --help` and `python -m frameit config migrate --help` under
that interpreter both exited **0**, confirming the documented migration options.
`git diff --check` passed during review; final staged checks and the local commit
are reported at handoff. No numerical suite, native dataset decode, production
run or download was needed for these documentation-only changes.

## Remaining work and next task

This verifies only the current user-entry rewrite. Global navigation and the six
original stage pages, mixed topic histories and their evidence includes remain
published for step 3; examples/changelog/ordinary spectral error wording remain
owned by step 4. The fresh artifact contains no developer archive pages. Full
HTML/search/source/inventory publication acceptance is still step 5.

Hosted CI (Python 3.12, Sphinx 8.1.3, `make -C docs html` -> `docs/build/html`),
reference Sphinx 9.2.0, fresh Conda creation, native lifetime/numerical suites,
production-reader reopening, external links and scientific-reference revalidation
were not run here. Documentation checks do not constitute scientific approval.

**Next task:** step 3, rewrite the compatibility/metadata/geometry/surface/cube/
spectral topic guides from current behavior, preserve the frozen scientific
evidence, and remove public stage sources/navigation and their affected links.
