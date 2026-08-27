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
  - Fixed box
  - AI-based tracking (utrack)
- **Normalized outputs** — standardized NetCDF outputs to facilitate inter-model and inter-simulation comparisons, 
  and enable AI dataset creation
- **Data reduction** — reduce data volume for easier manipulation and sharing with partners
- **Polar projection** — stereographic projection centered on the tracked object
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

## Quick start

1. Copy and edit the example configuration file:

```bash
cp example/conf_example.yml my_config.yaml
```

2. Edit `my_config.yaml` to match your simulation setup
   (input files, tracking method, subdomain size, output paths).

3. Run FrameIt:

```bash
frameit run my_config.yaml
```

That's it! FrameIt will extract the subdomain, track the object and write
normalized NetCDF outputs to the directory specified in `frameit_output_dir`.

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
