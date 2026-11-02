# Sharded Zarr v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select sharded Zarr v3 with `output.engine: zarr`, retaining the existing products and default NetCDF behavior.

**Architecture:** Add one optional Zarr writer beside the existing NetCDF writer, reusing metadata preparation and the export orchestration. Carry dimension-size mappings through execution options, planning, provenance and export. Use a dedicated local-directory publication helper rather than adapting file hard-link publication to directories.

**Tech Stack:** Python, xarray, Dask, optional Zarr v3, pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-sharded-zarr-design.md`

## Global Constraints

- NetCDF remains the default. No separate backend selector is introduced.
- `output.format` remains optional, NetCDF-specific, and unused for Zarr.
- Local stores only; no append/resume, cloud URLs or dual-format runs.
- Preserve scientific values, masks, coordinates, precision and metadata meanings.
- Optional dependencies must not be imported on ordinary NetCDF paths.
- Source datasets remain read-only; stage only task-related files; do not push.

## Review Focus

- Unaligned Dask chunks must not cause parallel writes to the same shard.
- A failed replacement must preserve the previous complete product.
- Zeros, integer sentinels, NaNs and decoded times must survive ordinary-reader reopening.
- Track and coupled groups have different dimensions; unused size overrides must not fail them.
- Schema-only validation and NetCDF execution must work without Zarr installed.

## File map

- Create `src/frameit/io/zarr_export.py`: dependency checks, shape resolution, encoding and dataset writing.
- Modify `src/frameit/utils/atomic.py`: isolated directory publication helper.
- Modify `src/frameit/io/netcdf_export.py`: shared metadata preparation and existing orchestration dispatch; keep public NetCDF APIs working.
- Modify `src/frameit/core/configuration.py`, `execution.py`, `preflight.py`, `coupled.py`: validate/resolve settings, preview names, export and inventory.
- Modify `src/frameit/cli.py`: explain legacy overall-export switch for either backend.
- Modify `pyproject.toml`, `src/frameit/templates/{arome,mesonh}.yaml`: optional extra and discoverable configuration.
- Create `src/frameit/testing/numerical/test_zarr_export.py`; extend existing configuration, output-layout and execution tests as needed.
- Update `README.md`, `docs/source/user_guide/{configuration_file,output_files}.rst`, installation documentation and `CHANGELOG.md`.

### Task 1: Safe sharded dataset writer

**Interfaces:** `write_dataset_zarr(ds, path, *, metadata, product_type, group=None, track_filename=None, overwrite=True, compress_level=1, compress_coords=False, chunk_size=None, shard_size=None) -> Path`; `check_zarr_dependencies() -> None`; `atomic_directory_output(path, *, overwrite=True)` context manager.

- [ ] Locate an available project test environment; the current shell's `python` lacks xarray. Inspect installed APIs and authoritative library documentation to establish supported xarray/Zarr version floors; add the optional `zarr` extra without changing core dependency requirements.
- [ ] Write failing writer/publication tests: actual v3 sharding codec; exact numeric/mask/time round trip using `xr.open_zarr` without importing FrameIt in a subprocess; scalar CRS, integer/boolean/string coordinates; input encodings do not leak NetCDF compression keys.
- [ ] Write failing safety tests: existing destination with overwrite disabled; write failure leaves old product untouched; publication failure restores old product; temporary directories cleaned; symlink/non-store replacement rejected.
- [ ] Run `python -m pytest src/frameit/testing/numerical/test_zarr_export.py -q`; confirm failures reflect missing implementation.
- [ ] Implement writer with shared metadata preparation, lossless compression and explicit v3 encoding. Default chunk extent: time=1, other axes=min(axis length,128); default shard extent: time=8 chunks, other axes=4 chunks. Explicit shard-only overrides choose a compatible default chunk divisor; chunk-only overrides retain default shard chunk counts. Never clamp explicit extents to dataset length, since boundary chunks may be partial. Scalars are unsharded. Document and test empty axes or unsupported dtypes with actionable failures.
- [ ] Validate positive integer dimension mappings and shard/chunk divisibility. Rechunk lazy arrays to shard boundaries for safe writes without loading whole datasets. Keep existing NetCDF metadata semantics; avoid carrying incompatible source storage encodings.
- [ ] Implement sibling temporary-store publication; when replacing an existing store, rename the old store to a private backup, publish the new store, restore the backup on caught publication failure, then remove only owned temporary/backup directories. Document the visibility gap and possible crash leftovers; run-root locking remains the concurrency boundary.
- [ ] Run writer tests to green, including unequal/unaligned Dask chunks, partially filled shards, absent dimensions and overrides. Commit only related writer, tests, helper and packaging changes.

### Task 2: YAML-to-product integration

**Interfaces:** `ExecutionOptions.zarr_chunk_size: dict[str,int]` and `.zarr_shard_size: dict[str,int]`, both empty by default; existing `export_outputs` accepts those optional mappings. `engine='zarr'` selects `.zarr` naming and writer dispatch throughout.

- [ ] Write failing tests accepting `output.engine: zarr`, optional size maps and omitted `output.format`; reject booleans, nonintegers, nonpositive sizes, nonmapping settings and explicit nondivisible pairs. Schema-only validation must not import Zarr.
- [ ] Write failing direct-export and synthetic pipeline tests: track, Cartesian and polar stores; sanitized names; track references; coupled source/group descriptors; dry-run `.zarr` paths; recursive inventory byte totals; effective settings survive resolved-config reload. Retain `.nc` tests unchanged.
- [ ] Run `python -m pytest src/frameit/testing/numerical/test_zarr_export.py src/frameit/testing/numerical/test_configuration_v2.py src/frameit/testing/numerical/test_hpc_execution.py src/frameit/testing/numerical/test_output_layout.py -q`; confirm new failures.
- [ ] Add defaults/validation and execution-option propagation, including resolved configuration and override provenance. Check optional dependency availability before scientific processing when Zarr export is enabled, but not for schema-only validation or disabled export.
- [ ] Extend existing export worker arguments/dispatch to choose the writer and suffix without duplicating the full orchestrator. Preserve bounded worker execution and NetCDF entry-point compatibility. Include actual loaded Zarr version in existing backend provenance.
- [ ] Fix names in ordinary/coupled preflight and product descriptors; calculate store byte totals recursively instead of counting directory inode bytes. Update export log/help wording without renaming existing switches or timing sections relied on by tests.
- [ ] Test missing dependencies via isolated/mocked imports and confirm ordinary NetCDF export still works. Run focused tests to green and commit task-related changes.

### Task 3: Documentation and final verification

**Interfaces:** User YAML and public output contract established in Tasks 1–2.

- [ ] Document `engine: zarr`, installation/version requirements, optional size maps, compression behavior, format/unlimited-time applicability, and the legacy `export.netcdf`/`--no-export-netcdf` overall export gate.
- [ ] Explain chunks versus shards in plain language with the approved 128-chunk example, element-count units, defaults/overrides, Dask distinction, boundary handling, memory/read trade-offs and ordinary-reader examples. State that values/resolution do not change.
- [ ] Update templates, README, output naming/layout, recursive inventory semantics, replacement/crash limitations and changelog; do not imply NCO/CDO can read Zarr or make unmeasured performance claims.
- [ ] Run `python -m pytest src/frameit/testing/numerical -q`; record actual results and missing optional fixtures/dependencies rather than claiming they passed. Run documentation build if the existing environment supports it.
- [ ] Run `git diff --check`, review connected code and task-only diff, commit documentation/final corrections locally, and report exact verification results and commit IDs. Preserve the unrelated `opencode.json` file.
