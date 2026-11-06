# Scientific topic guides and archival boundary

Documentation step 3, 2026-10-28; starting checkout `382624c`. Root instructions,
both external maintainer plans, current README/source/docs, the content map and
previous documentation diffs were inspected. The tracked tree was clean; existing
untracked `opencode.json` was preserved. This is not completion of steps 4/5 or
new scientific qualification.

## Public topics and scientific ownership

Neutral filenames remain; users do not need an implementation-stage vocabulary.

| Current public topic | Retained scientific/user contract | Full historical record here |
| --- | --- | --- |
| [FA compatibility and limitations](../../source/user_guide/fa_baseline.rst) | Current finite operations/families, explicit gridpoint/cube scope versus metadata-only/blocked rows, selected native errors/scaling and evidence requests. | [fa_baseline_history.rst](fa_baseline_history.rst) |
| [FA metadata and provenance](../../source/user_guide/fa_contracts.rst) | Facts/declarations/unresolved meaning, source assertions, structural types/budgets, masks/scaling, representative descriptors and ordinary readers. | [fa_contracts_history.rst](fa_contracts_history.rst) |
| [FA grids, domain selection and centres](../../source/user_guide/fa_geometry.rst) | Zones/native indices, explicit Earth model and CF origin, native-axis metric/ties/coverage, Snyder reference, numerical tolerances and snapping metadata. | [fa_geometry_history.rst](fa_geometry_history.rst) |
| [Coupled atmosphere and surface sampling](../../source/user_guide/fa_surface.rst) | Independent sources/products, exact-common/strict times, moving shared targets, budgets/masks, finite quantities/units/signs/time-support examples and unresolved producer meaning. | [fa_surface_history.rst](fa_surface_history.rst) |
| [Native atmospheric levels and cubes](../../source/user_guide/fa_atmosphere.rst) | Exact declared records, original full/interface labels/indices, A/B/PREFER, sparse selection, selected physical-vector rules and limits. | [fa_atmosphere_history.rst](fa_atmosphere_history.rst) |
| [Spectral FA support and limitations](../../source/user_guide/fa_spectral.rst) | Blocked production/raw-coefficient boundary, missing native/transform/reference contracts, separately labelled analytical library equations/conventions and finite numerical bounds. | [fa_spectral_history.rst](fa_spectral_history.rst) |

The topic editor owns these current contracts and links; producer/maintainer
scientific review remains unresolved where recorded. No new method, default,
physical-coordinate operation or scientific approval is introduced. Necessary
equations/citations/bounds stay public; detailed probe APIs/recipes, dependency
experiments, failed attempts and raw verification ledgers stay in the full originals.
The spectral candidate is not a supported FA coefficient decode or extraction path.

Preserved public numerical distinctions include:

- Snyder spherical tangent-Lambert basis and `fa-geometry-method`; `1e-5 m`
  sample/CRS consistency versus `2e-5 degree` header rounding, `64 * epsilon *
  coordinate_magnitude` axis/tie roundoff, first storage-index ties, `2e-11 degree`
  independent equations, `1e-7 m` canonical axes, `1e-10 degree` angular axes and
  the existing `5e-7` tangent-cone check. Source CRS distance is not ground distance.
- Original one-based full/interface labels versus zero-based native indices;
  `A_Pa = PAHYBR * PREFER`, dimensionless B, 100000-Pa independent fixture and
  complete coefficient axes through sparse data selection. No inferred mass means,
  pressure/height or incomplete CF formula terms.
- `5e-4 m/s` direction/basis bound only for the specified 1-km/8-km/5-m/s fixture;
  `1e-9` constant polar scalar checks versus exact shared target coordinates.
  Bilinear point sampling supplies no area-budget conservation guarantee.
- The exact double-Fourier mixed/pure-mode equations, unit/constant coefficients,
  inquiry counts/truncations and `rtol=0, atol=5e-13` float64 small-mode scope.
  The recorded `5.551115123125783e-15` error is historical library evidence,
  not a fresh test result, real-field tolerance or scientific promotion.
- Native C0/C1 type identities, SFX.TG1P1/WG1P1 IDs and mathematical C2 smoothness;
  native/source sampling, masks/zeroes, source units/signs and instant/interval
  distinctions are not erased by cosmetic token replacement.

## Removed public records and repaired links

All six `docs/source/user_guide/fa_epygram_c0.rst` through `fa_epygram_c5.rst`
sources are removed outright, with their toctree entries. Their complete records
already exist under the identical basenames in this directory, with a historical
notice and relocated links. There are no stage-named public stubs or redirects.
The finite old-URL -> current-topic/archive assignments remain in [CONTENT_MAP.md](CONTENT_MAP.md).

Before deletion, assertions compared all fourteen frozen full pages to the original
`9b11d602c4fb05fb2adf74b699439de6a0b8625b` bodies after only the declared notice/link
relocations, and to their unchanged bytes at `382624c`. All passed. The check still
passes after removal. `entry_points_history.md` is unchanged too. Twelve archived
include targets and 68 local RST links resolve; the unchanged directory depth keeps
`../../../src/...` and `../../../example/...` references valid. No bulk/private
dataset, generated product or machine environment is archived.

The four YAML examples had inbound stage references/header wording. Comments in
`arome_fa_native_cubes.yaml`, `coupled_arome_fa_polar.yaml`,
`coupled_cyclone_polar.yaml` and `coupled_fa.yaml` now name current topics. Parsed
YAML and native IDs are identical to `382624c`; no value/schema meaning changes.
The illustrated native-cube IDs are not a promise that real S001 records are gridpoint.

Other user-guide, tracker, polar, visualization and tracker-extension sources were
audited for roadmap references. They need no unrelated scientific rewrite; the
useful extension tutorial remains public. The legitimate quintic C2 description
and all method references/experimental statuses remain.

## Observed verification

Local tools import FrameIt from this checkout: Python **3.13.16**, FrameIt **1.1.0**,
Sphinx **8.1.3**, RTD theme **3.1.0**. `/tmp` was full; designated fresh outputs and
`TMPDIR` use ignored `build/`, without removing unrelated temporary work.

An initial strict build to `build/docs-fa-topics-20261028` failed for two short
RST heading underlines (metadata and surface guides). They were corrected, and a
fresh build to `build/docs-fa-topics-final-20261028` passed with no warnings.
Review then clarified that the scaling opt-in flag is software permission, not
proof of the researcher's scientific justification. The final reviewed command
exited **0 with no warnings**:

```sh
TMPDIR="$PWD/build" LC_ALL=C LANG=C \
/tmp/opencode/frameit-hpc-venv/bin/sphinx-build \
  -q -W --keep-going -b html docs/source build/docs-fa-topics-verified-20261028
```

Task-local preservation/publication assertions:

```sh
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python build/check_fa_topic_docs.py --archive-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python build/check_fa_topic_docs.py
```

Observed checks on the fresh rendered artifact: **29** public RST sources, **31**
HTML files and **1800** local link/anchor checks; all six removed HTML/source URLs
and search/inventory entries absent; no public archive/catalogue routes or FA
viewcode re-entry. The six rendered topic titles, scientific definitions, masks,
native IDs, equations and limits were reviewed. Five contextual source lines retain
native C0/C1 or quintic C2 meanings; no blanket token waiver is used. Hybrid/Fourier
math and existing public method anchors are preserved, and the JSON/ordinary-NetCDF
reader example compiles without importing FrameIt. The shared-target fragment
passes schema-only validation when merged into a complete coupled configuration.

All four edited examples exited **0**, printing `OK: schema validated`:

```sh
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/arome_fa_native_cubes.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/coupled_arome_fa_polar.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/coupled_cyclone_polar.yaml --schema-only
TMPDIR="$PWD/build" /tmp/opencode/frameit-hpc-venv/bin/python -m frameit validate example/config_file/coupled_fa.yaml --schema-only
```

`git diff --check` passes during review. The assertions also check that production/
numerical code, admission gates, schemas, test oracles, package/test catalogues,
dependencies and CI are unchanged. Final staged review and the focused local
commit are reported at handoff. The one-off checker lives only in ignored `build/`;
no new framework, execution service, dependency or CI contract is added.

## Remaining work

Next is step 4: the remaining public-entry audit, changelog wording and ordinary
messages, especially `src/frameit/io/fa_contracts.py::SPECTRAL_GATE`, preserving
the coefficient/native-grid guard and machine-readable contracts. Example header/
link cleanup is already closed here. Step 5 still owns complete deployment/CI
acceptance; the workflow's Python-3.12 `make -C docs html` and `docs/build/html`
artifact path are unchanged.

Hosted CI, Python-3.12 docs, reference Sphinx 9.2.0, native numerical/lifetime
suites, production runs/reader execution, browser visual inspection, external
link fetching and independent publisher/scientific revalidation were not run.
Source/test inspection and documentation assertions are not scientific approval;
real-producer scaling/units/support/Earth-model/vertical/vector evidence and
native-error/spectral/interval references remain unresolved where documented.
