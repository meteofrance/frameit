# Polar sampling does not require field kind

A polar request chooses eligible numeric fields and an interpolation method.
Missing `kind` must not block direct or prepared fields, including wind pairs,
or cause FrameIt to add a classification. This supersedes the
[evidence-based completion design](2026-11-20-polar-kind-from-evidence-design.md).

**Approaches.** Keep the bilinear default unless input metadata, CF flags or
a declaration establishes that a field is categorical. The maintainer chose
this over making nearest the default for unlabeled fields. Bilinear can blend
unlabeled categories; select `interpolation: nearest` for them. Do not add a
setting or infer kind from producer, field name or dtype.

Keep categorical method restrictions, numeric precision checks, preparation,
geometry, units, time and mask rules, and the separate FA input contract.
Sampled values must fit the supported numeric types even if `kind` is known;
the sampler cannot guarantee exact representation of 64-bit integers.
Remove the polar-only backfills and their warnings. Files that used a backfill
can omit the old `kind` attribute; users who need it can declare it.
