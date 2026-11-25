# Validate: catalogue repairs and RAM planning

`frameit validate` should help a researcher repair incomplete source metadata and
size a later `frameit run` without launching that run. The supplied
`FRAMEIT_VALIDATE_CATALOG_LOOKUP-TABLE.md` and catalogue 0.2.0 manifest define the
catalogue release and admission rules.

## Approaches

- Automatically applying a catalogue hit would change the interpretation of the
  source and could make validation pass while execution still fails. Instead,
  present a warning with a reviewable `sources.<id>.field_metadata` repair. The
  existing validation verdict and authored metadata retain precedence.
- Measuring a pilot would read data, execute science, and require a separate
  workload and output policy. Use the bound metadata plan for an advisory RAM
  estimate instead. Compare it with small measured runs during development, not
  as part of validation.

## Design

Only full validation consults the catalogue, and only for selected records with
missing metadata. The packaged compressed file is authoritative; the verified,
versioned, local SQLite index is replaceable. Proposals require an exact native
identity and all the release's context checks, agreement among applicable
assertions, no contradictions with known attributes, and admission by any
selected unit-consuming operation. Offer no broad repair if the existing
selector cannot target the intended definition. Do not add a version key, a
NetCDF-group reader, unit conversions, or any new scientific defaults.

After a successful bind, use selected sizes, dtypes, geometry, processing,
writer buffers and resolved concurrency to estimate peak and typical RSS for
the local run and workers. The typical estimate is a modeled median, not a
time-sampled statistic. Recommend a rounded allocation with headroom; explain
the principal unknowns or lack of a usable binding. Neither recommendation nor
lookup affects execution.

Both features add report-plan details without changing the version 1 envelope
or exit codes. Text and the terminal view surface warnings and the RAM summary;
JSON retains the inputs and evidence needed to understand them. Schema-only
validation remains offline and does not load the catalogue or plan a workload.

## Catalogue check and local measurements

The body hash is `ff7b1e735ff50370addda7c5a4308ff6457d960ab0c50fdd841dcbef598b41ec`.
In `frameit_env` on Linux x86-64 (Python 3.13.18, SQLite 3.54.1), opening into
an empty cache took 0.78 s, reopening took 0.034 s, and 10,000 repeated exact
`mesonh`/`6.0.0`/`THT`/`mesonh_netcdf_variable` queries including JSON decoding
had a median of 0.040 ms. SQLite used `field_lookup`. These timings concern the
catalogue only, not field validation or processing.
