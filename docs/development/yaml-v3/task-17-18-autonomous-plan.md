# Analytical tutorials and repeated cases implementation plan

> Execute inline under the maintainer's no-more-questions instruction.

**Goal:** Advance the independent portions of Tasks17–18 without changing the
preserved producer requests or declaring Task16 complete.

**Architecture:** Extend the existing instructional generator and reuse
`AnalyticVortex.evaluate`, ordinary complete v3 YAML, atomic outputs, current
launchers and the recorded product inventory. No runtime converter or new
dependency.

**Spec:** C10 and Tasks17–18 in `CHECKLIST_FOR_AGENTS.md`; the ocean formula
approval in `STATE.md`. Defaults remain native and diagnostics remain opt-in.

## Decisions and limits

- Generate separate fresh atmosphere, CROCO scalar and prescribed-track inputs.
  Atmospheric samples are at hours0/1/2; ocean samples at0/2. Stationary centre
  is60°E,20°S; translating longitude increases0.1° per hour, latitude stays fixed.
- Atmospheric parameters: R40km, signed Vmax40m/s, p∞101000Pa, Δp5000Pa,
  using C10's Gaussian formulas. The builder-selected instructional layer
  temperature is300K−(0.006K/m)z and interface W=(0.001/s)z.
- CROCO s=Cs=[−0.75,−0.25,0], h40m, hc5m, zeta0 and Vtransform2 give
  the approved depths−30/−10/0m. Temperature uses the approved formula unchanged.
  These are instructional rho-labelled samples, not a producer-conformance claim.
- The atmosphere's25×25 grid is0.05°; the ocean's13×13 grid is0.1°.
  Both cover the same event. A labelled missing/category variant uses a static
  hole and valid zero category; the baseline remains finite.
- Existing scalar helper APIs/formula/missingness stay unchanged.
- No installations, cluster work, benchmark campaign or standalone image checks.
  Plot/human acceptance portions remain explicitly incomplete if unavailable.

## Task17

**Files:** `testing/documentation_example.py`, its numerical tests,
`example/tutorials/analytic-moving.yaml`, `docs/source/task_guides/`.
**Interface:** `create_tutorial_inputs(directory, *, translating=False,
missing=False) -> dict[str, Path]`; CLI adds optional `--tutorial` while the
existing `--output` first-run invocation is unchanged.

- [x] Add failing deterministic/formula/clock/overwrite/mask tests.
- [x] Implement the generator using the existing geodesic wind helper and
  atomic-output contract. Expected: independent formula and source-byte checks pass.
- [x] Add complete YAML and an ordinary-reader walkthrough for sparse times,
  singleton levels, separate sources, explicit polar selection and error repair.
- [x] Execute compact native and polar tasks; inspect strict/publication/live
  text outputs, with independent bounded numerical/plain-English review.

## Task18

**Files:** `example/slurm/`, one repeated-case example, HPC guide and existing
repository-example tests.
**Interface:** one ordinary complete YAML per case; each retry uses a new attempt
directory and preserves original outputs. Checker follows each product's own
recorded source clock; exported track remains optional; NetCDF-only is explicit.

- [x] Read existing launcher/checker and add failing success/failure/retry tests.
- [x] Add the smallest local loop and matching array invocation using existing
  allocation/resource handling. Expected: true child exits, distinct attempts,
  no clobbering, unchanged calculated trajectories.
- [x] Test both default/native and polar output without an exported track,
  plus independently timed sources. Run the required local tests and docs checks.

Review focus: partial fixture publication, output overwrite, category zero versus
missing values, independent clocks, accidental diagnostic execution, and
retry/array path quoting. Do not claim real producer, HPC or human qualification.

## Final permitted evidence — 17 November

The independent portions above are implemented and reviewed. Final exact Task17
suite121:53 passed; Task18 suite122:58 passed. Generator/core commit `95c0f31`,
producer/assets `6426e40`, repeated cases `bd882c2`, documentation `2095dd8`.
All six example findings and later scientific/technical findings are closed.
Strict/publication iteration09,13 publication units and live desktop/narrow
text checks pass.

This does not complete Task17's restricted new-plot portion or Tasks19–21's
installed/whole-branch/human gates. The original formulas, fixtures and
preserved-request blockers remain explicit in `STATE.md`.
