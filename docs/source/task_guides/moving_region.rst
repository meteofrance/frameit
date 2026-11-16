Follow a moving region
======================

Choose how the geographical centre is supplied before choosing fields. A
supplied trajectory and a calculated atmospheric track are different requests.
The same geographical request applies independently to each source's native grid.

Use a supplied track
--------------------

This complete YAML uses illustrative input paths and a field name. Replace them
from the selected source metadata. The NetCDF trajectory must contain identifiable
one-dimensional time, latitude and longitude coordinates with consistent units.

.. code-block:: yaml

   schema_version: 3
   run:
     name: moving
   sources:
     atmosphere:
       model: arome
       files: ./data/atmosphere.nc
       variables:
         2d: [prmsl]
   region:
     track:
       file: ./prescribed_track.nc
     width_km: {x: 400, y: 400}
   products:
     model_grid: true
     track: true
   output:
     directory: ./results/moving

``region.track.file`` is the only trajectory setting; coordinate names come from
the file's evidence. Duplicate times, conflicting identification, incompatible
dimensions, missing units and nonfinite positions fail.
See :doc:`../tracker/prescribed_track` for the file contract.

The default ``region.sources_coupling_time_association: exact`` requires a centre
at every selected source time. Source timelines may differ if the trajectory
covers each one. Extra trajectory times are allowed; missing required centres
fail rather than shortening extraction or interpolating positions.
Use :doc:`../concepts/time_support` before choosing ``common`` or the narrow
AROME/NEMO ``preceding_hour`` association.

``region.width_km`` gives full widths along the source's native x/y directions.
A rotated grid can produce a rotated crop. The requested continuous centre and
the selected native point are distinct; fields are not recentered by interpolation.
Partial crops are padded with missing values. A centre outside a required source
footprint fails rather than moving to the edge.

.. figure:: ../_static/figures/fixed-moving-regions.svg
   :target: ../_static/figures/fixed-moving-regions.svg
   :width: 480px
   :alt: Schematic comparing a fixed geographical centre with two moving centres and their separately selected native boxes. Widths are full widths in kilometres.

   Schematic, not to scale. Each geographical centre selects a grid-aligned crop.
   Its native centre point can differ from the continuous trajectory position.

Use an atmospheric tracker
--------------------------

Replace the ``track`` block with a tracker, not a second centre provider.
This fragment selects pressure-wind tracking:

.. code-block:: yaml

   region:
     tracker:
       method: pressure_wind
       search_width_km: 200
       refine_width_km: 100
     width_km: {x: 400, y: 400}

Calculated tracking uses the atmospheric source, whatever its name. There is no
tracker-source selector. Required tracker fields are internal dependencies;
they do not become exports unless requested separately.
They obey the source's time selection, without reading excluded samples.

The pressure field is **mean sea-level pressure**, not surface pressure. The
:doc:`pressure-wind specification <../tracker/pressure_wind_tracker>` describes
the full search widths and optional initial geographic search.
The :doc:`pressure-centroid method <../tracker/pressure_centroid>` additionally
needs its documented three-dimensional fields, height convention and sampling.
Do not select a tracker merely because a similarly named field exists.
An atmospheric track does not automatically supply centres at unequal ocean
times; exact association still requires coverage.

.. _check-and-run:

Check the result
----------------

``products.track: true`` requests the reusable NetCDF trajectory; a centre
provider alone does not request a track file. Read its geographical coordinates,
not another grid's ``cx/cy`` indices.

Inspect centre positions, sample times, associations, coverage and
``tracking_complete`` in status/provenance. ``region.tracker.on_incomplete``
defaults to ``error``. Explicit ``keep_prefix`` is accepted only for a method
supporting it and leaves incomplete status; it is not ordinary time selection.
One position cannot establish motion: motion diagnostics are missing, not zero.
See :doc:`coupled_inputs` before comparing separate source products.

Run and check the prescribed-track example
-------------------------------------------

Save the first complete request as ``moving.yaml``, adapting its input and
trajectory paths. Then run:

.. code-block:: bash

   python -m frameit inspect moving.yaml
   python -m frameit validate moving.yaml
   python -m frameit run moving.yaml
   python -m frameit status results/moving

Expect ``products/moving.atmosphere.model_grid.nc`` and
``products/moving.track.nc`` under ``results/moving``. Check the completed
inventory before opening them:

.. code-block:: python

   import xarray as xr

   with xr.open_dataset("results/moving/products/moving.track.nc") as track:
       print(track.time.values, track.longitude.values, track.latitude.values)
   with xr.open_dataset("results/moving/products/moving.atmosphere.model_grid.nc") as fields:
       print(fields.prmsl.dims, fields.prmsl.attrs["units"])
       print(fields.time.values)

Missing centre times fail; supply the intended trajectory samples or correct
the explicit time selection. Do not interpolate positions merely to pass the
check. Use a fresh output directory after a failed attempt.
