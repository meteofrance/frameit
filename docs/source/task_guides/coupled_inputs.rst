Process coupled sources
=======================

Use named sources when inputs have different grids, quantities or layouts.
They share geographical centres, not an assumed common physical representation.
Inspect each stream independently, then generate one matching starter:

.. code-block:: bash

   frameit init arome-nemo
   # Or, in a separate run directory:
   frameit init mesonh-croco

AROME+NEMO selects independent pressure and native potential-temperature samples.
Meso-NH+CROCO selects explicitly interpreted SEA SST/SSS and native temp/salt.
The latter requires supported Meso-NH SEA metadata and ``FRAC_SEA`` support, plus
CROCO history/Vtransform=2 metadata. Neither starter selects currents or polar
sampling. Adapt paths, source fields, native levels, centre and full box widths.

Choose the reference and time policy
------------------------------------

``tracking.source`` identifies the source supplying continuous centres. Top-level
``model`` must match it. Each source has its own ``model``, ``input`` and
``variables``; do not put a shared variable selection at the top level.
For moving centres, the corresponding composition is:

.. code-block:: bash

   frameit init arome --coupling nemo --tracking prescribed_track

Supply an appropriate track and use ``input.time_alignment: common`` for exact
common labels (default), or ``strict`` to require equal source times and full
track coverage. Neither interpolates time. The explicit AROME/NEMO-only
``preceding_hour`` policy has additional temporal metadata requirements; see
:doc:`../concepts/time_support` before selecting it.

.. figure:: ../_static/figures/independent-sources.svg
   :target: ../_static/figures/independent-sources.svg
   :width: 540px
   :alt: Two separate source grids and masks map shared geographical centres independently. Optional equal polar target points lead to separate products, not merged quantities or physical depths.

   Schematic. Shared centres or target coordinates do not equate grids, masks,
   native depths, temperatures or temporal support.

Keep source meaning visible
---------------------------

NEMO T/U/V/W contexts can require separate sources even when dimensions have the
same names. CROCO sigma indices are not physical depths. Native currents/stresses
are not atmospheric winds; NEMO analysed components are unsupported. CROCO
rho/Earth currents require the documented static masks, angles and brackets.
See :doc:`../user_guide/ocean_netcdf` for these contracts, and
:doc:`../user_guide/fa_inputs` for explicit native FA declarations.

Enable ``polar.shared_target: true`` only when common point coordinates are
needed. Participating sources must agree on target geometry; the default shared
radial step is the coarsest participating spacing. Scalar/vector eligibility,
masks and interpolation support stay source-specific. The detailed target
contract remains in :doc:`../user_guide/fa_surface`.

Check and run
-------------

.. code-block:: bash

   frameit validate --schema-only
   frameit validate
   frameit run --dry-run
   frameit run

Check time exclusions and source-specific native indices in status/provenance.
A centre outside a required source footprint fails. Read source-qualified
products separately and compare coordinates, time bounds, units and missing
support before combining them. Equal array shapes or target IDs do not establish
physical equivalence; see :doc:`../user_guide/output_files`.
