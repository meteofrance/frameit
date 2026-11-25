# Validate: catalogue fallback and RAM planning

`frameit validate` should help a researcher repair incomplete source metadata and
size a later `frameit run` without launching that run. The supplied
`FRAMEIT_VALIDATE_CATALOG_LOOKUP-TABLE.md` and catalogue 0.2.0 manifest define the
release and admission rules. The requested application policy supersedes the
handoff's suggestion-only policy.

## Approaches

- A suggestion that must be copied to YAML adds work even when source evidence is
  sufficient. Instead, apply verified values in memory on the shared `validate`
  and `run` binding path. Native and explicitly declared metadata retain
  precedence. Both commands warn, and execution records the catalogue evidence.
- Measuring a pilot would read data, execute science, and require a separate
  workload and output policy. Use the bound metadata plan for an advisory RAM
  estimate instead. Compare it with small measured runs during development, not
  as part of validation.

## Design

Only full validation and execution consult the catalogue, for selected records with
missing metadata. The packaged compressed file is authoritative; the verified,
versioned, local SQLite index is replaceable. Proposals require an exact native
identity and all the release's context checks, agreement among applicable
assertions, no contradictions with known attributes, and admission by any
selected unit-consuming operation. Do not apply values if the selected native
definition is ambiguous. Never rewrite YAML or source files, add a version key
or NetCDF-group reader, or transform scientific values for the lookup.

After a successful bind, use selected sizes, dtypes, geometry, processing,
writer buffers and resolved concurrency to estimate peak and typical RSS for
the local run and workers. The typical estimate is a modeled median, not a
time-sampled statistic. Recommend a rounded allocation with headroom; explain
the principal unknowns or lack of a usable binding. The RAM recommendation does
not change run settings.

Both features add report-plan details without changing the version 1 envelope
or exit codes. Text and the terminal view surface warnings and the RAM summary;
JSON retains the inputs and evidence needed to understand them. Schema-only
validation remains offline and does not load the catalogue or plan a workload.

## Catalogue check and local measurements

The body hash is `ff7b1e735ff50370addda7c5a4308ff6457d960ab0c50fdd841dcbef598b41ec`.
In `frameit_env` on Linux x86-64 (Python 3.13.18, SQLite 3.54.1), opening into
an empty cache took 1.35 s; reopening and verifying its body and index took a
median of 0.54 s (three opens). Within one verified connection, 10,000 repeated exact
`mesonh`/`6.0.0`/`THT`/`mesonh_netcdf_variable` queries including JSON decoding
had a median of 0.039 ms. SQLite used `field_lookup`. These timings concern the
catalogue only, not field validation or processing.

## Compact RAM check

In the same environment, two independent CLI runs read an instructional
`float32` NetCDF field with eight times on a 129 × 129 grid. The sampler summed
Linux `/proc` RSS across local processes about every 20 ms, including startup.
The estimates used the same configurations, without reading the field values.

| Run | Estimated peak / median | Sampled peak / median | Recommended |
| --- | --- | --- | --- |
| Synchronous model-grid NetCDF | 259 / 258 MiB | 212 / 177 MiB (58 samples) | 1 GiB |
| Model grid and polar, two spawned export workers | 777 / 387 MiB | 676 / 281 MiB (156 samples) | 2 GiB |

The modeled and sampled medians are different statistics. Short peaks can be
missed by sampling. These checks do not qualify large jobs, native decoder
memory, or site-specific Slurm accounting.
