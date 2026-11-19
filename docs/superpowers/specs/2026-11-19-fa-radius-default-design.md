# FA projection radius default

When a supported AROME or SURFEX tangent-Lambert FA source has no declared
Earth radius, use the documented spherical radius of 6,371,229 m. See the
[AROME projection guide, §4.3.1 D](https://www.cnrm.meteo.fr/gmapdoc/IMG/pdf_PROJECTIONS_GB_72-1.pdf)
and [SURFEX v8.1 `ini_csts`](https://www.umr-cnrm.fr/surfex/data/BROWSER/doc_surf81/ini__csts_8F90_source.html#l00116).

**Approaches.** Resolve the default in FA geometry, not in the YAML schema:
a blanket setting would also assign an Earth model to angular-only grids.
Reuse the EPyGrAM geometry and original encoded-corner checks; do not fit a
radius, change the projection, or retry with a different value on conflict.
An explicit radius still controls the source, subject to the same checks.

Report the fallback and retain the effective radius and its origin in run
provenance. Do not relax producer, layout, field metadata or scaling checks.
Regular latitude/longitude grids and other formats are unchanged. Verify the
two FA profiles against the explicit standard radius and check a nonstandard
fixture that needs a valid override.
