# FrameIt
*Focused Regional Analysis of Modeled Events with Integrated Tracking*

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22128192.svg)](https://doi.org/10.5281/zenodo.22128192)

FrameIt is a configurable Python tool for fixed or moving subdomain extraction,
object tracking and selected diagnostics from **AROME and Meso-NH** model outputs.
It writes NetCDF products for use with ordinary readers and researchers' own
analysis scripts. Model, variable, grid and reference-frame conventions still
matter when comparing outputs.

## Installation

With Conda/mamba available, create the reference **Python-3.13
FA/GRIB/NetCDF/polar environment** from the checkout:

```bash
git clone https://github.com/meteofrance/frameit
cd frameit
conda env create -f environment.yaml --solver libmamba
conda activate frameit_env
python -m pip check
frameit --help
```

The YAML installs FrameIt in editable mode, including the native stack and
documentation/test tools. Keep this checkout available: edits to it affect the
installed package. **No second environment or subsequent FrameIt installation is
required.** FA workers run in isolated processes using the active Python; omit
`input.fa.python_executable` unless deliberately selecting a different runtime.

The package supports Python 3.10+. Core NetCDF processing can also be installed
without FA, GRIB or polar extras. See [installation](docs/source/getting_started/installation.rst)
for core/optional dependencies and [FA environment and troubleshooting](docs/source/user_guide/fa_environment.rst)
for fresh-environment migration and the optional interpreter override.

## Quick start

1. Inspect a deliberately selected input stream and create an annotated configuration:

```bash
frameit inspect ./data --model arome --format grib --pattern '*.grib'
frameit init arome
# For Meso-NH: frameit init mesonh --output chido.yaml
# To expose every supported setting: frameit init arome --full --output full.yaml
```

2. Edit `frameit.yaml`: set input paths, quantities and levels, tracking method,
   wind declarations, domain and output directory. Relative paths use the YAML
   file's directory. Polar processing is off by default; select it and its fields
   explicitly when needed.

3. Check and execute the requested plan:

```bash
frameit validate --schema-only  # YAML checks; opens no datasets
frameit validate                # Metadata, units, geometry and required inputs
frameit run --dry-run           # Preview effective settings, resources and products
frameit run
```

Validation and dry-run read metadata/coordinates, not scientific field payloads.
They do not verify decoded scaling/values, predict exact memory or runtime, or
establish scientific suitability. Processing can still fail on a selected payload.
See the [quick-start guide](docs/source/getting_started/quick_start.rst).

4. Review `run-status.yaml` under `output.directory`, then open the listed NetCDF
   products with xarray or another ordinary reader. `resolved-config.yaml` records
   effective settings; `run-provenance.yaml` records input, geometry, unit and
   execution facts. Outputs are published atomically per product; a failed run
   can leave earlier complete products. Concurrent writers to one run root are
   rejected. See [output files and interpretation](docs/source/user_guide/output_files.rst).

For legacy flat YAML, migrate explicitly and review the result:

```bash
frameit config migrate old.yml --output frameit.yaml --launch-directory /original/workdir
```

The [configuration reference](docs/source/user_guide/configuration_file.rst) explains
defaults, CLI precedence, wind/level selections and migration.

## Supported tasks and limits

- **Extraction and tracking:** fixed boxes, prescribed tracks, pressure-wind and
  adaptive pressure-centroid tracking (AROME isobaric and Meso-NH native levels).
  The seeded multi-field vortex tracker is experimental, with scientific
  qualification pending. UTrack requires its own weights and dependencies.
- **Coupled inputs:** named atmospheric GRIB/NetCDF and native AROME/SURFEX FA
  streams share geographical centres while retaining independent grids, masks,
  source/vertical-qualified products and physical definitions. The default
  `input.time_alignment: common` selects exact common times, warns about losses
  and records all exclusions; `strict` fails on unequal source times.
- **Native FA:** the EPyGrAM reader supports explicitly defined instantaneous
  gridpoint records, including evidenced AROME-47 / SURFEX-8.1 dense `PACK=0/X1`
  histories and explicitly associated atmospheric full/interface cubes. Units,
  time support, scaling and projected Earth model need explicit evidence and
  declarations. Missing native scaling fails by default. Compact engineering
  fixtures do not qualify arbitrary real producer fields. Spectral FA, packed
  SURFEX reconstruction and implicit pressure/height diagnosis remain unsupported.
- **Optional polar sampling:** continuous production fields default to bilinear
  point sampling, without an area-budget conservation guarantee. Categorical
  data require an explicit appropriate method such as `nearest_s2d`. Shared
  targets are opt-in (`polar.shared_target: true`); equal target coordinates do
  not imply equal source masks or quantities. Conservative, patch and additional
  vector-transport methods remain experimental.
- **Scientific selection:** installing dependencies or finding inputs does not
  enable unrequested diagnostics, deaccumulation, rates, height/pressure calculation,
  vector conversion or support-mask filling. Requested methods can require internal
  companion fields. Ocean and wave model adapters are not currently supported.

Start with [native FA and coupled inputs](docs/source/user_guide/fa_inputs.rst) and
[`example/config_file/coupled_fa.yaml`](example/config_file/coupled_fa.yaml).
The [coupled cyclone example](example/config_file/coupled_cyclone_polar.yaml)
selects scalar polar quantities with explicit wind declarations; the
[FA/FA example](example/config_file/coupled_arome_fa_polar.yaml) uses separate
native streams. Review producer-specific field/scaling/support/Earth-model facts
before use. See [native atmospheric levels and cubes](docs/source/user_guide/fa_atmosphere.rst),
[FA geometry](docs/source/user_guide/fa_geometry.rst),
[coupled atmosphere/surface sampling](docs/source/user_guide/fa_surface.rst) and
[spectral support and limitations](docs/source/user_guide/fa_spectral.rst).

## Optional scientific checks and analytical examples

```bash
python -m frameit.testing.polar_qualification --output ./runs/polar-qualification
python -m frameit.testing.polar_qualification --example --output ./runs/analytical-vortex
frameit run-all-tests --output ./runs/all-tests
```

Use fresh output directories. Qualification retains convergence tables, direct
analytical truth, complex harmonic comparisons, displaced-centre experiments,
coverage and export checks. The example writes a NetCDF vortex and truth/error/
harmonic diagnostic plots. `run-all-tests` also runs the packaged numerical tests
and the AROME/MNH integration matrix.

An opt-in [experimental polar-cell comparison](docs/source/polar_projection/conservative_experiment.rst)
evaluates conservative scalar cell means against point sampling, integrated
bilinear reconstruction and independent spherical overlap/analytical truth:

```bash
python -m frameit.testing.polar_cell_comparison --output ./runs/polar-cell-comparison
# Requires the frozen BATSIRAI fixture used by the --ci matrix:
python -m frameit.testing.polar_cell_comparison --ci --output ./runs/polar-cell-ci
# Source-signed accumulated sensible/latent surface heat exchange:
python -m frameit.testing.polar_cell_comparison --ci-heat-fluxes --output ./runs/polar-heat-ci
# Instantaneous temperature, relative humidity and specific TKE, with explicit weighting:
python -m frameit.testing.polar_cell_comparison --ci-thermodynamics --output ./runs/polar-thermo-ci
```

Production polar sampling defaults to **bilinear for every continuous variable**,
without an area-budget conservation guarantee. Conservative, patch and additional
vector transport remain experimental. Categorical data require an explicit
appropriate method, such as `nearest_s2d`.

The [experimental wind-method comparison](docs/source/polar_projection/wind_method_comparison.rst)
separately evaluates bilinear/ESMF patch weights and component/geodesic-transport
representations against independent vortex truth, with optional real CI winds:

```bash
python -m frameit.testing.polar_wind_comparison --ci --output ./runs/wind-methods-ci
```

These checks assess their documented numerical/engineering scope; passing them
is not scientific approval of another dataset or regime. Matrix commands require
the inputs described in the [regression workflow](docs/source/user_guide/matrix_testing.rst).

## Optional HPC / Slurm execution

Use one task on one node per configuration. `environment-hpc.yaml` provides a
base NetCDF/test environment; add GRIB and polar dependencies only when needed.
Portable launchers and an independent output checker are in `example/slurm/`.
See [the Belenos/Slurm qualification procedure](docs/source/getting_started/hpc.rst)
for environment setup, resource limits, isolated attempts, cancellation behavior,
and the results to collect. Site account/partition/module names must be supplied
from the current HPC documentation.

## Documentation

The full documentation is available at [https://meteofrance.github.io/frameit/](https://meteofrance.github.io/frameit/).

It includes:

- A detailed description of all configuration parameters
- A description of the available tracking methods
- A description of the output files

## Citation

If you use FrameIt in your research, please cite it as follows:

```bibtex
@software{soufflet_frameit_2026,
  author    = {Soufflet, Clément and Hoarau, Kevin and Colomb, Adrien and Laxenaire, Rémi},
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

Copyright 2026 Soufflet Clément - Météo-France

## Authors

FrameIt was developed at Météo-France.

- Clément Soufflet — Météo-France
- Kevin Hoarau — CNRS
- Adrien Colomb — Météo-France
- Rémi Laxenaire — Météo-France
