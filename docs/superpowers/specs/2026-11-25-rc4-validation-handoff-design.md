# Validation guide and 2.0.0rc4 check

- The storage/resources guide ends with planning, not running or plotting.
  Lead with Validate's **Overview → RAM estimate** in an interactive terminal,
  capture the real TUI using the instructional tutorial fixture, and then show
  the equivalent `--cli` command. Highlight the 1.5× peak RSS recommendation,
  rounded up to a whole GiB. Keep existing references to execution progress valid.
- Compare metadata-only estimates with sampled process-tree RSS from five
  sequential, bounded native pilots: AROME, Meso-NH, AROME SURFEX, CROCO, and NEMO.
  Use local inputs read-only, one selected time and field per pilot, one CPU and
  synchronous export. Preserve local logs and document the measured workloads
  and limitations, without publishing private files or paths.
- Prepare and test package version `2.0.0rc4` in Python 3.13 `frameit_env`. Use the
  approved, hash-verified fixture from `ci-fixtures-v1` for the full suite.
  Verify strict Sphinx, publication boundaries, live preview, and package metadata.
- Do not merge or push an unverified candidate. After verification, merge into
  the clean local `develop`, create `v2.0.0rc4` locally, and push only `develop`
  without force. The push scope includes the 30 existing unpublished commits.

## Approaches

Use actual TUI output and small native runs rather than a mock diagram or
synthetic-only checks. Full archives, production concurrency, and tuning a
headroom factor to five samples are out of scope; investigate any unexplained
shortfall before release.

## Observed native-input checks

Each run exported one selected time and one scalar on its native model grid.
Validation supplied the estimate for the same YAML, one CPU and synchronous
NetCDF export. On Linux, the sampler summed RSS for the CLI process and its child
processes roughly every 20 ms, including startup.

| Reader and field | Output horizontal shape | Estimated peak / median (MiB) | Sampled peak / median (MiB) | Recommended (GiB) |
| --- | --- | --- | --- | --- |
| AROME NetCDF, `prmsl` | 747 × 1395 | 276.93 / 265.00 | 222.56 / 181.93 | 1 |
| Meso-NH NetCDF, `MSLP` | 722 × 1442 | 622.28 / 519.89 | 411.04 / 361.27 | 1 |
| AROME SURFEX FA, `SFX.T2M` | 2037 × 3061 | 1463.80 / 846.60 | 834.26 / 665.22 | 3 |
| CROCO NetCDF, `zeta` | 720 × 1440 | 461.90 / 411.41 | 333.46 / 299.35 | 1 |
| NEMO NetCDF, `sossheig` | 238 × 424 | 264.52 / 260.13 | 213.91 / 181.07 | 1 |

The five products were reopened with xarray. The AROME GRIB candidate did not
finish validation within the bounded pilot (150 s or 5 GiB), so the completed
AROME trial is NetCDF, not real-GRIB calibration. Estimated peaks exceeded
sampled peaks in these five cases; the 1.5× factor was not changed. The medians
measure different things, and these results do not qualify multitime jobs,
spawned exports, other processors or site-specific Slurm measurements.

To regenerate the documentation capture from the public instructional fixture:

```sh
conda run --no-capture-output -n frameit_env env PYTHONPATH="$PWD/src" \
  python docs/capture_validate_ram.py docs/source/_static/figures/tutorial-validate-ram.svg
```
