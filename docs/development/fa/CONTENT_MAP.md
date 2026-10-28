# FA public/developer content and ownership map

Baseline: `9b11d602c4fb05fb2adf74b699439de6a0b8625b`, inspected 2026-10-28.
All old paths below are repository-relative; `UG/` means
`docs/source/user_guide/`. Archive links are relative to this directory.
Tables retain the baseline assignments and line references. Progress below
records completed work; uncompleted destinations remain assignments.

## User-entry rewrite progress

Step 2 starts at `35837df` and delivers the current user path in `README.md`,
`docs/source/getting_started/installation.rst`, `docs/source/getting_started/quick_start.rst`,
`UG/input_files.rst`, `UG/fa_inputs.rst`, `UG/fa_environment.rst`,
`UG/configuration_file.rst` and `UG/output_files.rst`.
See [the user-entry verification record](user_journey.md) for exact checks.

These sources and their rendered article bodies use descriptive current topics,
with the single reference environment, optional interpreter override, scientific
limits and ordinary-reader/partial-product contracts explicit. The environment
ledger include is removed; its original record and catalogue remain unchanged.
All fourteen archived full pages and the entry-point excerpts are unchanged.
The geometry method anchor/equations and wind/grid anchors remain public.

The FA overview includes `coupled_fa.yaml` beginning at `schema_version:` so its
rendered example omits the development header while retaining every parsed setting.
The original YAML comments and other example/release/message cleanup remain owned
by step 4. Descriptive explicit cross-reference text is used for mixed topic
guides awaiting step 3. The original stage pages and global navigation are still
published pending that task; this is not full publication acceptance.

## Owners and completion order

Owners are bounded task roles, not invented individual approvals:

- **Journey editor (step 2):** README, installation, inspect/configure/run/read
  guidance, environment, FA overview, configuration and output explanations.
- **Topic editor (step 3):** current compatibility/metadata/geometry/coupled/cube/
  spectral science and limits; historical page removal and affected navigation.
- **Surface editor (step 4):** example/release/message wording and remaining links;
  preserve settings, IDs and error guards. Scientific ambiguities go to the
  maintainer/producer reviewer; editors cannot grant scientific sign-off.
- **Publication owner (step 5):** fresh strict build and complete artifact review,
  including source downloads/search/inventory and CI's actual upload directory.

Each editor owns incoming links and visible titles/prose for their rows, and checks
the archived evidence before removal. The publication owner verifies the combined
boundary. Neutral topic URLs and `fa-geometry-method` should remain; old stage URLs
listed below are removed, not published as history redirects.

## Old path -> public topic / developer record

| Old path | Public destination and content owner | Developer record / duplicate-removal assignment |
| --- | --- | --- |
| `README.md` | Purpose, short single-environment install and current workflow/topic links — Journey | [FA excerpts](entry_points_history.md); replace stage links/prose at lines 32–70, 184–206 in step 2; Surface checks leftovers in step 4. |
| `docs/source/getting_started/installation.rst` | Same URL: one YAML, editable checkout, fresh named migration, core/extras — Journey | No unique test ledger; retain source at baseline. Step 2 removes stale prerequisites without changing Python/dependencies. |
| `docs/source/getting_started/quick_start.rst` | Same URL: inspect/init/schema-only/metadata preview/run/read — Journey | No roadmap hit; clarify check scope using current CLI in step 2. |
| `docs/source/getting_started/hpc.rst` | Same URL: optional portable Slurm/resource/ownership/incomplete-run procedure — Journey | No roadmap hit; keep site-dependent choices explicit; audit links only. |
| `UG/input_files.rst` | Same URL: input discovery, inventory, model/format/read-only contracts — Journey | No roadmap hit; audit links and advertised scope in step 2. |
| `UG/fa_inputs.rst` | Same URL: authoritative FA/coupling entry, declarations, exact times, independent grids, errors and limits — Journey | [Full original](fa_inputs_history.rst). Step 2 replaces history tour (lines 9–22, 72–83 and later C references), keeping the geometry method/anchor and user limits public. |
| `UG/fa_environment.rst` | Same URL: active-Python workers, optional override, fresh migration and troubleshooting — Journey | [Full original](fa_environment_history.rst). Step 2 removes dependency experiments, old-overlay chronology, test counts and `fa_environment.yaml` literal include from public source. |
| `UG/fa_baseline.rst` | Same URL: current finite compatibility/operation matrix and evidence scope — Topic | [Full original](fa_baseline_history.rst). Step 3 replaces frozen P0 matrix/history; do not treat its blocked cube row as current support. Remove public `fa_p0.yaml` include. |
| `UG/fa_contracts.rst` | Same URL: FA metadata, precedence, unresolved facts, masks/scaling and provenance — Topic | [Full original](fa_contracts_history.rst). Step 3 extracts current public contracts; private protocol/typed-API recipes, old native-reader statements and run logs stay here. |
| `UG/fa_geometry.rst` | Same URL: supported grids, Earth model, CI/C zones, centres/lookup/snap conventions — Topic | [Full original](fa_geometry_history.rst). Step 3 retains equations/reference link/tolerances and compatibility meaning publicly, removes repair chronology/verification log. |
| `UG/fa_surface.rst` | Same URL: independent atmosphere/surface products and selected shared sampling — Topic | [Full original](fa_surface_history.rst). Step 3 retains field distinctions/target budgets/masks/current limits publicly; corpus probes, run chronology and `fa_p3.yaml` include stay developer-only. |
| `UG/fa_atmosphere.rst` | Same URL: explicit native full/interface cubes and coefficients — Topic | [Full original](fa_atmosphere_history.rst). Step 3 keeps associations, original indices, A/B/PREFER, vector limits and meaningful verification scope public; old helper experiments/test runs stay here. |
| `UG/fa_spectral.rst` | Same URL: spectral support and limitations; production gate and missing references — Topic | [Full original](fa_spectral_history.rst). Step 3 keeps coefficient-not-grid distinction and actionable evidence requirements public; candidate APIs/probe recipes/Fourier method evidence and `fa_p4.yaml` include stay here, linked by this index. |
| `UG/configuration_file.rst` | Same URL: actual schema/defaults/precedence/migration, warned alias and optional interpreter — Journey | [Original FA preamble](entry_points_history.md). Step 2 replaces `fa_epygram_c4` link at line 20 with topic guidance. No key/meaning changes. |
| `UG/output_files.rst` | Same URL: ordinary-reader schema, source/vertical identity, descriptors and atomic completion — Journey | [Original FA passages](entry_points_history.md). Step 2 replaces P4/P5/C1/C3/C4/C5 narration at lines 43–86 with current definitions; preserves machine-readable attribute/provenance names. |
| `UG/matrix_testing.rst` | Same URL: opt-in reproducibility/regression workflows, prerequisites and limits — Topic | No roadmap hit; keep commands without converting test success into scientific suitability. Link/scope audit in step 3. |
| `UG/fa_epygram_c0.rst` | No public page; useful current limits -> `fa_baseline`, `fa_inputs`, `fa_contracts` — Topic | [Full stage record](fa_epygram_c0.rst). Delete public source and all inbound links in step 3. |
| `UG/fa_epygram_c1.rst` | No public page; dense admission/scaling -> `fa_inputs`, `fa_contracts` — Topic | [Full stage record](fa_epygram_c1.rst). Delete public source and all inbound links in step 3. Native `C1` type codes survive. |
| `UG/fa_epygram_c2.rst` | No public page; geometry/coefficients -> `fa_geometry`, `fa_atmosphere`, `fa_contracts` — Topic | [Full stage record](fa_epygram_c2.rst). Delete public source and all inbound links in step 3. |
| `UG/fa_epygram_c3.rst` | No public page; coupling/evidence scope -> `fa_inputs`, `fa_surface`, `output_files` — Topic | [Full stage record](fa_epygram_c3.rst). Delete public source and all inbound links in step 3. |
| `UG/fa_epygram_c4.rst` | No public page; alias/migration -> `fa_environment`, `configuration_file`, `fa_contracts` — Topic (Journey extracts migration in step 2) | [Full stage record](fa_epygram_c4.rst). Delete public source and all inbound links in step 3; never reuse old overlay instructions as current setup. |
| `UG/fa_epygram_c5.rst` | No public page; budgets/crash/partial products -> `fa_inputs`, `fa_environment`, `output_files` — Topic | [Full stage record](fa_epygram_c5.rst). Delete public source and all inbound links in step 3; compact measurements are not production quotas/estimates. |
| `docs/source/index.rst` | Descriptive public topics — Topic | Lines 36–41 currently publish all six stage pages. Remove entries with sources in step 3; sidebar-only hiding is insufficient. |
| `docs/source/what_is_frameit.rst`; six pages under `tracker/`; four under `polar_projection/`; `visualization_tools/rotate_polar_axes.rst`; `developper/how_to_add_my_tracker.rst` | Existing topic URLs — Topic | No roadmap meaning found; retain scientific methods/citations/experimental status and useful extension tutorial. `C2` smoothness is legitimate. Check links and generated exposure in step 3. |

The frozen environment/input/README/config/output histories are now developer-only
records; the current public pages retain their user contracts. Remaining public
full-page history copies are temporary duplicates scheduled for removal/rewrite
in step 3; changelog history cleanup is step 4. Preserve the archives. Step 5 must
find no public history copy, stage-named stub or link into this archive.

## Scientific-content ownership: what must survive extraction

| Content | Authoritative public destination / editor | Frozen evidence that must remain inspectable |
| --- | --- | --- |
| Finite AROME/SURFEX producer/layout/operation scope, selected native errors vs metadata, release/type/directory and scaling uncertainty | `fa_inputs`, `fa_baseline`, `fa_contracts` — Journey/Topic respectively | Baseline and contract histories; C0/C1/C4 matrices and catalogue sources. Inspection/readability is not permission to decode. |
| Native facts -> release-matched conventions -> user completion; units/kind/instantaneous support, source assertions, unknown scaling/default-fatal vs justified opt-in | `fa_inputs`, `configuration_file`, `fa_contracts` — Journey/Topic | Contract/C1 histories, source assertions, missing-FMULTM/FMULTE cases. No identity scaling from silence, filename or plausible values. |
| Snyder (1987), DOI `10.3133/pp1395`; tangent-Lambert equations, southern cone, declared radius, library/CF origin translation and native CI/C/E indices | `fa_inputs#fa-geometry-method`, `fa_geometry` — Journey retains method; Topic owns geometry | Input/geometry histories and C2. Keep `2e-5 degree` header bound distinct from `2e-11 degree` independent equation agreement, `1e-7 m` canonical axes and `1e-10 degree` angular axes. |
| Source-axis association, ties/descending storage, requested vs selected point, coverage and padding | `fa_geometry`, `output_files` — Topic/Journey | Geometry history: `1e-5 m` consistency tolerance, `64 * machine_epsilon * coordinate_magnitude` roundoff; first storage-index tie; no ground-distance claim. |
| Exact-common default, warnings and complete exclusions, strict/cycle/state-clock failures; independent source grids and moving centres | `fa_inputs`, `fa_surface`, `configuration_file`, `output_files` — Journey/Topic | Surface/C3 histories; shared-target signature means coordinates, not data identity. Keep explicit resolution/budget ordering and exact coordinate equality. |
| Point-sampled bilinear continuous production fields without area conservation, categorical explicit method, separate masks/undefined/support/extension/real zeroes | `fa_inputs`, `fa_surface`, polar topic guides — Journey/Topic | Surface/C1/C3 histories; exact dense/coordinate checks versus `1e-9` scalar interpolation tolerance. No implicit experimental-method switch or support filling. |
| Explicit record associations and mass/interface labels/native indices, `A_Pa=PAHYBR*PREFER`, dimensionless B, full coefficient axis through sparse selection | `fa_atmosphere`, `configuration_file`, `output_files` — Topic/Journey | Atmosphere/C2 histories; 100000-Pa independent fixture distinguishes hard-coded 101325-Pa errors. No inferred physical pressure/height, layer/tile axes or CF formula terms. |
| Vector sampling vs basis/frame, physical components, neighbours before crop, selected-only rotation/magnitude, unresolved stagger/map scaling | `fa_atmosphere`, existing wind/polar guides — Topic | Atmosphere history: `5e-4 m/s` bound applies to the specified 1-km/8-km/5-m/s fixture, not general accuracy. |
| Spectral coefficients not values, native -91 separate, required coefficient/transform/mask/reference contracts | `fa_spectral`, `fa_baseline` — Topic | Spectral history and `fa_p4.yaml`: double-Fourier equations, signs, counts, `rtol=0, atol=5e-13`, observed `5.551115123125783e-15` maximum on 36 small modes. Preserve this candidate evidence developer-side; do not advertise spectral extraction. |
| Source heat energy vs flux, rain accumulation vs rate, RH vs specific humidity, geopotential vs height, unresolved stress interval labels, original layer/patch/tile identity | `fa_surface`, `fa_inputs`, relevant output definitions — Topic/Journey | Surface history and `fa_p3.yaml` field-priority catalogue. No automatic rates/deaccumulation/sign changes/averages/diagnostics. |
| Fresh same-Python workers vs optional override, native lifetime failures, point/thread/timeout limits vs actual memory, per-product atomicity/status and ordinary readers | `fa_environment`, `fa_inputs`, `output_files`, optional HPC topic — Journey | Environment/C4/C5 histories; old overlay fault remains unlocalized, clean controls do not prove universal MPI/wheel incompatibility. Historical resource timings/counts stay here. |

These are preservation obligations, not a new scientific validation or promotion.
Publisher/reference verification recorded in old pages has not been independently
repeated for this freeze. Release-matched real units/scaling/support/Earth models,
native -91 diagnosis, spectral references, additional types/intervals and human
scientific review remain unresolved; no editor may erase them to simplify prose.

## Visible strings, examples and packaged/generated surfaces

| Old surface / observed reference | Destination, owner and check |
| --- | --- |
| `example/config_file/coupled_fa.yaml:3–5` (`C1/C2/C3` links) | Descriptive `fa_inputs`, `fa_geometry`, `fa_surface` references — Surface, step 4. Keep all unit/scaling/source/radius settings; schema-only validate. Included verbatim in `fa_inputs`, so comments are also published. |
| `example/config_file/coupled_cyclone_polar.yaml:3` (`C3` link) | Current coupled sampling/producer limits — Surface, step 4; schema-only validate. |
| `example/config_file/coupled_arome_fa_polar.yaml:7` (`C4` migration) | Current alias/configuration guidance — Surface, step 4; schema-only validate. |
| `example/config_file/arome_fa_native_cubes.yaml:1,21` (`P5/C2`) | Native-cube/geometry topics — Surface, step 4; schema-only validate. Also literal-included in `fa_atmosphere`. Preserve original names such as `S003TEMPERATURE`. |
| Other tracked `example/` files; `environment.yaml`; `environment-hpc.yaml` | No roadmap references found; Surface audits links/comments, preserves dependencies and settings. Do not recopy private fixture payloads. |
| `CHANGELOG.md:5,23,43,59` (`C4`, `C1--C3`, `C0`, `P4`) and surrounding historical assertions | Descriptive behavior/compatibility/limits in release entries — Surface, step 4. [Original unreleased FA excerpt](entry_points_history.md) preserves unique chronology. Keep software/release history. Timing stages and harmonic phase elsewhere are legitimate. |
| `src/frameit/io/fa_contracts.py::SPECTRAL_GATE` (line 18) | Descriptive spectral support reference — Surface, step 4. Used by `native_descriptor` and `fa_worker._describe`; appears in descriptor reasons, selected-input failure, inspection/preflight/provenance. Keep the gate and coefficient-contract/independent-native-grid requirements. Existing `test_fa_spectral.py` failure/descriptor/transfer cases own verification. No wording change in this freeze. |
| CLI parser/help/validation; `core/configuration.py`; `io/fa_backend.py`; `io/fa_epygram.py`; `src/frameit/templates/` and `presets/` | No additional roadmap-visible message found. `--fa-python` help correctly says optional. Surface rechecks generated full init, alias/missing-dependency messages and actual preflight after edits; preserve machine-readable configuration/provenance. |
| `io/fa_contracts.py` module docstring/comment (`P0`), `io/fa_epygram.py::check_surface_layout` docstring (`C1`), testing probe docstrings/errors (`C0/P4`) and test names | Developer implementation/investigation evidence; no current public autodoc/viewcode page found. Surface owns any actual publication exposure; no mass-renaming. Explicit probes are developer entry points, not normal supported extraction recipes. |
| `src/frameit/testing/catalogs/fa_p0.yaml`, `fa_p3.yaml`, `fa_p4.yaml`, `fa_p5.yaml`, `fa_c0.yaml`–`fa_c5.yaml`, `fa_environment.yaml` | Retain existing package assets and consumers (including runtime CI and `pyproject.toml` package-data) unchanged. Developer index/records own evidence links. Public includes of P0/P3/P4/C0–C5/environment ledgers go in steps 2/3. `fa_p5.yaml` is named in atmosphere prose. |
| `src/frameit/templates/arome.yaml`, `mesonh.yaml` / generated `frameit init ... --full`; README used as package long description | Journey/Surface own rendered prose, links and schema examples; retain all keys/defaults. Catalogue filenames and test/package IDs are machine contracts, not targets for cosmetic renaming. |
| `docs/source/conf.py` | Publication owner: `source` is the public root; `exclude_patterns` currently only `_build`, `Thumbs.db`, `.DS_Store`. Autodoc/autosummary/viewcode extensions are enabled, but no directives currently expose these FA modules. Do not import/include the developer archive. |
| `.github/workflows/docs.yml`, `docs/Makefile`, `docs/docs-requirements.txt`, `docs/make.bat` | Publication owner: retain Sphinx/RST and artifact `docs/build/html`; CI uses Python 3.12, Sphinx 8.1.3, theme, then `pip install .`, `make -C docs html`. Current build is not strict and does not explicitly clean old artifacts. Reference YAML's Sphinx 9.2.0 is a different environment. |
| HTML pages/titles/navigation, `searchindex.js`, `_sources/*.rst.txt`, `objects.inv`, any `_modules`/autodoc output and uploaded artifact | Publication owner checks all of these after steps 2–4. Current build publishes six stage pages, their downloaded sources and literal-included catalogues. Deleting only navigation or reusing a dirty HTML directory fails acceptance. |

## Contextual exclusions: retain actual identities

- `C0`/`C1` in SURFEX native character types (alongside N0/N1/L0/L1/X0/X1/X2/T0)
  describe data, including unsupported physical C1 arrays. They are not the
  EPyGrAM C0/C1 development checkpoints. `fa_worker.typed_metadata` uses actual
  `C0` type identity.
- `SFX.TG1P1`/`SFX.WG1P1` are native record IDs; `P1` is part of their identity,
  not the descriptor-development phase. Preserve all exact original IDs/indices.
- `C2` in `polar_projection/scientific_qualification.rst` and
  `testing/analytic_vortices.py` describes smoothness of the quintic/regularization,
  not the geometry-adapter increment. Harmonic phase, tropical stages, computation
  stages and grid increments are also legitimate technical language.
- Schema/protocol/library versions, scientific citations, catalogue keys and
  named test profiles (`core` included) retain their current meanings. Searches
  identify candidates for contextual review; no global token replacement or broad
  directory waiver is an acceptance check.

## Links and publication acceptance owned by step 5

1. Recheck every table row after the later edits. Public links must resolve to
   descriptive topics; keep neutral anchors where practical. No public link,
   footer, include, download, search entry or source-code link may route to this
   archive. Developer-to-public and developer-to-catalogue links remain allowed.
2. Delete the six stage sources and their toctree entries together in step 3.
   Repair README, `fa_inputs`, `fa_atmosphere`, `fa_geometry`, `fa_surface`,
   `fa_contracts`, `output_files`, `configuration_file`, stage-to-stage links and
   the four examples; steps 2/4 own the indicated incoming surfaces.
3. Build to a **brand-new designated directory** using
   `LC_ALL=C LANG=C sphinx-build -q -W --keep-going -b html docs/source "$FRESH_DOCS_OUTPUT"`.
   `-E`/`-a` do not remove stale HTML. Apply the same freshness/strictness to CI
   without changing its upload path or deployment responsibility.
4. Inspect the whole artifact, including downloaded source, search, inventory,
   any generated module pages and literal-included examples. Review legitimate
   codes contextually. Neither absence from the sidebar nor a passing Sphinx exit
   alone proves this boundary. Check that removed old URLs are absent as files.
5. Run `git diff --check`, schema-only validation of edited examples and existing
   affected failure-contract tests if a message changes. No numerical benchmark,
   dependency update, production dataset run or upload is required for prose edits.
   Report hosted/Python-3.12 checks separately from local results.
