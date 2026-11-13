# Task 02 verification commands and recorded results

Commands run from the repository root. Results below are historical; no checks
were rerun to create this appendix.

## Focused RED/GREEN checks

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py
```

| Recorded run | Observed result | Exit |
|---|---|---|
| Initial RED | 258 failed, 21 passed | 1 |
| Intermediate GREEN runs | 296, 300, 303, 305, then 307 passed | 0 |
| Final GREEN, two runs | 326 passed each | 0 |

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py --tb=short
```

| Recorded run | Observed result | Exit |
|---|---|---|
| Initial GREEN | 279 passed | 0 |
| Later boundary-test RED | 5 failed, 291 passed | 1 |

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py -k 'fa_declarations_do_not_require or binding_request_mutation' --tb=short
```

RED: **4 failed, 296 deselected**, exit 1.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py -k unquoted_yaml_timestamp --tb=short
```

RED: **1 failed, 300 deselected**, exit 1.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py -k fa_admission_errors --tb=short
```

RED: **2 failed, 301 deselected**, exit 1.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py -k tracking_dependency_source_runtime --tb=short
```

RED, two runs: **2 failed, 303 deselected** each, exit 1.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py -k omitted_vortex_options --tb=short
```

RED: **2 failed, 305 deselected**, exit 1.

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_configuration_v3.py -k 'mutable_runtime_fields or execution_options_own' --tb=short
```

RED: **19 failed, 307 deselected**, exit 1.

## Supplemental regressions

### Requests, tracking, winds, sampling and constructors

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_request_selection.py::test_selection_preserves_native_values_and_metadata \
  src/frameit/testing/numerical/test_request_selection.py::test_physical_domains_are_axis_specific \
  src/frameit/testing/numerical/test_request_selection.py::test_invalid_comodo_domain_fails \
  src/frameit/testing/numerical/test_request_selection.py::test_positive_mnh_heights_do_not_establish_physical_domain \
  src/frameit/testing/numerical/test_request_selection.py::test_ordinary_grib_axes_have_no_vertical_halo \
  src/frameit/testing/numerical/test_request_selection.py::test_source_native_index_retains_original_positions_after_subset \
  src/frameit/testing/numerical/test_request_selection.py::test_surface_group_copies_global_metadata \
  src/frameit/testing/numerical/test_request_selection.py::test_native_index_and_value_selections_remain_distinct \
  src/frameit/testing/numerical/test_request_selection.py::test_physical_filter_does_not_renumber_explicit_indices \
  src/frameit/testing/numerical/test_wind_pressure_seed.py \
  src/frameit/testing/numerical/test_polar_axes.py \
  src/frameit/testing/numerical/test_wind_collocation.py \
  src/frameit/testing/numerical/test_configuration_v2_1.py::test_lazy_wind_and_angle_equivalence \
  src/frameit/testing/numerical/test_configuration_v2_1.py::test_radius_metadata_converts_values_and_detects_disagreement \
  src/frameit/testing/numerical/test_configuration_v2_1.py::test_pressure_height_canonical_equivalence \
  src/frameit/testing/numerical/test_configuration_v2_1.py::test_spacing_argument_deprecation_preserves_metres \
  src/frameit/testing/numerical/test_configuration_v2_1.py::test_pressure_wind_direct_call_normalizes_components_before_minimum \
  src/frameit/testing/numerical/test_configuration_v2_1.py::test_flat_public_documents_cannot_use_runtime_dispatch \
  -k 'not test_schema_maps_seed_to_tracker and not test_explicit_count_and_serialized_configuration'
```

GREEN, initial and round-1 runs: **98 passed, 2 deselected**, exit 0.

### Lazy assembly, resource cleanup and FA contracts

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_variable_shards_merge_without_duplicate_times \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_variable_shards_reject_unsafe_assembly \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_arome_reference_time_survives_normalization \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_arome_reference_time_rejects_ambiguous_collisions \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_time_series_requires_field_at_each_selected_time \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_time_series_expands_changing_timeless_snapshots \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_time_series_retains_declared_duplicate_precedence \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_variable_shard_original_handles_close \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_variable_shards_selected_only_payload_stays_lazy \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_variable_shards_validate_repeated_curvilinear_geography \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_variable_shards_follow_auxiliary_dependencies_across_files \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_variable_shards_sample_clock_ignores_unrelated_scalar_coordinates \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_variable_shards_preserve_and_validate_interval_bounds \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_netcdf_reuse_expires_on_close \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_netcdf_reuse_respects_engine_and_chunks \
  src/frameit/testing/numerical/test_netcdf_assembly.py::test_netcdf_failed_load_closes_and_allows_retry \
  src/frameit/testing/numerical/test_fa_contracts.py::test_descriptor_json_unknown_meaning_and_native_fact_precedence \
  src/frameit/testing/numerical/test_fa_contracts.py::test_observed_layout_does_not_match_another_or_unidentified_release \
  src/frameit/testing/numerical/test_fa_contracts.py::test_encoded_scaling_descriptor_requires_consistent_native_evidence \
  src/frameit/testing/numerical/test_fa_contracts.py::test_raw_vertical_header_survives_without_coordinate_or_field_assumptions \
  src/frameit/testing/numerical/test_fa_contracts.py::test_typed_words_are_reinterpreted_not_cast_and_unknowns_never_read \
  src/frameit/testing/numerical/test_fa_contracts.py::test_unknown_protocol_rejected_without_opening_source \
  src/frameit/testing/numerical/test_fa_contracts.py::test_worker_rejects_protocol_before_loading_optional_libraries
```

GREEN, initial and round-1 runs: **46 passed, 71 warnings**, exit 0.

### Task 01 identity and delivered runtime

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q src/frameit/testing/numerical/test_hpc_execution.py -k 'test_resource_limits_use_strictest_allocation_and_affinity or test_thread_scope_restores_environment_and_dask or test_atomic_no_clobber_publication_race or test_atomic_publication_honors_umask_and_retains_existing_permissions or test_failed_netcdf_write_preserves_previous_complete_product or test_group_filename_collisions_fail_before_writing or test_group_phases_share_one_bounded_pool_and_close_it or test_cli_keeps_checkout_under_local_in_parent_and_spawn or test_cli_info_reports_selected_installation'
```

GREEN, baseline and subsequent runs: **16 passed, 12 deselected, 4 warnings**,
exit 0.

### Direct numerical vortex checks

```bash
PYTHONPATH="$PWD/src" conda run -n frameit_env python -m pytest -q \
  src/frameit/testing/numerical/test_multifield_vortex.py::test_log_pressure_native_interpolation_known_profiles \
  src/frameit/testing/numerical/test_multifield_vortex.py::test_ellipsoidal_vorticity_analytic_solid_rotation_and_warped_grid \
  src/frameit/testing/numerical/test_multifield_vortex.py::test_barnes_matches_independent_direct_gaussian_sum \
  src/frameit/testing/numerical/test_multifield_vortex.py::test_composite_weights_rejection_and_longitude_wrapping \
  src/frameit/testing/numerical/test_multifield_vortex.py::test_circulation_exact_samples_and_missing_arc \
  src/frameit/testing/numerical/test_multifield_vortex.py::test_translation_qc_uses_elapsed_interval_not_hourly_noise \
  src/frameit/testing/numerical/test_multifield_vortex.py::test_unresolved_spacing_is_not_a_silent_smoothing_choice
```

GREEN: **8 passed**, exit 0.

Latest verified total: **494 passed** = 326 + 98 + 46 + 16 + 8.
This is not a whole-project suite result.

## Future-dependent checks not run

- Full legacy/public suite; public-command, schema and catalogue portions of
  `test_configuration_v2_1.py`; `test_templates.py`,
  `test_documentation_example.py`, `test_configuration_integration.py`,
  CLI portions of `test_inspect_metadata.py`, `test_all_tests.py`,
  `docs/test_repository_examples.py`, documentation/matrix producer checks:
  Tasks 15–16/19.
- Remaining `test_hpc_execution.py` CLI/request/status integration:
  Tasks 12–16/19.
- Remaining request, wind, grid, NetCDF, ocean/coupling, SURFEX, FA replay/cube/
  pipeline and writer-configuration integration: inventory, binding, execution
  and caller-wide fixture conversion in Tasks 03–14 and 15–16/19.
- Explicitly excluded public-serialization nodes:
  `test_wind_pressure_seed.py::test_schema_maps_seed_to_tracker` and
  `test_polar_axes.py::test_explicit_count_and_serialized_configuration`.
- Source-archive payload binding/full decoder replay was not run.
- The schema worker did not run documentation checks. The lead's strict
  build/publication/preview results are recorded in `STATE.md`.
