# FrameIt
*Focused Regional Analysis of Modeled Events with Integrated Tracking*

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22128192.svg)](https://doi.org/10.5281/zenodo.22128192)

FrameIt extracts fixed or moving regions from **AROME, Meso-NH, NEMO and CROCO**
outputs. A YAML file selects inputs, fields, tracking and optional polar sampling.
Products use NetCDF or sharded Zarr v3 for analysis with your own tools.

## Installation

On Linux, with Git and Conda/mamba:

```bash
git clone https://github.com/meteofrance/frameit
cd frameit
conda env create -f environment.yaml --solver libmamba
conda activate frameit_env
python -m pip check
frameit --help
```

The environment uses Python 3.13 and installs FrameIt in editable mode. Keep the
checkout: edits to it affect what runs. See [installation](docs/source/getting_started/installation.rst)
and [dependency troubleshooting](docs/source/user_guide/fa_environment.rst).

## Quick start

New to FrameIt? Follow [Your first run](docs/source/getting_started/first_run.rst).

1. Inspect your inputs and create a starter:

```bash
frameit inspect ./data --model arome --format grib --pattern '*.grib'
frameit init arome
# For Meso-NH: frameit init mesonh --output chido.yaml
# Coupled native scalars: frameit init arome --coupling nemo
```

2. Edit `frameit.yaml`: set input paths, quantities and levels, tracking method,
   wind declarations, domain and output directory. Relative paths use the YAML
   file's directory. Polar processing is off by default; select it and its fields
   explicitly when needed.

3. Check and run:

```bash
frameit validate --schema-only  # YAML checks; opens no datasets
frameit validate                # Metadata, units, geometry and required inputs
frameit run --dry-run           # Preview effective settings, resources and products
frameit run
```

Validation and dry-run check metadata and coordinates; values are read during
execution. See [Quick start](docs/source/getting_started/quick_start.rst) for CLI tips.

4. Review `run-status.yaml` under `output.directory`, then open the listed NetCDF
   products with xarray or another ordinary reader. `resolved-config.yaml` records
   effective settings; `run-provenance.yaml` records input, geometry, unit and
   execution facts. A failed run can leave earlier complete products; use the
   status inventory. See [output files](docs/source/user_guide/output_files.rst).

Set `output.backend: zarr` for `.zarr` stores instead of `.nc` files. See
[storage settings](docs/source/user_guide/output_files.rst#sharded-zarr-v3) and the
[configuration reference](docs/source/user_guide/configuration_file.rst).

## Supported tasks and limits

- **Extraction and tracking:** fixed boxes, prescribed tracks, pressure-wind and
  adaptive pressure-centroid tracking (AROME isobaric and Meso-NH native levels).
  The seeded multi-field vortex tracker is experimental, with scientific
  qualification pending. UTrack requires its own weights and dependencies.
- **Coupled inputs:** sources share centres but keep their own grids, masks,
  quantities and products. `input.time_alignment: common` selects exact common
  times and records exclusions; `strict` fails on unequal times. See
  [coupled sources](docs/source/user_guide/fa_inputs.rst).
- **Native FA:** EPyGrAM reads selected instantaneous AROME/SURFEX gridpoint
  records and explicitly associated native cubes. Declare units, sampling and
  projected Earth model from producer evidence. Unresolved scaling fails by
  default. Spectral decoding and packed SURFEX reconstruction are unsupported.
  See [FA limits](docs/source/user_guide/fa_baseline.rst).
- **Optional polar sampling:** continuous production fields default to bilinear
  point sampling, without an area-budget conservation guarantee. Categorical
  data require an explicit appropriate method such as `nearest_s2d`. Shared
  targets are opt-in (`polar.shared_target: true`); equal target coordinates do
  not imply equal source masks or quantities. Conservative, patch and additional
  vector-transport methods remain experimental.
- **Ocean inputs:** regional NEMO supports native scalars and separate components;
  CROCO also supports selected rho/Earth current analysis. Fixed/prescribed
  centres, source depths, time intervals and field-specific missingness are
  preserved. Check [ocean conventions and limits](docs/source/user_guide/ocean_netcdf.rst).

Diagnostics run only when selected. Check scientific definitions, units, sampling
and reference frames before comparing products.

## Optional scientific checks and analytical examples

```bash
python -m frameit.testing.polar_qualification --output ./runs/polar-qualification
python -m frameit.testing.polar_qualification --example --output ./runs/analytical-vortex
FRAMEIT_CI_DATA_ROOT=/path/to/ci_dataset frameit run-all-tests --output ./runs/all-tests
```

Use fresh output directories. Qualification writes numerical JSON reports and
NetCDF examples with analytical errors, profiles, harmonics and coverage checks.
See [qualification](docs/source/polar_projection/scientific_qualification.rst) for
methods and tolerances. `run-all-tests` also runs the
[AROME/MNH matrix](docs/source/user_guide/matrix_testing.rst), which requires its
frozen input fixture, supplied separately through `FRAMEIT_CI_DATA_ROOT` (use
an absolute directory). These checks do not validate every real-data regime.

## Optional HPC / Slurm execution

Use one task on one node per configuration. Use the same `environment.yaml` and
`frameit_env` as the reference installation; no separate HPC recipe is needed.
Portable launchers and an independent output checker are in `example/slurm/`.
See [HPC and Slurm](docs/source/getting_started/hpc.rst)
for environment setup, resource limits, isolated attempts, cancellation behavior,
and the results to collect. Site account/partition/module names must be supplied
from the current HPC documentation.

## Documentation

[Read the documentation](https://meteofrance.github.io/frameit/).
For your own data: [fields and levels](docs/source/task_guides/field_selection.rst),
[moving regions](docs/source/task_guides/moving_region.rst),
[coupled inputs](docs/source/task_guides/coupled_inputs.rst), and
[storage/resources](docs/source/task_guides/storage_and_resources.rst).

## Citation

If you use FrameIt in your research, please cite it as follows:

```bibtex
@software{soufflet_frameit_2026,
  author    = {Soufflet, Clément and Hoarau, Kevin and Colomb, Adrien and Laxenaire, Rémi and Deferrez, Maxence},
  title     = {FrameIt: Focused Regional Analysis of Modeled Events with Integrated Tracking},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.22128192},
  url       = {https://doi.org/10.5281/zenodo.22128192}
}
```

This DOI always resolves to the latest release. To cite the exact version you
used, add the corresponding `version` field and replace the DOI with the
version DOI listed on the [Zenodo record](https://doi.org/10.5281/zenodo.22128192).

## License

FrameIt is released under the Apache 2.0 License.

Copyright 2026 Clément Soufflet and Maxence DEFERREZ — Université de La Réunion

## Authors

FrameIt was developed at Météo-France.

- Clément Soufflet — Météo-France
- Kevin Hoarau — CNRS
- Adrien Colomb — Météo-France
- Rémi Laxenaire — Météo-France
- Maxence DEFERREZ — Université de La Réunion
