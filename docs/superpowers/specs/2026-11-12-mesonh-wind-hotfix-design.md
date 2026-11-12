# Meso-NH wind metadata hotfix

## Intent and scope

Researchers with incomplete Meso-NH projection headers must be able to declare
known rotation parameters, or explicitly accept responsibility for treating the
components as Earth-relative. This is a focused extension of existing wind
declarations, not a new rotation method or automatic fallback.

## Agreed behavior

- `rotation.method: mesonh_projection` accepts optional finite numeric `BETA`,
  `RPK`, and `LON0`. BETA/LON0 are degrees; RPK is dimensionless in [-1, 1].
  Explicit YAML values override source variables, then source attributes.
- Missing effective parameters fail with the affected wind pair, all missing
  names, and instructions to supply known values under the YAML `rotation`.
  No value is inferred or silently defaulted, including zero.
- For explicit Meso-NH NetCDF pairs only, `reference_frame: earth` can override coherent
  grid-basis metadata when at least one effective projection parameter is absent.
  Warn that no grid-to-Earth rotation occurs and record the warning and original
  metadata in provenance/output attributes. Do not modify input datasets.
- Conflicts remain fatal with complete projection parameters, invalid or mutually
  contradictory metadata, wrong components, non-Meso-NH sources, implicit legacy
  declarations, GRIB inputs, or inconsistent prepared fields. Prepared outputs
  are idempotent; changed explicit projection parameters conflict with the record.
- Native outputs retain native sample locations. Under the explicit bypass their
  declared Earth basis must not be contradicted by unqualified grid-basis flags;
  original source attributes remain inspectable.
- Retain needed projection headers as checked coordinates through shard assembly
  and native tracker selection, without validating unused wind geometry during
  scalar extraction. Qualify superseded global basis flags while preserving
  other raw pairs' basis metadata.

## Approaches

1. **Selected:** extend the shared projection resolver and narrowly gate the
   existing frame check. All preflight, loading, native export and tracker callers
   use the same rules. This fixes the requested workflow without new options.
2. Unconditionally trust Earth declarations: rejected because it weakens unrelated
   metadata checks and hides avoidable scientific conflicts.
3. Add a separate force/override option: rejected because the explicit declaration
   and missing-parameter condition already express the requested policy.

The maintainer approved the missing-parameter-only exception in the conversation.
No new scientific validation or human scientific sign-off is claimed.

## Compatibility and release

Keep schema `2.1`, existing numerical formula, default basis, optional diagnostics,
output variable names and locations unchanged. Document troubleshooting, affected
task/reference/method pages and the reference YAML. Release name/tag:
`2.0.0rc2-hotfix1` / `v2.0.0rc2-hotfix1`; valid Python package version:
`2.0.0rc2+hotfix1`. Push the dedicated branch, open a PR against `main`, and publish
a prerelease from the verified hotfix commit without merging `main`.

## Verification and constraints

Use only Conda `frameit_env`, Python 3.13, compact synthetic fixtures and existing
dependencies. Test missing/partial/overridden/invalid parameters, header-only
checks without wind reads, strict conflict boundaries, native/prepared output
metadata, idempotence and small end-to-end NetCDF exports reopened using xarray.
Run strict Sphinx/publication checks and inspect live desktop/narrow previews.
Synthetic engineering tests do not qualify every producer dataset or prove that
a researcher's Earth-basis assumption is scientifically valid.
