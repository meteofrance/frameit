Native atmospheric levels and cubes
===================================

FrameIt assembles **explicitly associated, instantaneous gridpoint H2D records**
into labelled native atmospheric cubes. The records remain on their original
full/interface indices; extraction does not require pressure or height diagnosis.
This is an implemented, limited assembly/export contract, not qualification of
every producer's scientific fields or full FA compatibility.

Native cubes require ``input.format: fa`` and ``profile: arome_history``, with
qualified modern regular-lon/lat or spherical tangent-Lambert geometry.
Individually selected dense SURFEX records use ``surfex_history`` and its separate
source/layout checks. See :doc:`fa_inputs`, :doc:`fa_geometry` and :doc:`fa_baseline`.

Use the reference :doc:`fa_environment` for the single Python-3.13 stack. FA workers
use the active interpreter in isolated processes; ``python_executable`` is an
optional deliberate override. The ``fa`` extra and identical ``fa-epygram`` alias
use unmodified EPyGrAM 2.1.0, falfilfa4py 1.2.1 and ctypesForFortran 1.3.0, with
the qualified upstream dependencies. ``backend: epygram`` is the default;
``native`` is a deprecated alias of the same reader. Neither dependency nor alias
changes scientific admission.

EPyGrAM remains external software, copyright Météo-France (2014-), under
`CeCILL-C <https://github.com/UMR-CNRM/EPyGrAM/blob/2.1.0/LICENSE.txt>`_. No
implementation or definition tables are vendored. Its
`publisher's 2.1.0 metadata <https://pypi.org/pypi/epygram/2.1.0/json>`_ and
``formats/FA.py`` / ``geometries/VGeometry.py`` describe the version-specific
library interfaces; library defaults/tables are not producer-specific sampling proof.

Inspect and declare exact associations
--------------------------------------

.. code-block:: bash

   frameit inspect ./data --model arome --format fa --pattern '*.fa' \
       --fa-profile arome_history --fa-fields S003TEMPERATURE
   # Add --fa-python /path/to/runtime/bin/python only for a separate runtime.

Inspection reads selected metadata, not physical field payloads. Preflight uses
lazy NaN shape placeholders, never physical zeroes or decoded data. A selected
spectral record or native -91/-93/-94 error fails before physical decoding; it
cannot be accepted as harmless metadata or replaced by another field.

The annotated example below is an association template, **not** a release-qualified
field catalogue. A literal ID such as ``S001TEMPERATURE`` can be spectral in a real
stream. Inspect actual encodings and confirm units, sampling, coefficients and
wind basis before selecting records; installation cannot make an unsupported
declared record executable.

.. literalinclude:: ../../../example/config_file/arome_fa_native_cubes.yaml
   :language: yaml

``input.fa.native_cubes`` maps each logical variable to:

* a nonempty exact ``records`` list, without wildcards or ambiguous/repeated ownership;
* ``vertical_position: mass|interface`` and ``sampling: center``;
* explicit ``field_metadata`` units/kind/instantaneous meaning for the logical variable;
* for winds, declared vector basis and physical-velocity scaling as described below.

The library's selected fixed-surface type must be native hybrid type 119, with
one finite integral label per record within the declared full/interface bounds.
Declared labels must be unique and increasing; they are not silently sorted.
Variables in one vertical group must have the same sampling labels. Only requested
logical variables and declared wind companions are inspected. Every record in a
selected cube's declared list gets metadata/encoding validation, while lazy data
reads are limited to requested levels/times. Keep unsupported/unwanted records
out of that declaration instead of expecting sparse selection to hide them.

Native labels and sparse selection
----------------------------------

``variables.level`` selects mass/full-level data and ``variables.level_w`` selects
interface data. The admitted convention uses one-based labels 1..N and 1..N+1,
respectively. ``<axis>_source_native_index`` preserves the corresponding zero-based
native index. ``levels.indices`` addresses positions in the declared axis;
``levels.values`` matches actual native labels exactly, not pressure/height.

For declared labels [1,2,3], indices [0,2] retain labels [1,3] and native indices
[0,2]. Sparse/reordered selections keep original identities. A name beginning
S000 is not repaired into index zero when library metadata says otherwise.
Original record IDs remain ``<variable>_native_record`` string coordinates.
Wrong fixed-surface type, unavailable labels, out-of-range positions, incompatible
axes or changed hybrid definitions across files fail before physical output.
Individually named 2-D ``variables.surface`` requests remain supported separately.

Hybrid coefficients and reference pressure
------------------------------------------

The native header and checked library vertical grid use:

.. math::

   A_{i,\mathrm{Pa}} = \mathrm{PAHYBR}_i\,\mathrm{PREFER},
   \qquad B_i=\mathrm{PBHYBR}_i.

``PAHYBR`` is dimensionless; ``PREFER`` is the **source reference pressure in Pa**,
not a hard-coded 101325-Pa factor. There are N+1 interface coefficients for N
full levels. Library pressure-valued A and B must agree exactly with the original
normalized A/B/PREFER words and interface labels, once per transaction. Each
selected hybrid field must agree with that resource vertical grid.

Independent fixtures use PREFER=100000 Pa and known A=[0,10000,20000,0] Pa to
distinguish normalization/reference-pressure errors. Nonfinite/incomplete arrays,
invalid counts, nonpositive reference pressure, nonfinite A*PREFER or contradictory
library coefficients fail. Full-level coefficient means are not inferred.

Ordinary NetCDF products retain:

* ``fa_hybrid_interface`` labels 1..N+1;
* ``fa_hybrid_interface_source_native_index``: zero-based coefficient storage index;
* ``fa_hybrid_a_normalized`` (1), ``fa_hybrid_a`` (Pa), ``fa_hybrid_b`` (1);
* ``fa_reference_pressure`` (Pa), native data labels/indices and original record IDs.

The complete coefficient axis survives sparse selection and optional polar
sampling as non-horizontal metadata; it does not re-expand data onto unselected
levels. Native indices remain dimensionless, without hPa/metre labels or incomplete
CF pressure ``formula_terms``. Mass/interface **field association** is an explicit
user declaration; the library's header-wide ``mass`` default is not independent
per-field evidence. Descriptors retain that distinction and its origin.

Native extraction performs no ln(ps)/ps conversion, MSLP substitution, pressure,
geopotential/geometric-height diagnosis, hydrostatic integration, nonhydrostatic-
departure assumption, vertical averaging or extrapolation. These are different
quantities/operations, and ``levels: physical`` remains blocked for FA.

Wind location, basis and selected operations
--------------------------------------------

Cube wind pairs require matching explicit ``vector_basis: earth|grid``,
``component_scaling: physical_velocity`` and centre sampling, consistent with
``input.wind_pairs``. Unresolved staggering or map-scaled components fail.
The existing unit/frame validation and explicitly selected rotation methods apply;
there is no automatic frame/quantity substitution.

Declared companions and required horizontal neighbours are loaded before sparse
selection/cropping. Selected rotation uses the complete horizontal grid; native
Cartesian and Earth-relative analysis branches remain independent, and repeated
preparation is idempotent. Location/collocation, vector-basis rotation and
reference-frame motion are separate concepts; see :ref:`wind-grid-contract` and
:ref:`wind-preparation-method` for the existing equations and method limits.

``geolocation`` is a finite-neighbour WGS84 direction approximation, not an exact
producer-specific conformal correction. Independently specified spherical Lambert
vectors in both hemispheres check signs/components. The ``5e-4 m/s`` bound applies
to the specified 1-km-spacing, 8-km-wide, 5-m/s fixture and its direction-discretization/
ellipsoid effects, not arbitrary production accuracy. ``wind_speed`` is computed
only when requested; available U/V do not enable an unrequested magnitude product.
Continuous production polar sampling defaults to bilinear without conservation.

FA-driven atmospheric trackers remain unsupported. Cubes alone do not provide
verified MSLP, pressure-level diagnostics or tracker input conventions. Use
fixed-box/prescribed-track or a qualified GRIB/NetCDF tracking source in a coupled run.

Outputs, evidence and failure scope
-----------------------------------

Preflight and ``fa_inputs`` retain the backend, per-file cube associations, native
header words, checked hybrid convention and resolved declarations. Decode logs
record actual selected records, masks, scaling and worker/library versions.
Representative NetCDF descriptors describe input records, not a combined
multi-time or post-crop result; see :doc:`fa_contracts` and :doc:`output_files`.
Source/vertical-qualified products retain ordinary-reader schemas and per-product
atomic/final-status handling. A failed required decode/export is not a completed run.

Independent generated gridpoint fixtures cover coefficients/columns, zeroes and
undefined values, full/interface sparse/reordered selection, two times, selected-only
reads, unit/basis/staggering failures, vector preparation, sync/spawn export and
ordinary-reader reopening. They establish finite engineering/numerical behavior,
not real-producer scientific approval. Real sampling, release-matched units/scaling,
spectral decodes and independent real vertical/vector references remain unresolved.
No layer/tile axis, interval conversion or diagnostic is admitted by availability;
see :doc:`fa_baseline` and :doc:`fa_spectral` for remaining limits.
