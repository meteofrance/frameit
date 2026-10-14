Input files
===========

FrameIt accepts NetCDF and GRIB files (only GRIB for the AROME model; other GRIB files have
not been tested yet) as input. The following input formats are supported:

- A single NetCDF file containing all time steps.
- A list of files (NetCDF or GRIB), each representing a single time step.

All variables must share the same time dimension with the same name, usually ’time’ for MesoNH and ’valid_time’ for AROME.
For NetCDF files, be sure that the latitude and longitude variable are defined as coordinate for the other variables of the netcdf file.

Selection uses ``input.pattern`` (a standard glob or exact filename) or
``input.files`` (an ordered explicit inventory), with optional ``input.exclude``
globs. Relative paths are resolved from the YAML file. Content-based format
detection rejects mixed inputs; ``input.format`` may explicitly specify ``grib``
or ``netcdf``. See :doc:`configuration_file` for schema-v2 examples, units,
native-grid inference, and migration from the old filename fragments.
