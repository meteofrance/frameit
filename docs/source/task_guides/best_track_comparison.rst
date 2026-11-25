Compare a model track with RSMC La Réunion
==========================================

Start with a completed run that used fixed, prescribed or calculated centres.
Append this block to the same YAML, replacing the source and field names with
actual names. The radii are examples, not recommendations for every storm.

.. code-block:: yaml

   diagnostics:
     best_track:
       agency_template: RSMC
       input: {kind: model_grid, source: atmosphere}
       fields:
         wind: {speed: WSPD10}
         sea_level_pressure: MSLP
         cell_area: CELL_AREA
       search:
         pressure_radius_km: 100
         maximum_wind_radius_km: 250
         wind_radii_radius_km: 600
       rmw:
         method: annular_mean_speed
         radius_km: 150
         bin_width_km: 5
       wind_time_policy: require_10min
       on_unavailable: report

Use ``input: {kind: original, source: atmosphere}`` and exact original
NetCDF names instead if the crop does not supply your fields or search
support. If height is a native axis, a selector can be
``{field: u, group: height, level: {value: 10, units: m}}``.
Use a verified ``speed`` field or exactly two ``u``/``v`` selectors.

.. code-block:: bash

   frameit run-diag frameit.yaml --check --json
   frameit run-diag frameit.yaml

Use ``--run-directory`` after a parent output override or relocation.
``--check`` does not prove comparison eligibility. To request differences,
add the local archive and its exact identifier under ``best_track``:

.. code-block:: yaml

   reference:
     file: ./reference/rsmc.csv
     idswi: 03SWI2024

Read the attempt's ``model_best_track.nc`` for values, bounds and flags.
``rsmc_comparison.csv`` is the model-only projection. With a reference,
``comparison.csv`` also lists matched and unmatched times and eligible
model-minus-observation differences. Track separation uses WGS84. A
prescribed track is not treated as an independent position forecast.
See :doc:`../diagnostics/best_track` for the limits of the comparison.
