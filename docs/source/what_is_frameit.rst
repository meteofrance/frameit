What is FrameIt
===============

Global Goal
-----------
The primary goal of **FrameIt** is to provide a robust, modular, and user‑friendly Python library for analysing and visualising atmospheric cyclone data. 
It aims to streamline the workflow from raw model output to formatted data, enabling researchers to focus on scientific questions rather than data managing.

Description
-----------
FrameIt offers a collection of tools for:

- Loading and preprocessing model data (GRIB, NetCDF) with automatic handling of metadata.
- Running various cyclone tracking methods, including prescribed‑track, pressure‑wind, AI-based tracker and fixed‑box method.
- Performing storm-centred geodesic polar sampling with bilinear scalar interpolation
  and a local geodesic basis for radial and tangential winds.
- In the future : generating plots and diagnostics to aid interpretation of cyclone behaviour.

The library is built with extensibility in mind, allowing users to plug in custom trackers and in the future custom diagnostics while leveraging the existing utilities for I/O, 
logging, and configuration management.
