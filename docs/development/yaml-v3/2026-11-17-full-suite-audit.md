# Full-suite stale-test audit — 17 November 2026

Internal evidence, not published user guidance or scientific qualification.

## Scope and result

The maintainer requested session compaction, an audit for demonstrably obsolete
tests, replacement/removal of those expectations, and a final unfiltered suite.
The starting revision was `5e76be1ba8d69d5e7daba5884858ec710ed89c24`, with a
clean tracked worktree/index.

Only fifteen test modules changed. No production code, dependency, collection
rule, public configuration, output schema, numerical method or default changed.
No skips or xfails were added. Scientific regression payloads, analytical field
truths and existing numerical tolerances were not rewritten.

| Run | Passed | Failed | Skipped | Passing subtests | Warnings | Time |
|---|---:|---:|---:|---:|---:|---:|
| Unfiltered starting baseline | 3128 | 81 | 0 | 4 | 9646 | 1424.71 s |
| Final unfiltered suite | **3184** | **26** | **0** | **4** | **9711** | **1474.33 s** |

Both runs exit 1. The suite is **not green**. The final failing-node set is a
subset of the baseline failing-node set; there are no newly failing node IDs.
This does not mean every primary diagnostic is unchanged: repairing track units
exposed FA merge failures, and restoring documented CROCO provenance coverage
exposed the missing record behind an obsolete target-ID assertion.

Collection increased from 3209 to 3210 ordinary tests because of one additional
positive consistent-unit numerical case. XML totals include four passing
subtests, giving 3213/3214 cases respectively.

## Disposition of obsolete expectations

The authorities are current C1–C9, canonical configuration/time/output/ocean/FA
guidance, and connected implementation—not test age or a failure alone.

| Old assumption | Replacement and retained coverage |
|---|---|
| All native FA cubes/selectors are blocked | Require explicit cubes for 3D requests; reject FA physical-domain selection; retain schema-only index/value selectors without inventing a vertical axis for 2D records |
| A failed FA transfer removes every product | Require failure and pending publication, prohibit the failed surface product, inventory/size-check and independently reopen/load earlier complete products; retain source-byte, lock, partial and transfer cleanup checks |
| A partial CROCO field mock matches inventory | Supply the real preflight `time_varying` fact; retain native-index attributes, reordered values and unrelated temperature identity |
| Mixed stored units are normalized across files | Reject inconsistent velocity/geography definitions before output, identify both providers and preserve source bytes; separately verify a consistent km/h sequence against analytical m/s and W-interpolation truth |
| Several atmosphere sources are an admitted coupling request | Use an admitted synthetic atmosphere/ocean pair, with native NEMO clock/geography metadata; retain moving-centre, independent-grid, mask, temperature, budget, optionality, replay and ordinary-reader checks |
| Track names alone establish units | Declare degrees on synthetic prescribed tracks without changing their coordinates or times |
| Native mask support is automatically a requested output | Explicitly select the CROCO mask for model-grid output while excluding it from polar output; retain binary-mask checks |
| Unrelated PRES copies are forbidden by SEA interpretation | Reject an actually unknown interpretation; existing unchanged-value checks still cover unrelated PRES |
| Retired `strict` YAML reaches runtime alignment | Reject it at schema loading; retain valid `common` behavior and the separate supported low-level strict helper |
| Common association repairs a missing required field | Reject missing NEMO records before alignment rather than dropping required times |
| Preceding-hour association relabels ocean `time` | Compare native sample times and bounds with the source and interval-end association with `center_time`; retain values, statistics, warnings, replay and ordinary-reader checks |
| One file can change the calendar of a multi-file source | Apply the positive Gregorian-encoding fixture consistently to all four NEMO files, without changing decoded sample times |
| Legacy target IDs/status duplicates are necessary to prove shared geography | Compare actual target coordinates and verify the portable manifest; replay automatic controls through binding rather than expecting resolved YAML to invent explicit controls |
| The AROME starter already selects FA | Keep starter construction backend-free and check the maintained default only for explicitly declared FA; remove the incomplete legacy inspection fake, retaining the real metadata-only CLI test in `test_fa_cubes` |
| A changed FA grid must reach a late loader diagnostic | Check earlier selected-field ambiguity, including both providers, without admitting incompatible geometry |
| Nominal angular-fixture spacing is exactly a metre-grid spacing | Independently calculate WGS84 centre spacing with `pyproj.Geod`; do not loosen a tolerance or copy a production-plan value |
| Export-disabled preview has no authored products | Preserve planned intent without creating outputs; check actual publications separately |
| Coupled field outputs are split by vertical group | Expect one dataset per source/product: five products for two sources, two field roles and one requested track |

The retired three-atmosphere shared-target fixture becomes two admitted physical
sources. Its masked ocean source now supplies the coarsest 3-km grid. The
coarsest-grid and masked-origin invariants, Kelvin values, moving centres and
independent reader remain checked; this is a reworked synthetic test layout,
not an unchanged producer fixture or real-data qualification.

## Retained failures

| Count | Observed problem | Disposition |
|---:|---|---|
| 8 | Meso-NH native face latitude is missing/ambiguous during regional binding | Retain analytical and real-fixture checks; no evidence that native staggered extraction is retired |
| 7 | FA polar assembly conflicts on `source_i` | Retain actual scalar/mask/shared-target and unified-process checks; never use merge overrides to conceal incompatible coordinates |
| 2 | Named-source CROCO `current_provenance` is absent | Retain the documented mask-authority/boundary-policy contract, including the review correction below |
| 2 | FA track products lack documented native indices/snapping fields | Retain public-output regression checks |
| 1 | Unmapped GRIB record provenance is absent | Retain inspectability coverage |
| 4 | Coupled status lacks the tested `time_alignment` record | Leave the compatibility/record-contract mismatch unresolved, not silently classify it obsolete |
| 2 | Centroid binding accepts only one common operation time | Retain the method-admission failure checks; no scientific relaxation approved |

Complete final failing nodes, relative to `src/frameit/testing/numerical/`:

```text
test_arome_fa_coupling.py::test_arome_fa_and_surfex_fa_share_the_effective_target_on_distinct_grids
test_coupled_shared_polar.py::test_dense_fa_surface_moving_polar_values_masks_and_readonly_inputs[True]
test_coupled_shared_polar.py::test_dense_fa_surface_moving_polar_values_masks_and_readonly_inputs[False]
test_coupled_shared_polar.py::test_primary_pair_shared_target_geometry_budgets_and_fresh_exports[True]
test_coupled_shared_polar.py::test_primary_pair_shared_target_geometry_budgets_and_fresh_exports[False]
test_croco_mnh_coupling.py::test_generated_mesonh_croco_centroid_rejects_invalid_inputs[one_common_time-at least two]
test_croco_mnh_coupling.py::test_croco_mnh_shared_polar_keeps_sigma_support_and_current_identity[True-False]
test_croco_mnh_coupling.py::test_croco_mnh_shared_polar_keeps_sigma_support_and_current_identity[True-True]
test_fa_environment.py::test_default_interpreter_coupled_exports_and_shutdown[True]
test_fa_environment.py::test_default_interpreter_coupled_exports_and_shutdown[False]
test_fa_mapping.py::test_native_projected_extraction_and_ordinary_reader_provenance
test_fa_mapping.py::test_coupled_projected_source_retains_offsets_and_own_indices
test_fa_pipeline.py::test_grib_and_fa_share_one_run_without_native_runtime_collision
test_fa_pipeline.py::test_netcdf_fa_two_grids_time_intersection_independent_reopening[True]
test_fa_pipeline.py::test_netcdf_fa_two_grids_time_intersection_independent_reopening[False]
test_fa_pipeline.py::test_primary_grib_epygram_surfex_native_exports[True]
test_fa_pipeline.py::test_primary_grib_epygram_surfex_native_exports[False]
test_grid_representations.py::test_real_mnh_native_faces_match_source_file
test_grid_representations.py::test_cartesian_grid_choices_reopen_with_physical_samples[interfaces-native]
test_grid_representations.py::test_cartesian_grid_choices_reopen_with_physical_samples[mass-native]
test_grid_representations.py::test_cartesian_choice_does_not_change_real_polar_or_tracking[interfaces]
test_grid_representations.py::test_cartesian_choice_does_not_change_real_polar_or_tracking[mass]
test_grid_representations.py::test_secondary_declared_pair_normalizes_without_primary_alias_fields
test_grid_representations.py::test_mixed_horizontal_coordinate_units_preserve_physical_faces
test_grid_representations.py::test_native_crop_preserves_faces_with_mixed_horizontal_units
test_nemo_arome_coupling.py::test_generated_arome_nemo_centroid_rejects_invalid_inputs[one_common_time-at least two]
```

Later assertions behind these primary failures remain unverified. This audit does
not certify that every unreachable historical expectation is current.

## Commands and supporting evidence

All Python checks used `frameit_env`, Python 3.13.18, and this checkout's absolute
source `PYTHONPATH`. The existing approved fixture's nine payload checksums pass
before and after both full runs.

Exact final command, from the repository root:

```bash
PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 FRAMEIT_CI_DATA_ROOT="$PWD/build/yaml-v3-ci-fixture-01" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLBACKEND=Agg TMPDIR=/tmp/opencode conda run --no-capture-output -n frameit_env python -B -m pytest -q --junitxml=/tmp/opencode/frameit-suite-final-20261117.xml > /tmp/opencode/frameit-suite-final-20261117.log 2>&1
```

The baseline used exactly the same environment and pytest invocation with
`frameit-suite-baseline-20261117` instead of `frameit-suite-final-20261117` for
the log/XML names. Neither full invocation selected modules, excluded tests,
used fail-fast, changed warning policy or substituted fixtures.

Supporting checks and logs under `/tmp/opencode/`:

- `frameit-suite-collect-20261117.log`: 3209 tests; final collection log: 3210.
- `frameit-audit-core-01`: 74 passed / eight retained native-grid failures.
- `frameit-audit-coupling-02`: 86 passed / 16 failures before later corrections.
- `frameit-audit-ocean-03`: 116 passed / nine failures before later corrections.
- `frameit-audit-repairs-04`: 12 passed / three further stale assertions exposed.
- `frameit-audit-final-replacements-05.log`: those final three corrections pass.
- `frameit-audit-review-guard-06.log`: two passes / two expected observed
  `KeyError: current_provenance` failures after restoring the documented check.
- `frameit-audit-frozen-tests-20261117.json`: all fifteen test-module hashes
  match after the final run.
- Supplementary `conda run --no-capture-output -n frameit_env python -B -m pytest -q docs/test_check_publication.py`:
  16 passed / 40 passing subtests. This module is outside configured testpaths;
  its counts are not added to the full-suite counts.
- `conda run --no-capture-output -n frameit_env python -B -m pip check` passes.
- `sha256sum --check --strict SHA256SUMS`, from the approved fixture root:
  all nine payloads pass.
- Ruff JSON comparison across the fifteen changed modules: 90 baseline /
  76 current diagnostics, zero introduced, preserving diagnostic multiplicity.
  Existing findings are not called a clean lint run.
- `git diff --check` passes.

The full runs retain warnings, including the NumPy binary-size runtime warning,
netCDF4/xarray shape deprecations and xarray future-combine warnings. No
installation or environment repair was attempted. PNG smokes ran only in the
unfiltered full suites; their generated images were not opened.

## Review, boundaries and documentation

One fresh read-only task-scoped review found one Important issue and no
Critical/Minor issues. The ocean guide still promises named-source
`current_provenance`, including mask authority and boundary policy. The audit
restored that assertion, retained the new typed-angle/preparation checks, and
observed both current-enabled cases fail on the missing record. The final full
suite includes those failures. The runtime defect is not claimed fixed.

Other unresolved production/record-contract failures were deliberately retained.
Schema-only selector acceptance is not scientific support; invalid metadata
still fails without creating an owned output root. Broader lifecycle choices
were not redesigned.

Scientific impact: no method, physical assumption or default changed.
Compatibility: no public output/configuration changes or migration.
Docs: no user-facing impact because only tests and unpublished development
evidence changed. No strict Sphinx build or new visual preview was needed;
published pages/assets and the existing preview remain unchanged.

No installs, environment repairs, downloads, production/HPC jobs, benchmark
campaigns, reserved full-diagnostic campaign, pushes or merges were performed.
The newly authorized full pytest run now has actual red evidence; installed
qualification, unresolved failures and human acceptance remain open.
