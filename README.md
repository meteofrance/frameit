# FrameIt
*Focused Regional Analysis of Modeled Events with Integrated Tracking*

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22128192.svg)](https://doi.org/10.5281/zenodo.22128192)

A modular Python tool for subdomain extraction, object tracking and diagnostics 
from atmospheric and oceanic model outputs.

## Features

- **Subdomain extraction** — extract fixed or mobile subdomains from large model outputs (AROME, MesoNH)
- **Object tracking** — follow meteorological objects (tropical cyclones) 
  with multiple tracking methods:
  - Prescribed track
  - Pressure-wind algorithm
  - Adaptive pressure centroid (AROME isobaric and Meso-NH native-level inputs)
  - Experimental seeded multi-field vortex tracker (AROME and Meso-NH; scientific qualification pending)
  - Fixed box
  - AI-based tracking (utrack)
- **Normalized outputs** — standardized NetCDF outputs to facilitate inter-model and inter-simulation comparisons, 
  and enable AI dataset creation
- **Data reduction** — reduce data volume for easier manipulation and sharing with partners
- **Coupled inputs** — named GRIB/NetCDF and native AROME/SURFEX FA sources, shared
  geographical tracking, independent source grids and reported exact-time alignment
- **Polar sampling** — storm-centred geodesic polar sampling, bilinear scalar interpolation,
  and radial/tangential winds in the local geodesic basis
- **Modular architecture** — plug in custom trackers and diagnostics
- **Model support** — currently compatible with **AROME** and **MesoNH** model outputs,ocean and wave model extension planned

## Installation

Conda/mamba is recommended for the native scientific stack, particularly
ESMF/ESMPy for optional polar processing. Core NetCDF processing also declares
pip-installable runtime dependencies. The `grib` extra adds cfgrib/ecCodes;
the `polar` extra adds xESMF but still requires a compatible ESMF installation.
The reference conda environment targets Python 3.13 and includes the published
`falfilfa4py` wheel. The optional `fa` extra enables the isolated native reader.
FA supports explicitly defined instantaneous 2-D gridpoint records on qualified
regional headers; spectral transformations are not implicit.
SURFEX execution requires a complete AROME source/directory with `PACK=0` and
dense horizontal `X1` records. Native vertical-header facts remain inspectable
provenance, without inferred layer axes or atmospheric 3-D processing.
The optional `fa-epygram` extra provides an alternative isolated backend for
[explicit native atmospheric cubes](docs/source/user_guide/fa_atmosphere.rst),
retaining full/interface indices and checked hybrid coefficients. It uses its
own upstream native pins; choose it separately from the `fa` extra. Native
extraction does not require pressure or height diagnosis.
The [P0 baseline and family matrix](docs/source/user_guide/fa_baseline.rst)
separate current evidence from blocked capabilities; full FA compatibility is
not claimed.
The optional [P4 ecTrans candidate evaluation](docs/source/user_guide/fa_spectral.rst)
checks independent regional Fourier modes in an isolated helper; native spectral
FA execution remains gated pending verified coefficient and real-field references.

1. Clone the repository
```bash
git clone https://github.com/meteofrance/frameit
cd frameit
```
2. Create and activate the conda environment
```bash
conda env create -f environment.yaml
conda activate frameit_env
```
3. Install FrameIt

```bash
pip install .
```

## Requirements

- Python 3.10+
- A compatible scientific Python/native-library environment (conda/mamba recommended)
- Compatible with AROME and MesoNH model outputs

## Scientific qualification and analytical example

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
# Real accumulated rain from the same bundled BATSIRAI fixture as the --ci matrix:
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

## Quick start

1. Create an annotated, model-specific configuration:

```bash
frameit init arome
# Or: frameit init mesonh --output chido.yaml
# All supported settings: frameit init arome --full --output full.yaml
```

2. Edit `frameit.yaml` to match your simulation setup
   (input files, tracking method, subdomain size, output paths).

3. Validate, preview, and run FrameIt:

```bash
frameit validate
frameit run --dry-run
frameit run
```

That's it! FrameIt will extract the subdomain, track the object and write
normalized NetCDF outputs under `output.directory`. Schema version 2 uses grouped
settings, automatic native-grid spacing inference, and explicit units. Relative
paths are resolved from the YAML file. Runs save `resolved-config.yaml` and
`run-provenance.yaml` alongside products and logs.
An atomic `run-status.yaml` records final completion and the product inventory.
Concurrent runs in the same output root are rejected.

### HPC / Slurm

Use one task on one node per configuration. `environment-hpc.yaml` provides a
base NetCDF/test environment; add GRIB and polar dependencies only when needed.
Portable launchers and an independent output checker are in `example/slurm/`.
See [the Belenos/Slurm qualification procedure](docs/source/getting_started/hpc.rst)
for environment setup, resource limits, isolated attempts, cancellation behavior,
and the results to collect. Site account/partition/module names must be supplied
from the current HPC documentation.

Existing flat YAML requires explicit migration:

```bash
frameit config migrate old.yml --output frameit.yaml --launch-directory /original/workdir
```

Inspect source variables, units, and geometry with
`frameit inspect ./data --model mesonh`. Use `frameit validate --schema-only`
for configuration checks without opening datasets.

For atmospheric GRIB/NetCDF coupled to SURFEX FA, start from
[`example/config_file/coupled_fa.yaml`](example/config_file/coupled_fa.yaml).
The primary integration target is **EPyGrAM-backed SURFEX FA + AROME GRIB**.
The [C0 baseline, API evidence and cleanup ledger](docs/source/user_guide/fa_epygram_c0.rst)
record the current admission plan: SURFEX execution still uses the native backend;
the EPyGrAM backend currently accepts atmospheric FA only. Other producer or
native-container integrations are outside this increment. A native FA/FA example is
[`example/config_file/coupled_arome_fa_polar.yaml`](example/config_file/coupled_arome_fa_polar.yaml).
`input.time_alignment: common` selects exact common times by default, warns for
each source losing times and records all exclusions in provenance/final status.
Choose `strict` to fail on unequal source times. Each source retains its own
grid; FA geometry and field meaning/scaling need explicit declarations.
For separate atmospheric/surface products with identical polar target coordinates,
select `polar.shared_target: true`. See the
[cyclone coupled-polar example](example/config_file/coupled_cyclone_polar.yaml) and
[P3 field/evidence notes](docs/source/user_guide/fa_surface.rst). Source masks and
physical definitions remain independent. Marine-model adapters are future work.

## Documentation

The full documentation is available at: *[https://meteofrance.github.io/frameit/]*

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
