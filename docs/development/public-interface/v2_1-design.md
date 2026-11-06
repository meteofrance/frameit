# YAML v2.1 public contract — G1 approved

**Status: G1 APPROVED (2026-11-05); implementation receipts are in rc-readiness.md.**
Baseline: `288c532a03a0805c7cfe50ab049b019b1b676e8d` on `dev_md`;
scientific implementation unchanged from `212fcca`. Task 2's capability/evidence
matrix is in [rc-readiness.md](rc-readiness.md). The approved external plan's
design/safeguards are authoritative; this record supplies its missing exact
interface contract. The maintainer approved the complete proposal at `ab0be01`
with the reply **"Approved"** on 2026-11-05. This authorizes Tasks 4 onward under
the existing plan, not G2, scientific sign-off, publication or deployment. Do not
advertise the commands as implemented until their implementation is verified.

## 1. Intent, approach and decisions requested

Make extraction/configuration understandable to researchers without changing
numerical methods, source interpretation, units, masks, time support, sampling,
diagnostic selection or scientific output schemas. Keep the current Python
resolver → runtime/presets → adapters/processing → writers boundaries, Sphinx
and ordinary output readers. No plugin framework, legacy converter, application,
new diagnostic, producer admission or dependency is proposed.

The umbrella plan already selected a narrow schema translation rather than a
runtime rewrite, and a guided first run followed by task-oriented guides rather
than either a monolithic handbook or disconnected recipes. Within that approach:

- **Recommended:** keep clear names, remove compatibility synonyms, and rename
  only misleading controls/values, with explicit model-specific definitions.
  This gives a small, reviewable translation into the existing numerical runtime.
- Retaining every old name with better prose has less code churn but leaves a
  NetCDF-named switch controlling Zarr and wind-named controls selecting currents.
- A new general vector/processing hierarchy would separate more concerns but
  add scope and abstractions without another demonstrated task; not recommended.

### G1 decisions (approved in full on 2026-11-05)

1. Approve the full inventory below, including unchanged entries, strict string
   version, removals, source inheritance, defaults and CLI/effective records.
2. Approve `domain.width_km`, `pressure_wind`, `polar.variables: extracted`,
   `output.export.enabled`, `output.backend` and `output.netcdf_format`.
3. Approve generic `output.cartesian.horizontal_vectors: native/earth_centered`.
   `earth_centered` is a representation request, **not** a universal ocean
   algorithm: atmospheric mass/Earth, CROCO rho/Earth where qualified, and NEMO
   component analysis still rejected. It does not imply physical-depth collocation.
4. Approve removal of the public scalar wind-frame fallback in favour of explicit
   `input.wind_pairs`, FA backend value `native`, and the `levels: all` synonym.
   These are interface/admission breaks, not permission to change rotations or
   stored-level selection. Internal numerical structures are a separate boundary.
5. Approve the generator/catalogue, including the instructional AROME-adapter
   fixed-scalar starter, exact coupled defaults and rejection rules in §6.
6. Approve explicit `output.overwrite: false` in **all** new starters. The runtime
   default stays true for equivalence; the safer generated requests differ from
   the old AROME/Meso-NH starter defaults and must not be slipped in unnoticed.
7. Approve the content/figure map in §7. This is not G2 visual/editorial approval.

### Scientific uncertainties / boundaries — no guessed resolutions

- Neither schema naming nor matching timestamps establishes equivalence of an
  ocean mean and an atmospheric snapshot. `common` remains the global default.
  `preceding_hour` stays an explicit AROME/NEMO NetCDF-only convention; existing
  examples choosing it keep that choice during translation. New ordinary coupled
  starters explicitly choose `common`; users of half-hour means must select and
  justify another admitted policy themselves, not receive a silent fallback.
- The current global horizontal selector applies to all sources. This proposal
  preserves that limitation; it does **not** add per-source output overrides.
  Native currents/stresses do not become winds. NEMO analysis and CROCO stress,
  wet/dry or physical-depth analysis remain unqualified.
- `vertical_velocity: interfaces/mass` is retained as a method/location control,
  not renamed into a claim about all models. Meso-NH W has the existing native
  interface/mass preparation; NEMO W retains depthw and rejects mass analysis;
  CROCO W retains its declared stored sigma location. Ocean polar processing
  bypasses atmospheric W preparation. A universal vertical transformation would
  be a separate scientific feature, not this rename.
- `levels: physical` means the declared **non-halo index domain**, not conversion
  of labels to physical metres. NEMO/CROCO value selection remains exact; the
  current atmospheric matching tolerances remain unchanged. No new pressure,
  altitude or physical-depth diagnosis is authorized.
- FA unit/scaling/Earth-model evidence, CROCO angle/mask authority and SURFEX
  sentinel/support/unit evidence remain required. This audit did not independently
  verify the actual real producers, flux sign/basis, SURFEX averaging/reset setup,
  unknown NEMO mesh/angles or experimental tracker qualification.
- Advanced generated multi-field seeds/motion/gravity are currently illustrative
  values, not producer facts. §6 proposes no advanced experimental starter that
  guesses them. Existing numerical methods remain manually configurable; removal
  of those generator selections needs G1 approval, not deletion of the methods.

## 2. Audit evidence and acceptance contracts

Read the complete validator branches in `core/configuration.py` (including
dynamic requests, wind pairs, FA records/cubes and named sources), `to_runtime`,
resolved records/origins and `write_template`; YAML/mapping constructors and
preset application in `core/settings_class.py` and `io/loader.py`; parser and
inspection generation in `cli.py`; options/provenance/export in `core/execution.py`.
Also inspected `core/coupled.py`, `core/time_association.py`, ocean/SURFEX adapters,
`processing/requests.py`, wind collocation/reference, polar sampling/coverage/cache
validators, Zarr encoding, tracker options/presets, templates, examples, matrix
catalogue/recipe/service generation and current documentation/navigation.

All `src/frameit/...` paths here are repository-relative beneath `src/frameit/`.
The inventory has **117 DEFAULTS leaf/open-map paths**, plus the dynamic paths
in §4 that DEFAULTS does not describe. A default entry alone is not proof that
every value is admitted: downstream conditional contracts remain binding.

Legend for inventory tables:

- `=`: retain that exact path and accepted values unless a value mapping is stated.
- Default column: current `DEFAULTS` value, unchanged unless `→` is shown. `null`
  is not a scientific zero. Required/conditional requirements override defaults.
- Scope: **G** run-global; **I** independent input/source; **P** polar settings,
  inherited by named sources then explicitly overridden. Source overrides are
  exactly the paths in §5, not every G key.
- Consumer/check references below form part of **every** row; all also require
  type/unknown-key/retired-alias rejection and effective-record/replay coverage.
  They are required future checks, **not tests claimed to exist/pass for v2.1**.

| Code | Consumers and required equivalence/failure checks |
| --- | --- |
| C | Shared resolver, YAML/mapping constructors, CLI. Reject retired/mixed/duplicate/unknown keys before dataset access/output creation; exact version and path/precedence tests. |
| I | `io/loader.py`, `core/preflight.py`, model adapters. Pin inventory/order/exclusions, units, geometry and lazy selected input; fail incompatible scientific metadata. |
| F | FA options/isolated reader/contracts. Pin field identity, units, native scaling, time support, record/cube dependencies, helper identity and bounded failure, without optional imports on base paths. |
| W | Wind reference/collocation, CROCO/NEMO adapters, extraction. Independent known-angle/staggered/zero/missing/window results; no ocean wind diagnostics or changed basis/defaults. |
| T | Selected tracker and preset fields. Preserve parameters, convergence/failure/shortened-track behavior, seed requirements and independent existing oracles. |
| V | `processing/requests.py`, adapters and selection. Pin stored indices/order/labels, exact ocean values, atmospheric tolerances, halo domains and retained coordinate dependencies. |
| P | Polar axes/coverage/cache/regrid. Pin exact axes/geography, independent scalar/vector/zero/missing/support thresholds and optionality; no conservation claim. |
| O | Execution options, NetCDF/Zarr writers and run state. Pin requested products, ordinary-reader values/metadata, layout, overwrite/lock/partial/failure behavior and backend optionality. |
| R | Runtime resource resolver/execution scopes. Pin concurrency caps/default origins, invalid resource failures and numerical equivalence; measure without changing precision. |
| M | Existing metadata/provenance/status builders. Pin annotations versus scientific controls, effective selections/origins, significant warnings and portable records. |

## 3. Complete static old-to-proposed inventory

### Identity and input

| Current path | Proposed path/value | Type / accepted values / meaning and units | Default / origin | Scope; consumers/checks |
| --- | --- | --- | --- | --- |
| `schema_version` | required string `"2.1"` | Exact string; reject missing, bool, numeric and every retired/unknown version | required; current D=2 → no version inference | G; C |
| `model` | = | Required `arome/mesonh/nemo/croco`; adapter identity, not proof of producer | required; D=`arome` does not satisfy omission | I; C,I |
| `run.name` | = | Nonempty identifier; no `/`, `\`, `.` or `..` path tokens | `analysis` | G; C,O |
| `run.description` | = | String annotation, not a method choice | `""` | G; M |
| `input.directory` | = | Nonempty YAML-relative directory; also base for discovery exclusions | `./data` | I; I |
| `input.pattern` | = | Relative glob/filename or null; exactly one nonempty pattern/files for a single source | null; explicit selection required | I; I |
| `input.files` | = | Ordered path-string list or null; each file required, paths YAML-relative | null; alternative to pattern | I; I |
| `input.exclude` | = | Glob-string list; basename, absolute or input-directory-relative matches | `[]` | I; I |
| `input.format` | = | `grib/netcdf/fa` or null; null content detection, never identity from name alone | null; resolved content origin recorded | I; I,F |
| `input.grid_spacing_m` | = | Positive finite scalar metres or null; nominal override, not permission to bypass grid checks | null; metadata/geodesic inference | I; I |
| `input.duplicate_time_policy` | = | `first/last` for ordinary time-series duplicate precedence; not a way to legalize duplicate preceding-hour physical records | `first` | I; I |
| `input.wind_reference_frame` | **remove** | Old scalar `earth/grid/null` compatibility fallback; replace by exact pair/group declarations below, never guess a pair | null → absent; manual upgrade for explicit uses | I; C,W |
| `input.wind_pairs` | = | List of exact per-group source component/basis/rotation declarations (§4); not ocean-current reinterpretation | `[]` | I; W |
| `input.netcdf.engine` | = | `h5netcdf/netcdf4/scipy` input reader, not output backend | `h5netcdf` | I; I |
| `input.netcdf.chunks` | = | Native-dimension → positive integer/-1; `{}` retains backend-preferred lazy chunking | `{}` | I; I,R |
| `input.netcdf.file_layout` | = | `time_series/variables`: concatenate prepared snapshots versus exact same-grid complementary shards | `time_series` | I; I |
| `input.netcdf.surfex_fields` | = | Unique list from `SST,SSS,H_SEA,LE_SEA,FMU_SEA,FMV_SEA,FRAC_SEA`; only explicit selected Meso-NH NetCDF time-series interpretation | `[]`, raw opt-out | I; I,W,M |
| `input.fa.profile` | = | `arome_history/surfex_history` or null; required when format=fa, model=arome | null | I; F |
| `input.fa.subdomain` | = | `CI/C`, no spectral extension | `CI` | I; F |
| `input.fa.earth_radius_m` | = | Positive finite metres or null; projected FA requires evidenced source radius | null, no fitted default | I; F |
| `input.fa.field_metadata` | = | Exact record/logical-cube definitions (§4); source units/meaning, not conversion requests | `{}`; required for selected physical inputs, including virtual-speed companions | I; F |
| `input.fa.expected_source` | = | Optional assertions for `PROGRAM,VERSION,BUG,MASDEV,BUGFIX`, not replacements for missing native facts | `{}` | I; F |
| `input.fa.backend` | `epygram` only | Remove deprecated `native` alias; same maintained isolated decoder | `epygram` | I; C,F |
| `input.fa.python_executable` | = | Nonempty path or null; helper runtime with required stack; preserve symlink spelling | null → active interpreter | I; F |
| `input.fa.native_cubes` | = | Explicit ordered native-record/vertical/sampling definitions (§4) | `{}` | I; F,V |
| `input.fa.max_points` | = | Positive integer stored points per native transaction, not bytes or exact RSS | 20000000 | I; F,R |
| `input.fa.timeout_seconds` | = | Positive finite seconds per isolated transaction | 120.0 | I; F,R |
| `input.sources` | = | Named model/input/variables/polar mappings only; no nested sources (§5) | `{}` | G; C,I |
| `input.time_alignment` | = | `common/strict/preceding_hour`; exact association contracts, never interpolation | `common`; only meaningful with named sources | G; I,T,M |

### Tracking and domain

| Current path | Proposed path/value | Type / accepted values / meaning and units | Default / origin | Scope; consumers/checks |
| --- | --- | --- | --- | --- |
| `tracking.source` | = | Named reference source or null for single source | null; required for coupled | G; C,T |
| `tracking.method` | `wind_pressure` → `pressure_wind`; others = | `pressure_wind/pressure_centroid/multifield_vortex/fixed_box/prescribed_track/utrack`; only fixed/prescribed ocean/FA references | `wind_pressure` → `pressure_wind`, same algorithm | G; C,T |
| `tracking.wind_pressure.search_half_width_km` | `tracking.pressure_wind.search_half_width_km` | Positive finite square search **half-width**, km | 100.0 | G; T |
| `tracking.wind_pressure.refine_half_width_km` | `tracking.pressure_wind.refine_half_width_km` | Positive finite square refinement **half-width**, km | 50.0 | G; T |
| `tracking.wind_pressure.initial_guess` | `tracking.pressure_wind.initial_guess` | null or complete latitude/longitude/search-radius mapping (§4); first-time restriction only | null | G; T |
| `tracking.fixed_box.center.latitude` | = | Finite degrees north [-90,90], required for selected fixed box | null, not an automatic centre | G; T |
| `tracking.fixed_box.center.longitude` | = | Finite degrees east [-180,180], required for selected fixed box | null | G; T |
| `tracking.prescribed_track.file` | = | YAML-relative path or null; required when selected, exact supported timestamps | null | G; I,T |
| `tracking.prescribed_track.time_name` | = | String source coordinate name | `time` | G; I,T |
| `tracking.prescribed_track.latitude_name` | = | String source latitude name | `latitude` | G; I,T |
| `tracking.prescribed_track.longitude_name` | = | String source longitude name | `longitude` | G; I,T |
| `tracking.utrack.weights_file` | = | YAML-relative path or null; required when selected, never download automatically | null | G; T |
| `tracking.utrack.use_gpu` | = | Strict Boolean, explicit resource choice | false | G; T,R |
| `tracking.utrack.batch_size` | = | Positive integer batch samples | 16 | G; T,R |
| `tracking.pressure_centroid.convergence.max_iterations` | = | Positive integer centre iterations | 15 | G; T |
| `tracking.pressure_centroid.convergence.tolerance_m` | = | Positive finite metres for centre convergence | 250.0 | G; T |
| `tracking.pressure_centroid.motion.max_iterations` | = | Positive integer coupled-motion iterations | 50 | G; T |
| `tracking.pressure_centroid.motion.solver` | = | `aitken/fixed`; same declared solver | `aitken` | G; T |
| `tracking.pressure_centroid.motion.relaxation` | = | Finite fraction (0,1] | 0.25 | G; T |
| `tracking.pressure_centroid.motion.tolerance_m` | = | Positive finite metres, motion-centre convergence | 250.0 | G; T |
| `tracking.pressure_centroid.sampling.r80_max_distance_km` | = | Positive finite km for existing R80 search limit; not the 500-km reference ring | 250.0 | G; T |
| `tracking.pressure_centroid.sampling.radial_step_km` | = | Positive finite km internal radial sampling, not polar export spacing | 2.5 | G; T |
| `tracking.pressure_centroid.sampling.azimuth_step_deg` | = | Finite degrees (0,180), internal tracker sampling | 5.0 | G; T |
| `tracking.multifield_vortex.profile` | = | Experimental `all_no_thick` only | `all_no_thick` | G; T |
| `tracking.multifield_vortex.on_track_loss` | = | `stop/error`, preserving incomplete/failure semantics | `stop` | G; T,O |
| `tracking.multifield_vortex.seed.latitude` | = | Required finite degrees north, 0 < absolute value < 90 | null | G; T |
| `tracking.multifield_vortex.seed.longitude` | = | Required finite degrees east [-180,180] | null | G; T |
| `tracking.multifield_vortex.seed.time` | = | ISO timestamp string or null; preserve existing first-time selection contract | null | G; T |
| `tracking.multifield_vortex.seed.motion_u_m_s` | = | Required finite eastward initial motion, m/s (zero permitted if explicitly chosen) | null | G; T |
| `tracking.multifield_vortex.seed.motion_v_m_s` | = | Required finite northward initial motion, m/s | null | G; T |
| `tracking.multifield_vortex.mnh_gravity_m_s2` | = | Positive finite m/s² or null; explicit evidenced Meso-NH height convention required | null | G; T |
| `tracking.multifield_vortex.numerics.analysis_step_km` | = | Positive finite km search grid spacing | 25.0 | G; T |
| `tracking.multifield_vortex.numerics.refinement_km` | = | Positive finite km, not greater than analysis_step_km | 2.5 | G; T |
| `tracking.multifield_vortex.numerics.max_iterations` | = | Positive integer iterations | 20 | G; T |
| `tracking.multifield_vortex.numerics.minimum_support` | = | Finite fraction (0,1] | 0.8 | G; T |
| `tracking.multifield_vortex.numerics.minimum_samples` | = | Positive integer samples | 16 | G; T |
| `tracking.multifield_vortex.quality.minimum_parameters` | = | Positive integer, at most nine existing parameter definitions | 2 | G; T |
| `tracking.multifield_vortex.quality.pressure_rise_pa` | = | Positive finite Pa, existing pressure-quality criterion | 50.0 | G; T |
| `tracking.multifield_vortex.quality.vt850_min_m_s` | = | Positive finite m/s, existing circulation-quality criterion | 1.5 | G; T |
| `tracking.multifield_vortex.quality.max_separation_km` | = | Positive finite km, accepted parameter separation | 425.0 | G; T |
| `tracking.multifield_vortex.quality.max_speed_m_s` | = | Positive finite m/s translation threshold, not a current/wind clipping rule | 30.866666666666667 | G; T |
| `tracking.multifield_vortex.quality.speed_check_interval_hours` | = | Positive finite hours, existing translation-quality interval | 6.0 | G; T |
| `domain.size_km` | `domain.width_km` | null or exact positive finite `{x,y}` full widths in km; never halve/double on translation | null → full domain | G; T,V,P |
| `domain.edge_policy` | = | `pad_nan` only; retain centred geometry/missing padding | `pad_nan` | G; V,O |
| `variables` | =; `levels: all` → `stored` | Source-native group mapping (§4); no discovery-based selection | `{}` | I; V,W |

### Polar sampling

| Current path | Proposed path/value | Type / accepted values / meaning and units | Default / origin | Scope; consumers/checks |
| --- | --- | --- | --- | --- |
| `polar.enabled` | = | Strict Boolean; no auto-selection from available fields/dependencies | false | P; P |
| `polar.shared_target` | = | Strict Boolean coupled-target choice; source values must agree globally | false | G; P,I |
| `polar.variables` | `all` → `extracted`; mapping = | `extracted` means extraction selections, not every source field; or explicit group/name subset | `all` → `extracted` | P; V,P |
| `polar.radial_step_m` | = | Positive finite metres or null; default native spacing, shared coarsest participant; no finer-than-source step | null, record resolved origin | P; P |
| `polar.azimuth_step_deg` | = | Finite degrees (0,120] or null; mutually exclusive with count; effective spacing is 360/ceil(360/request) | null → automatic outer-ring spacing if count also null | P; P |
| `polar.azimuth_count` | = | Integer ≥3 or null; endpoint-exclusive periodic samples | null → automatic if step also null | P; P |
| `polar.interpolation_method` | = | `bilinear/nearest_s2d`; explicitly appropriate categorical method required | `bilinear`, point sampling not conservative | P; P |
| `polar.missing_data_policy` | = | `strict/renormalize`; retain exact support semantics | `strict` | P; P |
| `polar.min_valid_weight_fraction` | = | Finite fraction [0,1], relevant to declared coverage policy | 0.5 | P; P |
| `polar.weight_zero_tolerance` | = | Finite fraction [0,1e-6); negligible stencil-weight criterion, not data smoothing | 1e-14 | P; P |
| `polar.source_halo_points` | = | Integer ≥1, native stencil halo points | 1 | P; P |
| `polar.ellipsoid` | = | String accepted by pyproj.Geod; validity checked without source-field reads | `WGS84` | P; P |
| `polar.max_points` | = | Positive integer target-point budget, including selected time count where planned | 2000000 | P; P,R |
| `polar.plan_cache.entries` | = | Nonnegative integer retained plans; zero disables retention | 8 | P; P,R |
| `polar.plan_cache.max_bytes` | = | Nonnegative integer estimated retained-plan bytes, not full-process memory limit | 134217728 | P; P,R |
| `polar.chunks` | = | Output dimension → positive integer/-1; excludes internal `x_box,y_box,locations,dummy,theta_deg` names | `{}`, existing automatic chunks | P; P,R |
| `polar.profile` | = | Strict Boolean execution/timing instrumentation, not extra diagnostics | false | P; P,M |

### Output, execution and annotations

| Current path | Proposed path/value | Type / accepted values / meaning and units | Default / origin | Scope; consumers/checks |
| --- | --- | --- | --- | --- |
| `output.cartesian.horizontal_winds` | `output.cartesian.horizontal_vectors`; `mass_earth` → `earth_centered` | `native/earth_centered`; preserve each adapter's admitted sampling/basis/units and rejections (§1) | `mass_earth` → `earth_centered` | G; W,O |
| `output.cartesian.vertical_velocity` | = | `interfaces/mass`, existing model-specific W representation, not arbitrary depth conversion | `interfaces` | G; W,V,O |
| `output.polar.vertical_velocity` | = | `interfaces/mass` for atmospheric W preparation; ocean native sigma/depth contracts remain separate | `mass` | G; W,V,P |
| `output.directory` | = | Nonempty YAML-relative output root; CLI override launch-relative | `./output` | G; C,O |
| `output.export.netcdf` | `output.export.enabled` | Strict Boolean product-export gate for **both** NetCDF and Zarr; not processing enablement | true | G; O |
| `output.export.cartesian` | = | Strict Boolean Cartesian product selection, not vector representation | true | G; O |
| `output.export.polar` | = | Strict Boolean polar product selection; does not enable polar computation | true | G; O,P |
| `output.compression.level` | = | Integer 0..9, existing lossless NetCDF/Gzip level; 0 disables compression | 1 | G; O |
| `output.compression.coordinates` | = | Strict Boolean coordinate compression, no precision change | false | G; O |
| `output.engine` | `output.backend` | `netcdf4/h5netcdf/zarr`: selected writer/storage backend, not source format | `netcdf4` | G; O |
| `output.format` | `output.netcdf_format` | Current NetCDF accepts only `NETCDF4`; Zarr currently ignores any string here. Proposed `NETCDF4` only; describes NetCDF encoding, not Zarr version; retained default has no effect for Zarr | `NETCDF4` | G; O |
| `output.unlimited_time` | = | Strict Boolean NetCDF unlimited dimension; does not change time meaning or Zarr values | true | G; O |
| `output.overwrite` | = | Strict Boolean run-root replacement policy; never source overwrite authorization | true; starters explicitly false, approval required | G; O |
| `output.max_workers` | = | Positive integer export-process cap or null; actual allocation capped by runtime | null → resource resolver | G; O,R |
| `output.synchronous_export` | = | Strict Boolean controlling-process export, not an algorithm | false | G; O,R |
| `output.zarr_chunk_size` | = | Dimension → positive integer **elements**, not bytes; backend v3 defaults below | `{}` | G; O,R |
| `output.zarr_shard_size` | = | Dimension → positive integer elements; multiples of chunk sizes on overlapping keys | `{}` | G; O,R |
| `output.institution` | = | String output attribution; preserve existing value, do not invent affiliations | `LACy, Université de La Réunion, CNRS, Météo-France` | G; M,O |
| `execution.dask_scheduler` | = | `threads/synchronous` | `threads` | G; R |
| `execution.dask_workers` | = | Positive integer or null → CPU-allocation-aware default | null | G; R |
| `execution.native_threads` | = | Positive integer native-library thread cap | 1 | G; R |
| `execution.require_complete_tracking` | = | Strict Boolean: fail instead of accepting explicitly incomplete trajectory | false | G; T,R,O |
| `logging.level` | = | `DEBUG/INFO/WARNING/ERROR` | `INFO` | G; M,R |
| `metadata.ocean_model` | = | String annotation, not an adapter selector/capability declaration | `""` | G; M |
| `metadata.wave_model` | = | String annotation, not wave-model support | `""` | G; M |
| `metadata.extra` | = | User mapping annotations, not a route to undeclared scientific options | `{}` | G; M |

## 4. Dynamic keys, conditional values and defaults

These complete the inventory beyond the 117 static rows. `*`, `[]`, `<group>`,
`<record>`, `<cube>`, `<dim>`, `<id>` are descriptive placeholders, not literal
wildcard selection or permission for other keys. Named-source copies of I/P
paths use these exact same validators, units and defaults. Unmentioned types
are invalid; Boolean values never count as integers/numbers.

| Current path / proposed mapping | Meaning, accepted values, defaults and scope | Consumers / required checks |
| --- | --- | --- |
| `domain.size_km.x`, `.y` → `domain.width_km.x`, `.y` | Both positive finite km; both required together if width map exists; no default component | G; T,V,P; identical old/new crop and polar radius=half shorter full width |
| `variables.<group>.names` = | Required nonempty list of source variable strings or the existing atmospheric virtual `wind_speed` request; `<group>` is `surface` or an admitted native vertical group, not an arbitrary physical coordinate promise | I; V,W; missing/ambiguous quantity failure, speed-only selection and selected-only payload |
| `variables.<group>.levels` = except `all` removed | Default `stored`; strings `stored/physical`, or exactly one `indices/values` mapping. No null strategy or mixed strategies | I; V; same stored/halo rules, not physical-depth diagnosis |
| `variables.<group>.levels.indices` = | Nonempty ordered list of nonnegative integers, zero-based stored positions; bounds checked against source | I; V; sparse/reordered selection/NaNs and native source index metadata |
| `variables.<group>.levels.values` = | Nonempty finite numeric list in the source coordinate's declared units. Ocean exact matches; preserve atmospheric reader/preflight tolerances | I; V; known source values and unavailable-level failure |
| `polar.variables.<group>.names` = | Nonempty name list (including admitted atmospheric `wind_speed`), subset of extracted selections in same group; inherits selected levels; no polar-levels key | P; V,W,P; reject extra group/variable/levels and no implicit companion export |
| `input.netcdf.chunks.<dim>` = | Positive integer or -1, native input dimension labels; default none per dimension | I; I,R; native chunks/laziness/culling |
| `polar.chunks.<dim>` = | Positive integer/-1, polar output labels, reject internal dimensions listed in §3; default automatic | P; P,R; actual bounded tasks and numerically equal chunks |
| `output.zarr_chunk_size.<dim>` = | Positive integer elements. Current default min(axis length,128) for last two non-time axes; 1 otherwise, adjusted by gcd if explicit shard requires it | G; O; inspect actual v3 chunks in ordinary reader |
| `output.zarr_shard_size.<dim>` = | Positive integer elements; defaults chunk×8 for time, ×4 for last two non-time axes, ×1 otherwise. Explicit overlapping chunk/shard sizes must divide exactly | G; O; actual shard metadata/safe task alignment |
| `tracking.wind_pressure.initial_guess.latitude` → `tracking.pressure_wind.initial_guess.latitude` | Complete optional guess: finite [-90,90] degrees north, no default | G; T; first-record restricted search only |
| `tracking.wind_pressure.initial_guess.longitude` → `tracking.pressure_wind.initial_guess.longitude` | Complete optional guess: finite [-180,180] degrees east | G; T; first-record known centre / bad guess failure |
| `tracking.wind_pressure.initial_guess.search_radius_km` → `tracking.pressure_wind.initial_guess.search_radius_km` | Positive finite **circular radius** km, not a square half-width | G; T; exact radius inclusion/unsupported inputs |
| `input.wind_pairs[].group` = | Required nonempty group string; pair scope, not automatic quantity discovery | I; W; independent pairs in one dataset |
| `input.wind_pairs[].u`, `.v` = | Required distinct nonempty component-name strings; no duplicated component within group across declarations | I; W; required companions and output selection separate |
| `input.wind_pairs[].reference_frame` = | Required `earth/grid` basis; header contradictions fail, no silent override | I; W; known rotations and conflicting frame metadata |
| `input.wind_pairs[].rotation.method` = | Required for grid basis; `coordinate/geolocation/mesonh_projection`; no default for explicit pairs | I; W; named-angle/local-geodesic/source-projection sign oracles |
| `input.wind_pairs[].rotation.coordinate` = | Nonempty coordinate string required for `coordinate`; angle units/convention must be declared, never inferred from filename | I; W; missing/invalid coordinate and basis checks |
| `input.fa.expected_source.PROGRAM` = | Optional nonempty exact string assertion | I; F; missing/conflicting native facts fail |
| `input.fa.expected_source.VERSION`, `.BUG`, `.MASDEV`, `.BUGFIX` = | Optional nonnegative integers, no default asserted version | I; F; each source assertion checked independently |
| `input.fa.field_metadata.<record>.units` = | Required nonempty source-unit string; exact 1..16 ASCII native identifier or declared logical cube; no unit conversion merely from relabelling | I; F; actual scaling/units provenance |
| `input.fa.field_metadata.<record>.kind` = | Required `continuous/categorical` | I; F,P; categorical method rejection/explicit selection |
| `input.fa.field_metadata.<record>.temporal_kind` = | Required `instantaneous` only; no accumulated/mean profile admitted | I; F; actual native support evidence/rejection |
| `input.fa.field_metadata.<record>.allow_unscaled` = | Optional strict Boolean, default false. Explicit justified identity fallback only; warn/record observed fallback | I; F; missing scaling fails by default |
| `input.fa.field_metadata.<record>.long_name`, `.standard_name` = | Optional strings, no fabricated scientific definition; native facts take precedence over unresolved completion | I; F,M; contradicting source facts fail |
| `input.fa.native_cubes.<cube>.records` = | Required nonempty ordered exact record-string list, 4..16 ASCII chars, no glob chars, duplicates/reuse or self-reference | I; F,V; selected-record decoding only |
| `input.fa.native_cubes.<cube>.vertical_position` = | Required `mass/interface`; only arome_history cubes; `<cube>` must be 1..16 ASCII identifier with field_metadata, no reserved/prefixed fa_ name | I; F,V; exact native labels/dependencies |
| `input.fa.native_cubes.<cube>.sampling` = | Required `center` only, no new staggering inference | I; F,W |
| `input.fa.native_cubes.<cube>.vector_basis` = | Optional null/`earth/grid`; no default scientific basis supplied | I; F,W; declarations/native facts/companion consistency |
| `input.fa.native_cubes.<cube>.component_scaling` = | Optional null/`physical_velocity`; map-scaled/unknown components gated | I; F,W; no inferred map-factor correction |
| `input.sources.<id>.model` = | One admitted model; default top-level model; source ID starts letter, then letters/digits/_/- | G→I; C,I; reference-model agreement |
| `input.sources.<id>.input` = | Ordinary I settings, independent defaults/paths; no nested source tree or source time policy | I; C,I; reject nested sources and misplaced G options |
| `input.sources.<id>.input.time_alignment`, `.sources` → remove from child input | Current resolver can accept an irrelevant child common/strict policy or empty nested sources map. Proposed child input rejects either key even if empty/default; coupling policy and source membership belong only to the parent | G; C,I; fail misplaced controls before data access, without changing effective scientific requests |
| `input.sources.<id>.variables` = | Independent source request mapping, default `{}`; no top-level variables inheritance | I; C,V |
| `input.sources.<id>.polar` = | Ordinary P settings inherit top-level polar then override; shared_target must agree globally; field subsets source-local | P; C,P; exact inherited/overridden axes and budgets |
| `metadata.extra.<key>` = | Annotation mapping remains open, including nested serializable annotations; not processed as control fields and no scientific defaults drawn from it | G; M; round-trip annotation separate from effective scientific selections |

The atmospheric virtual `wind_speed` request remains runnable, including FA
speed-only selection: required declared U/V inputs and their source metadata are
loaded internally, existing speed equations/units/support are retained, and
unselected companions are not thereby exported. It is not a required native
`wind_speed` record or an ocean current-speed operation. Existing automatic
speed/other companions for selected atmospheric wind processing remain governed
by their current contracts, not silently removed or newly enabled by the rename.
Required future checks include `test_fa_cubes.py`'s independent 3-4-5 speed-only
case and existing atmospheric scalar/U-only/V-only/polar selection oracles.

Additional admission constraints preserved: logical FA cube identifiers cannot
reuse reserved coordinate/derived names (`time,x,y,level,level_w,latitude,longitude,
crs,source_i,source_j,forecast_period,wind_speed`) or duplicate native records;
surface FA uses exact record names, not vertical indices/physical selection.
Ocean model references admit only fixed/prescribed centres and NetCDF. AROME FA
references likewise admit only fixed/prescribed; a separate atmospheric GRIB/
NetCDF reference can supply tracking for FA secondary sources. Inactive tracker
blocks remain representable for full effective inspection; selecting a method
enforces its required inputs. Do not turn optional unselected methods into work.

## 5. Resolution, precedence, failure and replay

Top-level shape stays `schema_version, model, run, input, tracking, domain,
variables, polar, output, execution, logging, metadata`. The 117-row map and §4
define **all** allowed descendants; there is no second parallel schema catalogue.
Recognized old paths/values in a v2.1 document fail, even when the new path is
also present. No coercion of version, flags, numbers or units. Unknown nested
keys and duplicate YAML keys fail with dotted paths/line information where
available, not silent drops. Reject source IDs/group/dimension keys of invalid
type at the configuration boundary, before discovery or output creation.

Do not carry forward incidental permissiveness as a scientific default: the
current schema can accept `exclude: null`, empty file inventories beside a
pattern, empty names inside a variable list, irrelevant child time policies or
empty nested source maps, and arbitrary ignored Zarr `output.format` strings.
The proposed contracts require actual nonempty names/path selections, an exclude
list, no misplaced child controls, and the declared encoding enum. These are
explicit G1 validation/admission tightenings; preserve valid effective scientific
requests rather than reproducing a later TypeError or an ignored declaration.
Tests must pin their rejection before discovery, not silently normalize them.

Single-source input has exactly one nonempty `pattern/files`. With named sources:

1. Parent `input` contains only `sources/time_alignment`; variables and polar
   variable maps belong inside sources. `tracking.source` must name a source and
   its model must equal parent `model`.
2. Source keys are exactly `model/input/variables/polar`. Source input defaults
   are ordinary independent defaults, **not** inherited parent input. Top-level
   output/domain/execution/tracking policies remain run-global. Secondary-source
   internal coordinate-only fixed-box placeholders are never executed as a
   scientific (0°,0°) centre; the continuous reference track is supplied explicitly.
3. Parent polar defaults → explicit parent polar → explicit source polar. A
   source cannot override shared_target to disagree; targets must satisfy the
   existing exact coordinate/ellipsoid/native-spacing/resource checks.
4. All YAML paths use the original document's directory, including source input
   inventories, prescribed track, weights and FA helper. Preserve FA interpreter
   symlinks. CLI `--output-directory` alone uses launch-directory semantics.

Precedence is existing schema defaults → explicit YAML/source overrides →
validated geometry-dependent resolution where a value was left automatic →
explicit non-null CLI/ExecutionOptions overrides. Adapter/preset coordinate names
and tracker dependency definitions are not public override keys and remain
authoritative. A supplied scientific declaration does not overrule contradictory
native evidence. Resource caps can reduce requested concurrency and must record
requested/effective values; they must not select a different scientific method.

Omission uses the per-row default. Null is legal **only** where explicitly listed;
it means auto/unset/required-later as stated, never zero, missing-data filling or
a fallback to another quantity. Empty maps/lists are legal only where their
contracts permit them. All unit-bearing numbers use the named units (no strings
like `"2 km"`). Scientific ambiguities fail in preflight/loading when source
evidence is required; schema-only validation is not payload or applicability
validation. Existing categorical/polar/time/native scientific rejections stay.

`resolved-config.yaml` must be strict reloadable v2.1, including inferred source
formats/spacing, effective product/resource overrides, per-source requests and
the exact public names/tokens. `resolved_sources` must use those same paths and
retain default/YAML/inferred/execution origins. Public-to-runtime translation
maps new tokens to the existing numerical methods/representations, not a legacy
YAML conversion service. Independent output, run-status, FA descriptor, common
target, catalog, dataset-manifest and report schema versions do **not** change.
Provenance continues to distinguish source labels/intervals, conversions, current/
wind/SURFEX declarations, incomplete steps and warnings. Do not add input hashing
or privacy-leaking paths just to perform a rename.

### Every entry point / caller that must change together

| Current boundary / callers | Required v2.1 treatment and test |
| --- | --- |
| `read_yaml`, `UniqueLoader`, `load_runtime`, `resolve_schema`, `to_runtime` | Exact string only; reject old/mixed keys before input discovery or output creation. Preserve signatures `resolve_schema(raw, *, base_dir=None)` and `to_runtime(raw, *, base_dir=None)`. |
| `SimulationConfig.from_yaml`, `.from_yaml_with_model_preset`; `load_config_with_model_presets` | All YAML routes use the same strict resolver; no dataclass/legacy YAML fallback. |
| `SimulationConfig.from_mapping_with_model_preset`; `resolve_config_with_model_presets` | Public run mappings must be strict too; current dual public/runtime dispatch must not become a bypass when model/version is absent. Separate internal preset application from public run-document admission, without maintaining an old-schema converter. |
| Direct `SimulationConfig(...)` / `.from_dict`, low-level numerical request structures and preset files | Internal runtime boundary, not public YAML compatibility. Keep scientific oracles/internal structures where still needed; make the distinction explicit. Update runtime-origin guards currently comparing `schema_version == 2` in settings/execution without touching other contracts. |
| CLI run/validate/config show/inspect/init | New public literals everywhere, inspection-generated document included. `--schema-only`/init/help must not open datasets or optional stacks; run/dry-run same effective override precedence. |
| `source_document`, `_resolve_sources`, `prepare_sources` child documents | Children emit v2.1, use translated names, preserve source defaults/dependency/time/target policies and remain strict-reloadable. |
| `ExecutionOptions.from_config`, `resolved_configuration`, `resolved_sources`, `core/preflight.py`, `core/execution.py`, writer metadata (`io/netcdf_export.py`) | Translate names once at shared boundary, update current public-key reads/origins; independent ordinary-reader values/metadata unchanged. Existing internal `export_netcdf` names need not be a public promise. |
| `config migrate` / `migrate_mapping` and their CLI imports/tests | Remove public converter and legacy public execution tests. Replace documentation by a static release-specific mapping; retain relevant independent numerical assertions in current-schema tests. |
| `testing/catalog.py`, `testing/matrix.py` planning/worker validation, `testing/datasets.py` GRIB conversion helper | Matrix currently builds flat runtime dictionaries and invokes migrate_mapping twice; emit explicit current-schema requests at construction/binding instead. Do not hide a new general old-schema converter under another name. Preserve catalogue/manifest versions and independent selections/oracles. |
| `testing/catalogs/*.yaml`, `testing/recipes/ci.yaml`, presets | Distinguish scientific catalogue/recipe versions and internal method keys from run YAML. Translate public emitted requests; preserve archive evidence and exact independent oracle values. Rename pressure-wind internal identifiers only where needed for consistent dispatch, not blind search/replace. |
| Packaged numerical tests, test services, `example/config_file/*`, public reST literalincludes/commands, README, Slurm examples | Inventory every emitted/loaded run YAML. Switch request syntax, remove active legacy examples/conversion dependence, preserve analytical/source-window assertions. Archived development evidence is historical and is not bulk rewritten into pretend v2.1 evidence. |
| Packaging/CI/environment/version metadata | Task 4 Python >=3.13,<3.14 and Python 3.13 CI alignment; Task 12 candidate 2.0.0rc1. Neither is already implemented here. Optional dependencies remain optional. |

Proposed CLI terminology: `run --no-export-netcdf` → `run --no-export`;
`--no-export-cart` → `--no-export-cartesian`; retain `--no-export-polar` and the
clear existing run controls (`--output-directory`, `--no-overwrite`,
`--synchronous-export`, `--max-workers`, `--require-complete-tracking`,
`--compress-level`, `--institution`, `--log-level`, `--dry-run`,
`--no-hdf5-debug-pop`). No aliases for retired flags. `inspect --format` still
means input format; `--fa-backend` admits only epygram. `config show [--resolved]`
remains complete inspection, not an exhaustive starter. No new backend CLI flag.

## 6. Proposed generator and minimal commented catalogue

Keep the existing configuration boundary, with this exact interface:

```python
write_template(name, path, *, tracking=None, coupling=None, force=False) -> Path
```

No `full` argument. No file-path selectors, registry/plugin framework, generic
template engine or new dependency. Authoritative packaged YAML resources retain
their actual comments; avoid the current load/dump cycle that strips them.
Use the smallest explicit model/workflow selection and active-method section
composition. Never expose unrelated method/default sections in a starter.

### Selector and conflict rules

- Model selectors remain exactly `arome`, `mesonh`, `nemo`, `croco`.
- Named selectors are exactly the seven rows in the catalogue below. They fully
  specify a workflow: reject **any** non-null tracking/coupling flag with a named
  selector, including an identical-looking one; do not ignore or override it.
- Single-model generation admits `fixed_box/prescribed_track` for all four;
  `pressure_wind/pressure_centroid` additionally for AROME/Meso-NH. Model defaults
  stay pressure-wind for atmosphere, fixed-box for ocean.
- Proposed starter-only removal: `--tracking multifield_vortex/utrack` is not
  admitted by init. Do **not** remove these methods from runnable YAML. Their
  required seed/motion/gravity/checkpoint facts need explicit research selection;
  advanced manual examples stay experimental/optional and are translated, not
  silently furnished with guessed values. G1 must approve this generator break.
- Coupling compositions are exactly reference `arome --coupling nemo` and
  `mesonh --coupling croco`, fixed-box by default; prescribed-track also admitted
  for both, pressure-wind additionally for mesonh/croco (existing compact evidence).
  Reject other init combinations and reverse-reference forms rather than promise
  unqualified templates. This does not redefine arbitrary named-source YAML
  admission beyond the existing scientific contracts.
- For each admitted composed selection the named equivalent, where listed, must
  resolve identically at the same base directory, including comments' scientific
  declarations, exact-time policy, fields, level indices and disabled extras.
- Output defaults to `frameit.yaml`; refuse existing destinations without force
  and preserve bytes on refusal. `--force` replaces only the selected generated
  configuration, never input data. Reject unknown/path-like selectors. No dataset,
  checkpoint, native reader or optional polar import/access during generation.

### Exact key-set notation

Each workflow includes **only** its row's base/extra sets. Every dotted leaf below
is an exact required starter leaf; no unrelated defaults may be added. Nested
containers are implied. Source ID and group spellings are fixed by the row.

- **B**: `schema_version, model, run.name, input.directory, input.pattern,
  input.format, tracking.method, domain.width_km.x, domain.width_km.y,
  polar.enabled, output.directory, output.overwrite`.
- **F** (fixed centre): `tracking.fixed_box.center.latitude,
  tracking.fixed_box.center.longitude`.
- **A** (atmospheric surface winds): `input.wind_pairs` with exactly one
  `{group,u,v,reference_frame}` declaration; `variables.surface.names`;
  `output.cartesian.horizontal_vectors`.
- **N**: `variables.deptht.names, variables.deptht.levels.indices`.
- **C**: `variables.s_rho.names, variables.s_rho.levels.indices,
  variables.surface.names`.
- **Coupled base K**: B minus `input.directory/input.pattern/input.format`, plus
  `input.time_alignment, tracking.source`; F also for fixed centre. No top-level
  variables, per-source output, unused vector controls or shared/polar target.
  Each source adds exactly `model,input.directory,input.pattern,input.format`
  and its row's variable/interpretation paths.
- **Prescribed replacement H**: remove F; add only
  `tracking.prescribed_track.file` (default coordinate names stay in reference).
- Pressure-centroid composition adds only its needed source wind declaration(s)
  as below, not the full method tuning map; numerical defaults remain inspectable.

All starters explicitly use `schema_version: "2.1"`, `polar.enabled: false`,
`output.overwrite: false`, relative paths and no optional diagnostic/sampling.
Box widths/centres and real-data fields in templates are **illustrative adaptation
points**, not scientific recommendations or a claim they fit a user's domain.
Run names use the named selector, consistently for model/composed equivalents.

| Named generation command (proposed, not currently runnable) | Equivalent model/composed command | Exact sets, selections and defaults | Required relevant comments / prerequisites / expected products |
| --- | --- | --- | --- |
| `frameit init arome-pressure-wind` | `frameit init arome` or `frameit init arome --tracking pressure_wind` | B+A; arome, grib, `*.grib`, pressure_wind; surface `[u10,v10,prmsl]`, earth pair u10/v10, earth_centered; 500×500 km | YAML-relative paths; verify source wind basis, pressure/velocity units and actual fields; full widths not search half-widths; polar disabled. Track + surface Cartesian NetCDF, with existing selected-wind companions, no polar. |
| `frameit init mesonh-pressure-wind` | `frameit init mesonh` or `frameit init mesonh --tracking pressure_wind` | B+A; mesonh, netcdf, `*.nc`, pressure_wind; `[UM10,VM10,MSLP]`, earth pair, earth_centered; 500×500 km | As above; UM10/VM10 source convention must be verified; exact 000-timeseries exclusion when needed, not broad filename heuristics. Track + surface Cartesian, no SURFEX interpretation/polar. |
| `frameit init arome-fixed-scalar` | `frameit init arome --tracking fixed_box` | B+F+`variables.surface.names`; netcdf, `first-run.nc`, input `./data`; `[instructional_scalar]`; centre (-20,60), 4×4 km | Instructional scalar/structured adapter example, **not an AROME producer file**; replace inspected field/paths for real work; zero ≠ missing; full widths; no wind/polar needed. Task 6 supplies this fixture. Track + scalar Cartesian NetCDF only. |
| `frameit init nemo-native` | `frameit init nemo` or `frameit init nemo --tracking fixed_box` | B+F+N; netcdf, `*.nc`; `[votemper]`, indices `[0]`; centre (-20,60), 100×100 km | Regional native T-grid potential temperature, source units/depth retained, zero-based stored index not diagnosed depth; adapt paths/centre/box. Native component additions require explicit native horizontal representation/separate grids. Track + deptht Cartesian, no polar. |
| `frameit init croco-native` | `frameit init croco` or `frameit init croco --tracking fixed_box` | B+F+C; netcdf, `*_his.nc`; s_rho `[temp,salt]`, indices `[0]`; surface `[zeta]`; centre (-20,60), 100×100 km | Admitted history/Vtransform=2 only; dimensionless sigma ≠ metres, retain formula dependencies and masks; adding currents requires explicit representation choice, not wind declarations. Track + s_rho/surface Cartesian, no new depth/current diagnostic. |
| `frameit init arome-nemo` | `frameit init arome --coupling nemo` or with `--tracking fixed_box` | K+F; ref `atmosphere`=arome, source `ocean`=nemo; explicit common. Atmosphere netcdf `*.nc` in `./data/arome`, surface `[prmsl]`; ocean netcdf `*.nc` in `./data/nemo`, deptht `[votemper]`, indices `[0]`; centre (-20,60), 100×100 km | Independent grids/masks/depths, exact labels only; half-hour means fail to pair with whole-hour snapshots unless an explicitly justified admitted policy is selected. No implicit preceding_hour, winds, currents or shared target. Track + each selected source/group Cartesian. |
| `frameit init mesonh-croco` | `frameit init mesonh --coupling croco` or with `--tracking fixed_box` | K+F; ref `atmosphere`=mesonh, source `ocean`=croco; common. Atmosphere `./data/mesonh`, netcdf `*diag.nc`, surface `[SST,SSS]`, `input.netcdf.surfex_fields: [SST,SSS]`; ocean `./data/croco`, netcdf `*_his.nc`, s_rho `[temp,salt]`, indices `[0]`; centre (-20,60), 100×100 km | Explicit producer-specific SEA interpretation; requires valid FRAC_SEA support/comment units, source999 rule only selected fields, no inferred timing/sign/basis. Ocean/native sigma separate from atmospheric support; no temperature equivalence, current/polar work or NEMO association. Track + each selected source/group Cartesian. |

Other admitted compositions are exact transformations of these bases, **not**
additional named catalogue entries:

- `frameit init mesonh --tracking fixed_box`: B+F+`variables.surface.names`,
  Meso-NH NetCDF `*.nc`, `[MSLP]`, (-20,60), 100×100 km. No A/wind declarations.
- `frameit init arome --tracking prescribed_track` and
  `frameit init mesonh --tracking prescribed_track`: respective fixed-scalar
  selection above +H instead of F; `./track.nc`, exact coordinate/time matching
  comments; for arome keep the instructional NetCDF field, not an invented
  producer identity. The guide must explain replacing both instructional data
  and track when using real inputs.
- `frameit init nemo --tracking prescribed_track` and
  `frameit init croco --tracking prescribed_track`: native row +H instead of F.
- `frameit init arome --tracking pressure_centroid` and
  `frameit init mesonh --tracking pressure_centroid`: respective pressure-wind
  surface selection B+A, method pressure_centroid; add arome isobaricInhPa u/v
  earth pair or mesonh level UT_ZM/VT_ZM earth pair, no extra exported levels.
  Comments must require source-dependent ASL/pressure/native brackets and full
  500-km reference-ring support, and verified actual wind declarations; no
  artificial geometry/height completion. Same existing method/preset requests.
- `frameit init arome --coupling nemo --tracking prescribed_track` and
  `frameit init mesonh --coupling croco --tracking prescribed_track`: coupled
  row +H instead of F; source-independent matching remains common.
- `frameit init mesonh --coupling croco --tracking pressure_wind`: coupled row
  without F; add atmosphere `[UM10,VM10,MSLP]` to SST/SSS, explicit Earth pair
  and global earth_centered representation; no ocean currents selected. Required
  comments distinguish the atmospheric tracker from independent ocean sampling.

All exact commands listed here require Task 5 schema-only/comment/key-set tests
and Task 12 installed-package generation checks. Template rendering/selection
must not generalize unsupported combinations simply because a generic merge can
construct YAML. First-run qualification is the specific fixed-scalar workflow;
other real workflows require their stated inputs and later risk-based checks.

## 7. Complete content / figure map

### Maintainer reading-feedback amendment — 2026-11-06

The maintainer selected `fields_2d` instead of the ambiguous public `surface`
group: fields without a selectable vertical axis, not necessarily ground-level
quantities. Apply it to extraction, polar selections and wind-pair declarations,
including named sources and generated/replayed public YAML. Internal scientific
groups and existing `.surface` output names remain unchanged. This is an approved
public-interface correction before RC freeze, not a data-schema change or alias.

Replace the flat sidebar with collapsible Start here / Task guides / Reference /
Development parents; retain the existing theme and useful nonexperimental URLs.
An annotated all-options **documentation reference**, explicitly not a runnable
starter or new init mode, is now requested. Keep the minimal starter catalogue.
Use environment.yaml/frameit_env for HPC too; retire the extra environment recipe.

Regenerate grid-free illustrations and move experimental comparisons out of public
sources. All six tracker pages end in Known limitations. Correct grid-aligned
Cartesian extraction wording: native indices and rounded point counts define the
crop; a continuous geographical centre can still define polar sampling.

Real BATSIRAI fields—not synthetic radar patterns—must supply contextual plots.
After read-only metadata inspection found no stored dBZ, the maintainer chose a
documented external rain-only estimate. Keep its approximation and temporal/level
support explicit; no new FrameIt diagnostic or plotting API is authorized. The
first-run data remain instructional, with their own minimal downstream plot.

Keep useful `.rst` URLs. The maintainer's G2 correction removes public schema
history and adds `getting_started/first_run.rst`; `quick_start.rst` becomes the
short refresher. Preserve existing explicit labels and heading IDs where retained; when
consolidating content leave a short destination link and retain the old anchor,
not two copied references. Validate resulting local paths/fragments in Task 9.

| Current source beneath `docs/source/` | Decision / canonical destination |
| --- | --- |
| `index.rst` | Rewrite navigation: first run, task guides, concepts, reference/troubleshooting, contribution; no archive toctree. |
| `what_is_frameit.rst` | Rewrite focused mission/current capabilities/limits; preserve URL and attribution; no all-in-one/future-app claims. |
| `getting_started/installation.rst` | One Linux/Python 3.13 setup route. Show commands; omit commentary about unrequested alternatives. Link advanced setup separately. |
| `getting_started/first_run.rst` | Guided scalar example: read the YAML, change run name/output directory, check/run and inspect independent values. |
| `getting_started/quick_start.rst` | Short template/edit/check/run reminder and CLI links for users who know their data. |
| `getting_started/hpc.rst` | Site-neutral HPC/Slurm setup, bounded pilot checks, resources, cancellation and retry policy. No named site or developer-review handoff. |
| `user_guide/input_files.rst` | Retain canonical input/layout/metadata contracts; link task field/coupled guides. |
| `user_guide/ocean_netcdf.rst` | Retain authoritative NEMO/CROCO/SURFEX/time/scientific scope and formulas; clearer task entry links, update selectors only. |
| `user_guide/fa_inputs.rst` | Retain native FA admission/declarations; consolidate duplicated task steps by linking coupled guide. |
| `user_guide/fa_environment.rst` | Retain canonical native-stack setup/troubleshooting; Python 3.13 only, no stale development-environment advice. |
| `user_guide/configuration_file.rst` | Current v2.1 keys, values/defaults/precedence/failures. No public schema-history page or conversion instructions. |
| `user_guide/fa_baseline.rst` | Retain current compatibility/limits, preserve anchors/evidence distinction; no archived development publication. |
| `user_guide/fa_contracts.rst` | Retain metadata/provenance specification; link output and current declarations, not development history. |
| `user_guide/fa_geometry.rst` | Retain native geometry/Earth/grid/centre contract, link fixed/moving/frames guides. |
| `user_guide/fa_surface.rst` | Retain source-specific sampling/support science; task workflow consolidated into coupled guide with old sections/anchors linking there. |
| `user_guide/fa_atmosphere.rst` | Retain equations/full-interface cube specification, applicability and native dependencies. |
| `user_guide/fa_spectral.rst` | Retain unsupported/experimental boundary and evidence; no promotion to supported spectral processing. |
| `user_guide/output_files.rst` | Rewrite ordinary NetCDF/Zarr reader contract, selected source/vertical groups, masks/intervals/status/provenance/storage. Preserve wind-grid-contract and sharded-Zarr anchors. |
| `user_guide/matrix_testing.rst` | Retain regression/fixture procedure, update current emitted syntax and distinguish data availability from manifest. |
| `tracker/fixed_box.rst` | Retain URL; task steps link new fixed_region; preserve algorithm/grid semantics and useful anchors. |
| `tracker/prescribed_track.rst` | Retain exact-time/coordinate specification; link moving_region, no nearest/interpolated association. |
| `tracker/pressure_wind_tracker.rst` | Retain URL, equations/figure/anchors; public method token pressure_wind, link moving guide. |
| `tracker/pressure_centroid.rst` | Retain scientific method/evidence/ASL/reference-ring notes; fix narrow overflow during planned presentation work without changing equations. |
| `tracker/multifield_vortex.rst` | Retain explicit experimental status and remaining reference/real-case qualification; manual current-schema example, no invented approval. |
| `tracker/utrack.rst` | Retain optional weights/dependencies/input scope; manual current-schema example, no automatic download. |
| `polar_projection/xESMF_proj.rst` | Retain technical sampling/reference details; workflow steps link polar_sampling; preserve labels/equations. |
| `polar_projection/scientific_qualification.rst` | Retain independent qualification methodology/results with revision/scope and current sampling conventions. |
| `polar_projection/conservative_experiment.rst` | Retain experimental method/evidence, not a stable production choice. |
| `polar_projection/wind_method_comparison.rst` | Retain experimental comparison and limitations; do not turn method comparison into automatic selection. |
| `visualization_tools/rotate_polar_axes.rst` | Remove with plotting APIs/examples per the post-G2 maintainer correction. Keep numerical methods and explanatory figures. |
| `developper/how_to_add_my_tracker.rst` | Retain URL, update contributor interface examples and method evidence/optionality obligations; correct navigation label without gratuitous URL break. |
| `contributing/documentation.rst` | Refine Task 1 guide with G2 feedback, branding tokens/logo export recipe, precise checks. |

New canonical pages (implemented in Task 8, following the approved G2 pattern):

- Task guides: `task_guides/fixed_region.rst` (pilot), `field_selection.rst`,
  `moving_region.rst`, `scalars_and_vectors.rst`, `polar_sampling.rst`,
  `coupled_inputs.rst`, `storage_and_resources.rst` (all beneath task_guides).
- Concepts: `concepts/sampling_and_frames.rst`, `time_support.rst`,
  `missingness_and_status.rst` (all beneath concepts). Short linked explanations,
  not a compulsory theory course or copied output/configuration reference.
- `getting_started/first_run.rst`: the guided YAML introduction, separate from
  the quick-start refresher. Document only the current configuration format.
- `troubleshooting.rst`: actionable index by failure phase, linking native/method
  specifics rather than duplicating every caveat.
- README stays short: implemented mission, installation/first-run/deeper links,
  limits and preserved credits/citation. Use **Maxence DEFERREZ** in project
  credits, package author metadata and documentation copyright (spelling corrected
  by the maintainer after G2).

Editable SVGs beneath `_static/figures/` (implemented in Tasks 7–8; captions label **schematics**,
not data/validation; units/alt text/legends and non-color distinctions required):

| Asset | Placed beside the relevant decision |
| --- | --- |
| `processing-products.svg` | first_run + output_files: input → checks → chosen processing → products/status/provenance |
| `fixed-moving-regions.svg` | fixed_region + moving_region: continuous centre versus native cropped samples, full widths |
| `sampling-frames.svg` | sampling_and_frames + scalars_and_vectors/polar_sampling: native/Cartesian/polar locations, basis rotation and frame motion distinct |
| `exact-time-association.svg` | time_support + coupled_inputs: exact labels versus explicitly bounded preceding-hour means |
| `independent-sources.svg` | coupled_inputs: separate native grids/depths/masks, optional common target not physical equivalence |
| `missing-zero.svg` | missingness_and_status + first run: valid zero, missing support and no arbitrary fill |
| `status-provenance.svg` | output_files: requested/completed/incomplete/failed products and inspectable provenance |
| `chunks-shards.svg` | storage_and_resources + output_files: compute chunks versus compressed storage chunks/shards, element counts |

Reuse existing `_static/wind_horizontal_c_grid.svg` and `wind_vertical_w.svg` for
actual staggering distinctions; retain sound existing data figures with their
labels/attribution rather than recoloring them. Shared restrained navy/teal/
orange explanatory art follows the approved plan; scientific data colormaps do
not. Copy the supplied masters unchanged and produce a verified font-independent
wordmark only in Task 7. No font substitution/theme migration is authorized.
G2 must approve pilots before applying that design across the site. No archive
from `docs/development/` is included in public Sphinx sources/downloads/inventory.

## 8. Static upgrade and implementation obligations

The upgrade guide must show the explicit renamed paths/tokens in §§3–4 and the
removed `config migrate`, `init --full`, old versions/aliases/flags. A user must
manually review source pairs/levels/representations/time policies when rewriting
a document; do not infer their scientific choices. Historical resolved YAML
stays a truthful record but is no longer executable; existing NetCDF/Zarr data
are not modified/invalidated. Ordinary reader compatibility still depends on
dimensions, quantities, metadata and supported format versions, not just suffix.

Task 4 red/green cases must cover all public loaders, no-dataset/no-output spies,
every removed alias, dynamic/conditional key type failure, source inheritance,
relative paths, explicit override origins, current resolved replay, and runtime
equivalence for each renamed control. Existing analytical/source-window oracles
must survive syntax updates; no regenerated snapshots to justify scientific
change. Task 5 adds catalogue/comment/key-set/conflict/overwrite equivalence
checks; Task 6/12 supply installed first-run/readers. Optionality/failure-safety/
native scientific scope still need Tasks 9–11. No code is implemented here.

### G1 approval record

- Maintainer approval: **RECEIVED, 2026-11-05**, exact reply **"Approved"** to the
  request to approve the complete G1 proposal at `ab0be01`.
- Scope: all seven decisions above, the complete key/value/default/removal map,
  generator/catalogue/conflicts, source inheritance, admission tightenings,
  starter-only advanced-selector removal, explicit starter overwrite refusal,
  content/figure map and stated scientific boundaries. No amendments requested.
- Downstream implementation literals are frozen from this record in the existing
  external plan. G2 and human scientific/reader acceptance remain separate gates;
  this approval does not supply scientific validity or permission to push/deploy.

### Audit verification receipt (not approval)

- Mechanical comparison with the inspected baseline `DEFAULTS`: 117/117 static
  leaf/open-map rows covered, no duplicates. Dynamic validator paths are listed
  separately and were reviewed against the implementation, not inferred from
  that comparison.
- Mechanical comparison with current Sphinx sources: all 31/31 existing reST
  pages have an explicit retain/rewrite/consolidate destination decision.
- One fresh, read-only design builder check identified source-only wording that
  could accidentally exclude the existing atmospheric virtual `wind_speed`
  selection. The source expansion and independent FA speed-only test were
  inspected and the contract corrected; this is behavior preservation, not a
  new diagnostic. No extra maintainer question beyond the explicit G1 decisions
  was reported. This engineering check does not approve G1 or scientific claims.
- No runtime, templates, examples, numerical tests, package metadata or
  dependencies have been changed by Task 3. The v2.1 tests described here remain
  implementation obligations after G1, not passing evidence for an unbuilt schema.
- Confirmed the documented baseline permissive cases with schema-only calls,
  without opening datasets. Audit coverage/results are retained in ignored
  `build/rc/g1-audit-01/inventory-check.log`.
- Fresh `frameit_env` strict Sphinx `baseline-05` build and publication check both
  exited 0; documentation unit tests passed (2); `git diff --check` passed. The
  development proposal is excluded from published Sphinx sources. No full
  numerical/native/installed-artifact or human acceptance claim is made here.
