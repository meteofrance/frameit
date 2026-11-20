# Default polar kind from selected input evidence

Fill a missing polar `kind` by default only when admitted input evidence
identifies a continuous quantity. Do not add a YAML setting. Resolve observed
kind and categorical flags, then valid field declarations, before applying
an evidence rule. Unresolved kinds and contradictions remain errors; the
existing explicit-nearest exception is unchanged.

**Approaches.** Unconditionally assuming `continuous` would blend unlabeled
categories. An opt-in would add a setting. Use the approved evidence-based
default in the shared binding instead.

Keep the three existing producer matches. For direct, unchanged NEMO NetCDF
surface scalars, add a rule based on the exact observed [CF sea surface height
above geoid definition](https://vocab.nerc.ac.uk/standard_name/sea_surface_height_above_geoid/)
and supported length units on a selected numeric `time_counter` record with
native `(y, x)` geography. This identifies a quantity, regardless of the
variable's spelling; it is not a match to an AMM12 writer. Do not infer units,
datums, time statistics, or masks or loosen existing layout and reader checks.

Warn once per source and field during input-aware validation for any used
kind completion. Record the rule and evidence on real participating samples
and the warning in run provenance. Keep kind unchanged in native-only copies.
Compare reopened products against the same run with `kind: continuous`
declared; values, missingness, quality, coordinates and units must agree.
