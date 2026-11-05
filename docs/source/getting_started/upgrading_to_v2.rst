Upgrade to the v2 interface
================================

Run YAML now requires the exact string ``schema_version: "2.1"``. Python 3.13
is the supported runtime. Retired versions (including numeric ``2.1``), flat
documents and old aliases are rejected by every public YAML/mapping loader.
Preserve old configurations and results as historical records; do not edit source
data. There is no ``frameit config migrate`` command or automatic converter.

Manual syntax map
------------------

Rewrite a copy of the document using :doc:`../user_guide/configuration_file`.
These substitutions preserve the intended numerical request, not its scientific
suitability for another source:

.. list-table:: Retired spelling and current spelling
   :header-rows: 1
   :widths: 45 55
   :class: manual-upgrade-map

   * - Retired
     - Current
   * - ``schema_version: 2``
     - ``schema_version: "2.1"``
   * - ``domain.size_km``
     - ``domain.width_km`` (still full widths in km)
   * - ``tracking.method: wind_pressure``; ``tracking.wind_pressure``
     - ``pressure_wind``; ``tracking.pressure_wind``
   * - ``polar.variables: all``
     - ``polar.variables: extracted`` (only extracted selections)
   * - ``variables.<group>.levels: all``
     - ``stored`` (including stored halo positions)
   * - ``output.export.netcdf``
     - ``output.export.enabled`` (both storage backends)
   * - ``output.engine``; ``output.format``
     - ``output.backend``; ``output.netcdf_format`` (only ``NETCDF4``)
   * - ``output.cartesian.horizontal_winds: mass_earth``
     - ``output.cartesian.horizontal_vectors: earth_centered``
   * - ``output.cartesian.horizontal_winds: native``
     - ``output.cartesian.horizontal_vectors: native``
   * - ``input.wind_reference_frame``
     - Removed; explicitly declare each group/U/V/basis in ``input.wind_pairs``
   * - ``input.fa.backend: native``
     - ``epygram`` (or omit for that default)
   * - ``run --no-export-netcdf``; ``--no-export-cart``
     - ``run --no-export``; ``--no-export-cartesian``

Do not merely change the version header of a flat configuration. Express its
actual inventory, exclusions, fields, native levels, method, geometry and output
choices in nested sections. Resolve paths against the old launch directory
deliberately; new relative paths use the YAML's directory. Internal dataclass
names are not a public compatibility format.

Review before execution
-----------------------

* Verify each source wind pair and its basis/rotation against producer evidence;
  a filename does not establish units or physical meaning.
* Keep stored indices distinct from physical coordinates/depths. Do not silently
  remove halo positions, change units, fill missing samples or replace zeroes.
* Put coupled ``sources/time_alignment`` only on the parent. Each source retains
  independent input defaults, variables, masks and vertical axes. Exact time
  association does not turn a mean into a snapshot.
* Use nonempty file/name selections and an actual exclusion list. Null exclusions,
  empty inventories and ignored encoding strings are no longer admitted.
* Inspect ``frameit config show`` for defaults and ``config show --resolved`` for
  metadata-dependent settings, then validate, dry-run and use a fresh output root.

Historical resolved YAML remains provenance but is not executable under the new
loader. Existing NetCDF/Zarr files are not rewritten. Reader compatibility still
depends on quantities, dimensions, metadata and supported storage versions, not
just a matching filename suffix. Passing checks is not scientific approval.
