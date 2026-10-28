# FA documentation: developer evidence and handoff

**Evidence frozen — 2026-10-28.** Inspected checkout:
`9b11d602c4fb05fb2adf74b699439de6a0b8625b` (FrameIt 1.1.0). This is step 1 of
the maintainer's five-step documentation plan. Subsequent user-entry and topic-guide
rewrites are recorded below; the full public rework is not complete.
The plans were read from `../architectures_ideas/frameit-md/docs/README.md` and
`CONTENT_MAP.md`; this index is usable without that separate checkout.

- [Content, ownership and removal map](CONTENT_MAP.md): finite destinations,
  scientific retention, visible strings, incoming links and publication gates.
- [Verification record](VERIFICATION.md): checks actually run for this freeze.
- [User-entry rewrite](user_journey.md): current workflow changes, retention and
  checks for step 2, starting at `35837df`.
- [Scientific topic guides and archival boundary](topic_guides.md): step 3,
  starting at `382624c`, including removed public URLs and preservation checks.
- Current public entry points: [installation](../../source/getting_started/installation.rst),
  [FA inputs](../../source/user_guide/fa_inputs.rst),
  [environment](../../source/user_guide/fa_environment.rst),
  [configuration](../../source/user_guide/configuration_file.rst) and
  [outputs](../../source/user_guide/output_files.rst).
  Entry pages, FA topic guides and navigation use descriptive current guidance.
  Remaining release/message cleanup and final publication acceptance are mapped below.

## What was frozen

The RST records below retain the complete original page bodies, including equations,
citations, meaningful tolerances, test transcripts, failed attempts and unresolved
evidence. Only a historical notice and relocation of Sphinx links were applied.
Their installation commands, future-tense statements and test counts describe their
own checkpoints; they are **not current installation instructions or new results**.

| Original under `docs/source/user_guide/` | Frozen record here |
| --- | --- |
| `fa_epygram_c0.rst` | [Baseline, library APIs and initial cleanup ledger](fa_epygram_c0.rst) |
| `fa_epygram_c1.rst` | [Dense SURFEX admission](fa_epygram_c1.rst) |
| `fa_epygram_c2.rst` | [Geometry and selected metadata adapter](fa_epygram_c2.rst) |
| `fa_epygram_c3.rst` | [Primary coupled-engine qualification](fa_epygram_c3.rst) |
| `fa_epygram_c4.rst` | [Reader retirement and migration ledger](fa_epygram_c4.rst) |
| `fa_epygram_c5.rst` | [Distribution, transfer failures and compact resources](fa_epygram_c5.rst) |
| `fa_baseline.rst` | [Corpus and operation matrix](fa_baseline_history.rst) |
| `fa_contracts.rst` | [Descriptors, typed structure and evidence](fa_contracts_history.rst) |
| `fa_geometry.rst` | [Native-axis repair and geometry verification](fa_geometry_history.rst) |
| `fa_surface.rst` | [Coupled targets, field priorities and corpus observations](fa_surface_history.rst) |
| `fa_spectral.rst` | [Transform candidate, equations and admission gates](fa_spectral_history.rst) |
| `fa_atmosphere.rst` | [Native cubes, hybrid coefficients and vector evidence](fa_atmosphere_history.rst) |
| `fa_environment.rst` | [Unified environment experiments and lifetime evidence](fa_environment_history.rst) |
| `fa_inputs.rst` | [Input overview and original geometry method record](fa_inputs_history.rst) |

[Entry-point excerpts](entry_points_history.md) also freeze the original FA passages
in README, changelog, configuration and output guidance. Other unchanged sources
remain recoverable with `git show <inspected-revision>:<old-path>`.

Evidence catalogues remain in [the existing package directory](../../../src/frameit/testing/catalogs/):
`fa_p0.yaml`, `fa_p3.yaml`, `fa_p4.yaml`, `fa_p5.yaml`, `fa_c0.yaml`,
`fa_c1.yaml`, `fa_c2.yaml`, `fa_c3.yaml`, `fa_c4.yaml`, `fa_c5.yaml` and
`fa_environment.yaml`. Their names, contents, schemas and test/package consumers
are unchanged. This archive has the same directory depth as the old pages, so
`../../../src/...` and `../../../example/...` include paths still resolve.
No private/bulk datasets, generated products or environment copies are archived.

## Current installation/interpreter contract

Reinspected in `environment.yaml`, `pyproject.toml`, `core/configuration.py`,
`cli.py`, `io/fa_backend.py`, `io/fa_worker.py` and `io/fa_epygram.py` under
`src/frameit/`; these source facts are distinct from historical qualification logs.

- From the checkout: `conda env create -f environment.yaml --solver libmamba`,
  then `conda activate frameit_env`. The YAML selects Python 3.13 and installs
  `-e .[test,grib,polar,fa]` from that checkout. Keep the checkout for that editable
  installation. A fresh migration can use `-n frameit_unified`; no second install
  or second environment is required by the reference path.
- Conda declares the shared native stack, including Python netCDF4 1.7.2,
  python-eccodes 2.44.0, ESMPy 8.9.1 and xESMF 0.9.2. The `fa` extra pins
  EPyGrAM 2.1.0 and ctypesForFortran 1.3.0; `fa-epygram` has identical requirements.
  The worker checks falfilfa4py 1.2.1, ecTrans 1.6.0 and netCDF4 1.7.2 too.
  Declared versions do not by themselves establish native lifetime compatibility.
- Package Python support remains `>=3.10`. Core dependencies do not include FA,
  GRIB or polar extras. `grib`, `polar` and `fa` are optional; xESMF still needs a
  compatible ESMF installation. `environment-hpc.yaml` is a base NetCDF/test
  environment, not a second required reference environment.
- `input.fa.backend` defaults to `epygram`; `native` is a warned deprecated alias
  of that same reader. Both retain scientific/source/scaling/resource guards and
  requested/effective-backend provenance. It is not a fallback decoder.
- Omitted/null `input.fa.python_executable` resolves to `None`; `request_fa`
  launches `request.get("python_executable") or sys.executable` in a fresh FA-only
  child. Requests are serialized per consuming process, with one native thread,
  timeout/crash handling and child-only definition-path filtering.
- A nonempty explicit interpreter path selects a deliberately separate runtime
  containing FrameIt and the coherent FA stack. YAML paths are YAML-relative,
  made absolute without dereferencing interpreter symlinks; named sources resolve
  independently and resolved YAML preserves the selection. There is no automatic
  retry using another interpreter. `frameit inspect --fa-python` is the optional
  CLI equivalent for FA inspection (passed directly to the request).
- `validate --schema-only` opens no datasets; ordinary validation and `run --dry-run`
  call metadata preflight. Neither metadata inspection nor a successful plan is
  evidence of decoded values, producer-specific scientific suitability or safe
  native teardown. The existing generated-fixture lifetime tests were read, not
  rerun as new native qualification for this documentation task.

## Publication boundary and next task

This directory is outside `docs/source/` and has no Sphinx toctree or public inbound
link. Do not include it in public HTML, search, downloaded sources, viewcode or the
deployment artifact. Developer records may link to public topics and evidence.

The environment/input/entry-point histories and six mixed FA topic histories are
replaced by current guidance. All six public `fa_epygram_c*.rst` sources and their
navigation entries are removed, with no stage-named stubs or redirects. The full
originals above remain unchanged, including raw verification/dependency ledgers.
Catalogue references and archived relative links retain their existing valid paths.

Example comments pointing to removed records now name current topics; their parsed
settings are unchanged. Step 4 still owns release wording, ordinary messages and
the remaining entry-point audit; step 5 owns complete CI/publication acceptance.
The detailed map retains the finite old-URL -> topic/archive assignments.

**Next task:** step 4, finish release-note and user-visible message wording while
preserving scientific guards and all machine-readable contracts. Reinspect the
current implementation and changes since this freeze before editing.
