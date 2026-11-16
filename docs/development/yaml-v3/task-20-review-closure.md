# Task20 review closure — wording gates verified

The private Pass1 reports enumerate 55 journey/example/template paths, 33
scientific/reference paths, and separate complete CLI/help/error coverage.
They are review evidence, not human or scientific approval. Pass2 used fresh
reviewers and read57 journey/example/template paths,33 scientific/reference
pages,17 help invocations and24 error/report families. Both passes' coverage,
finding closure and the independent technical shortening check are recorded.
Reviewed changes are being committed locally in dependency order; the resulting
commit IDs are recorded in `STATE.md`. Broader qualification remains blocked.

## Accepted Pass1 findings and disposition

| Finding family | Repair / evidence | State |
|---|---|---|
| Slurm spool relocation | Explicit absolute delegate argument; moved-script regression53→54, included in68-pass lane62 | Implemented |
| Wrapper interruption and missing YAML | Own/forward/wait child; terminal receipts protected and attempt ownership cleared; missing paths continue | All six findings closed; final122 has58 passes; committed `bd882c2` |
| Checker calendars, trajectory contracts and averaging bounds | CF-calendar-aware labels, track dimensions/units, recorded interval endpoints checked; corruption regressions | Implemented; lane62 |
| Atmospheric formula tolerance | Explicit `rtol=0, atol=1e-12`; unchanged formulas | Lane62 |
| Canonical AROME tracker ambiguity | Method's existing isobaric dependencies resolved before ambiguity checks; qualified pair declarations bound to native components | RED67→GREEN70, unfiltered fixture and no payloads |
| Public native validation accepts known-invalid requests | Public collector binds; internal discovery remains unbound | RED60→GREEN61; full connected95 has1227 passes |
| CROCO finite-land polar mask and active sigma formula | Apply static rho water mask before sampling; archive source sigma formula metadata on polar only | One/two-file regression94 passes; dynamic/changing masks still rejected in95 |
| Existing NEMO component gate | Native copies allowed; polar component analysis still explicitly unqualified | Focused57 passed |
| Polar base versus derived vector meaning | Correct output/reference prose; native base defaults not described as automatic mass/Earth preparation | Text corrected |
| Shared targets versus source clocks | Equal spatial target does not make native clocks, masks or intervals equal | Text/comments corrected |
| Retired ocean/multifield controls and inspection paths | Use source files/explicit transforms, public incomplete policy and actual v3 JSON fields/record inventory | Text corrected |
| Old public dimensions/track names and crop-face promise | Current C7 names; native crops independently selected, no universal N+1 promise | Text corrected |
| UTrack, nearest interpolation and publication flags | Explicit unavailable v3 binding; public `nearest`; distinguish selection from CLI publication suppression | Text/help corrected |
| Compression/help/recovery keys | YAML override applying to NetCDF/Zarr; actual polar-budget/incomplete controls; preserve internal format-diagnostic location mapping | Corrected; report/CLI lanes in95 pass |
| Four incomplete task pages | Complete launch/status/result-reader steps for field selection, moving, representations and coupled inputs | Added, built/previewed |
| Consumed missing/category and explicit W tasks | Complete YAMLs, real runs/readers and unchanged formula/overwrite checks | Two new tests71 pass |
| Analytical sign and fixture-set failure behavior | Clockwise convention; per-file atomicity, not a multi-file transaction | Corrected and built |
| NEMO copying comment | Remove compulsory wind-pair requirement for native copies | Corrected |

## Pass2 and technical closure

- Journeys: all4 Important and13 Minor edits are closed by the original reviewer.
- Scientific pages: I1–I4 are closed by the original reviewer.
- CLI/cross-page: Important1–11 are closed by the original reviewer.
- Independent technical shortening promoted three previously Minor clauses:
  product-only filename prefixes, CROCO native copies needing no analysis
  declaration, and collocation statements scoped to prepared-vector checks.
  All three are corrected and independently closed. Defaults, units, masks,
  temporal distinctions, bearing/sign conventions and tolerances were retained.
- The remaining44 numbered nonblocking science/CLI groups and optional subparts
  are deferred, not claimed implemented. CLI19/23 overlap completed journey/help
  fixes. Full per-ID dispositions remain in the private technical/closure
  reports; there is no blanket statement that all suggestions were applied.
- Strict Sphinx/publication iteration09 passes. Twenty-six affected text pages
  were checked at1280/320px in05, the static-gap addition in06, and the later
  output/qualification/first-run changes in07. Menu focus/click/Enter checks
  succeeded. Earlier unchanged text need not be re-read solely for a new build.
- Iterations08/09's matrix paragraph was inspected at both widths. The producer
  reviewer confirmed its independent time/level expectations and crop checks.
  An adjacent obsolete claim that the checker requires an explicit open-grid
  marker was removed and independently confirmed against the actual checker.
  This changes no runtime check or scientific request.
- Final Task17 suite121 has53 passes; Task18 suite122 has58 passes. Publication
  units124 have13 passes; release126 has2 passes and2 passing subtests.
  Core review's two
  later Important cases were reproduced, fixed and independently closed;
  connected95 has1227 passes. Template wording regression98 is fixed, with
  all74 template cases passing in102.

## Remaining qualification and handover gates

- Producer/canonical assets are committed as `6426e40`; downstream caller
  preservation as `d82ef1f`; repeated-case examples as `bd882c2`.
  The final state record lists the documentation and evidence commits.
- Keep restricted plotting, installed-wheel/HPC/producer checks and actual human
  acceptance explicitly missing. Existing unchanged figures have not received
  new visual acceptance.
- Task16's remaining preserved-request/core incompatibilities are not made green
  by a documentation edit or by changing scientific assertions.
