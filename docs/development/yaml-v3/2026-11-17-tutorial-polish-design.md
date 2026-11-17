# Tutorial polish and final reviews

## Request and chosen presentation

The maintainer requested disposition/fixes for the six reported reader/tracker
failures, copyable plotting examples, clearer Reference prose, revised figures,
and Task 21's final whole-branch reviews. They selected **temperature with wind
vectors** for the atmospheric row of the coupled figure.

Use the existing Python/xarray/Matplotlib stack. Replacing it or adding a plotting
framework would not simplify these small examples.

- Demonstrate `height.levels.values` with units using existing height labels.
  This already works: `[0.01, 1] km` selects `[10, 1000] m` without interpolation.
- Reproduce each of the six failures and compare its expectation with the current
  contracts. Fix implementation defects; replace obsolete expectations with tests
  of current behavior, retaining numerical, metadata and error coverage.
- Show the complete minimal plotting code inline; downloads are optional, never
  the only instructions. Remove the real-input adaptation section from fixture
  generation only.
- Use sparse one-decimal geographical ticks for the trajectory figure.
- Plot polar outputs on circular axes, north at zero and clockwise azimuth.
  Changing display coordinates must not change component meaning or values.
- The coupled illustration is a 2×3 panel: 10 m air temperature and 10 m wind
  vectors above SST, at three shared times and fixed geographical bounds. Use
  consistent row colour scales and a wind-vector scale.

## Scientific and compatibility boundaries

Add dedicated coupled instructional files rather than alter the existing
stationary/translating examples and their independent clocks. Reuse the declared
vortex winds. Define the moving warm anomaly and persistent ocean cold trail
explicitly in fixture metadata and documentation. These are prescribed signals,
not a simulated or validated air–sea response.

Keep native samples, masks, quantities, units, selectors, helper signatures and
tolerances unless a demonstrated defect requires a reviewed change. In
particular, do not restore automatic native-field transformations merely to make
an old assertion pass.

Shorten Reference by leading with the usable rule/example and retaining necessary
units, defaults, assumptions and failure behavior. Preserve useful links/anchors.

## Final review boundaries

After the fixes and rendered checks, run the two fresh reviews required by
Task 21: combined-branch technical/scientific/package/safety review and complete
documentation/user-journey review. Have those reviewers verify accepted closures.
Do not equate agent approval with human usability or scientific acceptance.

Existing restrictions remain: `frameit_env` Python 3.13; no installations or
environment repair, reserved full diagnostic, production/HPC run, benchmark
campaign, push or merge. Missing Task 19 evidence and human walkthrough observations
must stay explicit instead of being marked complete.
