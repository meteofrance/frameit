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
  - Fixed box
  - AI-based tracking (utrack)
- **Normalized outputs** — standardized NetCDF outputs to facilitate inter-model and inter-simulation comparisons, 
  and enable AI dataset creation
- **Data reduction** — reduce data volume for easier manipulation and sharing with partners
- **Polar sampling** — storm-centred geodesic polar sampling, bilinear scalar interpolation,
  and radial/tangential winds in the local geodesic basis
- **Modular architecture** — plug in custom trackers and diagnostics
- **Model support** — currently compatible with **AROME** and **MesoNH** model outputs,ocean and wave model extension planned

## Installation

FrameIt requires **conda** to manage dependencies, as some packages (e.g. `xesmf`) 
are not available via pip.

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
- conda (via Miniconda or Anaconda)
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

Existing flat YAML requires explicit migration:

```bash
frameit config migrate old.yml --output frameit.yaml --launch-directory /original/workdir
```

Inspect source variables, units, and geometry with
`frameit inspect ./data --model mesonh`. Use `frameit validate --schema-only`
for configuration checks without opening datasets.

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
