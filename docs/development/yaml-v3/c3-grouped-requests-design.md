# C3 optional vertical groups

Status: maintainer approved the optional-group approach on2026-11-16. This
document records the bounded implementation choices, not an implemented feature
or scientific validation. It belongs with the existing YAML-v3 design records.
The earlier explicit autonomous-workflow instruction avoids repeating an
approval round for routine implementation choices. Independent review is still
required before a local commit.

## Intent and scope

Express the existing AROME requests without changing their scientific meaning:
height indices `[0,2,5]` and pressure values `[1000,850,400]`hPa within one
atmospheric source, even when both contain fields called `u` and `v`.
Also permit independent selectors on uniquely named fields with different axes.

Preserve simple flat requests, one source per physical type, selected-record
read boundaries, separate clocks, native W, explicit vector preparation,
magnitude after polar component sampling and the C7 coordinate contract.
No new method, implicit field choice, source splitting, fixture preprocessing,
input relabeling, provider preference, interpolation or dependency is introduced.
The three separate NetCDF/CROCO reports are not part of this extension.

## Approaches

1. **Chosen by the maintainer: optional native vertical groups.** Reuse the
   existing binder and readers; add explicit identity and selector information.
   Simple requests remain small; mixed-axis requests become expressible.
2. Retain the old prohibition and declare the catalogue unsupported. This keeps
   less code, but does not preserve the demonstrated required workflow.
3. Split/filter/relabel inputs or use multiple atmospheric sources. Rejected:
   violates the source/scientific-preservation boundaries and hides selection.

The `group.field` reference spelling and always-qualified grouped export names
below are lead implementation choices, not separately claimed human decisions.

## Authored controls

Flat mode is unchanged:

```yaml
variables:
  3d: [UT, VT, WT]
  levels: {indices: [0, 2, 5]}
```

Grouped mode:

```yaml
variables:
  2d: [prmsl]
  3d:
    heightAboveGround:
      names: [u, v, t, r, tke]
      levels: {indices: [0, 2, 5]}
    isobaricInhPa:
      names: [u, v]
      levels: {values: [1000, 850, 400], units: hPa}
derived:
  height_speed:
    method: wind_speed
    inputs: {u: heightAboveGround.u, v: heightAboveGround.v}
```

`3d` is either a nonempty list or a nonempty group mapping, never a mixture.
A group has only required nonempty `names` and optional `levels`. Group keys
are native axis/group identifiers reported by inspection, not arbitrary aliases;
they start with a letter and contain letters/digits/underscore/hyphen.
Duplicate names within a group fail; the same raw name in different groups is
allowed. Grouped mode forbids `variables.levels`, including an empty mapping.
Omitted local levels retain all native levels. Existing strategies, unit rules,
roundoff, physical-domain evidence and destination-grid selection remain intact.

## Identity and references

Each grouped field has the canonical reference `<group>.<raw-source-name>`.
Use it consistently in product `fields`, polar `field_options`, transforms,
wind pairs, derived inputs and field metadata. `names` contains raw source names.
Derived result names remain user-chosen and source-local.

Qualified internal inputs may use a declared group's namespace without being
exported. They use that group's selector. A product filter never supplies
scientific identity; an unqualified name remains an unqualified request even
when only one declared group contains it. Metadata must resolve it independently.

GRIB groups come from inventoried `typeOfLevel`; NetCDF groups come from the
evidenced native selectable vertical dimension; FA cubes use their admitted
full/interface dimension. A group is matched before applying any transform.
It does not declare physical equivalence, broaden supported axes or select a
provider. Any missing group, wrong category, multiple identities within the same
qualified group, competing provider or duplicate request by resolved identity
fails before payload reads/writes. Repeated times/levels of one identity are
not name ambiguity. Unrequested ambiguous fields do not block another request.

Preserve raw field names, IDs, groups and locators in the inventory. Binding
maps canonical references to those identities; never rewrite native evidence.
Use the same resolver for inventory admission, final binding, operation inputs,
metadata declarations and inspection to avoid inconsistent early/late decisions.

## Selectors and calculations

The source request handoff keeps flat `fields`, `levels`, exports and operation
keys. Group mode adds the local group declarations and flattens declared names
to canonical references, rather than adding a second planner.

A native field, explicit transform or polar preparation uses its own group's
selector on the applicable representation. A 3D derived result uses the common
selector of its vertically varying inputs. If those inputs prescribe different
selectors, fail rather than choosing one; users must make that choice explicit
in their source groups. This adds no per-result or per-product level override.
2D results have no vertical selector. Internal neighbour/read support remains
separate from exported level selection.

Implementation boundary found by a new end-to-end test: two native groups can
transform onto the same destination grid but select different coordinates on
its one output axis. This increment rejects that combination in metadata
preflight, with a repair to use matching selections or separate runs. It does
not invent sparse padding or a new output-axis alias scheme. Native groups on
different axes, and equal selections on a shared destination, remain supported.
This is a lead technical limitation, not new human scientific approval.

Existing tracker methods retain their admitted input definitions and independent
support selectors. No user-selected field group may silently redefine a tracker's
scientific inputs or authorize a new tracker profile.

## Exports, reports and provenance

Grouped base fields are always stored as their canonical references, for example
`heightAboveGround.u` and `isobaricInhPa.u`. Names remain stable under filtering,
addition and reordering. Flat field and derived result names are unchanged.
Reject collisions with other requested fields/results or required coordinates;
do not overwrite, select a winner or invent a fallback rename.

The product descriptor maps the reference to stored name, dimensions, units,
path and actual raw field identity. Retain original name/group/ID in binding and
portable output provenance. C7 axes, coordinate auxiliaries, units, bounds,
formula dependencies, missingness and writer encodings do not change.
C9's version1 seven-key report envelope is unchanged.

Inspection offers grouped snippets only when the evidenced group identifies an
admitted 3D field uniquely. Remaining within-group ambiguity reports a repair,
not an executable suggestion. The editor schema describes both shapes and the
source/local-level exclusion; payload-dependent identity checks stay in preflight.
Regenerate the shipped schema from `configuration_schema()`.

## Acceptance and limits

Use TDD for metadata-free schema, references, independent local selectors, missing
groups, within-group ambiguity, provider/identity collisions and flat regressions.
Use compact actual ecCodes multi-axis messages to check metadata-only preflight,
selected-time/level decoder boundaries, distinct values/masks, operation inputs,
stable names and plain-reader NetCDF outputs. Cover grouped NetCDF native axes,
singleton dimensions and independent W selectors without changing fixtures.
Check polar input/result selection and magnitude-after-component-sampling.

Run focused and connected caller checks, strict Sphinx/publication/unit checks
and text-only live GUI desktop/narrow checks. No standalone image/plot checks,
downloads, installation, environment changes or benchmark campaign. Preserve all
earlier evidence and the partial Task16 diff. This increment does not consume or
replace Task16's single post-freeze full diagnostic. Independent review and a
focused local commit precede handing the extension to the producer worker.
