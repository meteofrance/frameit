.. note::

   Frozen developer evidence from 9b11d602c4fb05fb2adf74b699439de6a0b8625b.
   Commands, support statements and results below describe historical checkpoints.
   See the `developer index <README.md>`_ for current topics and the removal plan.

FA P5 native cubes and maintained EPyGrAM reader
================================================

The optional ``fa`` extra integrates **EPyGrAM 2.1.0** into FrameIt's
existing isolated FA worker. ``fa-epygram`` remains an identical installation alias.
EPyGrAM is the sole maintained reader and default; ``backend: native`` is a
deprecated alias, with warnings and effective-backend provenance (see `fa_epygram_c4 <fa_epygram_c4.rst>`_).
No scientific approval or full FA compatibility is implied by that dependency.
The subsequent `fa_epygram_c0 <fa_epygram_c0.rst>`_ records the cleanup baseline; `fa_epygram_c1 <fa_epygram_c1.rst>`_
adds evidenced dense SURFEX admission and removes the duplicate raw-resource
prepass from EPyGrAM transactions. P5 results below remain historical evidence.
The current `fa_epygram_c2 <fa_epygram_c2.rst>`_ supplies library-derived labelled geometry and
checks one source-level vertical contract per transaction, preserving P5 sampling.

Implemented scope
------------------

P5 assembles **explicitly associated, instantaneous gridpoint H2D records** into
labelled native atmospheric cubes. Admitted horizontal geometry is still the
existing modern regional regular-lon/lat or spherical tangent-Lambert contract.
Native cubes require ``profile: arome_history``. Individual dense SURFEX records
can use ``profile: surfex_history`` through the C1 capability checks. Coupled
sources may select different helper interpreters without sharing native state.

Independent generated packing-0 fixtures qualify the assembly/export mechanics,
not an arbitrary producer/release's field meanings. Real spectral 103/18,
native -91, unknown scaling, physical-coordinate calculations, staggered/map-scaled
vectors and additional producer conventions retain their gates. EPyGrAM's own
classification of -91/-93/-94 as possible metadata is **not** used to bypass
FrameIt's native encoding guard. No spectral coefficient payload is read here.

Installation and selection
---------------------------

The reference `fa_environment <fa_environment_history.rst>`_ installs the complete stack from
``environment.yaml`` in one Python-3.13 environment; FA workers use that same
Python in separate processes. No helper path is needed. The pip extra below
remains available for separately managed installations.

From a Python-3.13 environment:

.. code-block:: bash

   python -m pip install 'frameit[fa]'

For development, use ``python -m pip install -e '.[test,fa]'``.
Both FA extras supply EPyGrAM's falfilfa4py 1.2.1, ecTrans 1.6.0 and other
unmodified upstream dependencies, with ctypesForFortran 1.3.0. Combining the
installation aliases is supported. A coherent dedicated environment can be selected
with ``input.fa.python_executable``; otherwise the current interpreter is used.
FrameIt must be installed in the helper environment too. Relative executable
paths are YAML-relative; virtual-environment symlinks are preserved.

EPyGrAM is an unmodified external dependency, copyright Météo-France (2014-),
under `CeCILL-C <https://github.com/UMR-CNRM/EPyGrAM/blob/2.1.0/LICENSE.txt>`_.
No EPyGrAM implementation or tables are vendored in FrameIt. References checked
include the `publisher's 2.1.0 metadata <https://pypi.org/pypi/epygram/2.1.0/json>`_
and the installed unmodified ``epygram/formats/FA.py`` and
``epygram/geometries/VGeometry.py`` API/source.

The child selects FA-only formats and no plugins using EPyGrAM's supported user
configuration in a private temporary HOME. It excludes personal configuration,
tables and inherited GRIB/ecCodes definition/sample overrides, and keeps the
existing one-request lock, one native thread, timeout/crash handling, OLD/KEEP
source access and JSON/NPY transfer. Python GRIB and ecTrans imports in this
gridpoint child are explicitly rejected. Parent GRIB settings are untouched.

.. code-block:: bash

   frameit inspect ./data --model arome --format fa --pattern '*.fa' \
       --fa-profile arome_history --fa-backend epygram \
       --fa-fields S003TEMPERATURE
   # Add --fa-python /path/to/helper/bin/python for a separate environment.

Inspection reads selected field metadata with ``getdata=False``. Preflight field
shapes use lazy NaN placeholders, never physical zeroes or decoded payloads.

Configuration and native selection
-----------------------------------

.. literalinclude:: ../../../example/config_file/arome_fa_native_cubes.yaml
   :language: yaml

``input.fa.native_cubes`` maps a logical variable to exact native record names,
``vertical_position: mass|interface`` and ``sampling: center``. Each logical
variable still needs explicit ``field_metadata`` units/kind/instantaneous meaning.
There is no wildcard quantity discovery, name-based unit inference or implicit
level sorting. Only requested logical variables and declared wind companions are
inspected; Dask decodes only selected levels/times when products require them.
Metadata/encoding validation covers every record in a selected cube's declared
list. Keep unsupported/unwanted records out of that list; sparse original native
labels are retained, rather than inferred by parsing an unreadable record name.

``variables.level`` selects mass/full-level data; ``variables.level_w`` selects
interface data. The admitted EPyGrAM convention uses one-based labels 1..N and
1..N+1 respectively. Separate ``<axis>_source_native_index`` coordinates preserve
zero-based native indices. ``levels.indices`` addresses positions in the declared
axis; ``levels.values`` matches native labels exactly. Other index conventions
require evidence and separate admission. In particular a name beginning S000 is
not repaired into index zero when library metadata says otherwise.

Original record IDs survive as ``<variable>_native_record`` string coordinates,
including after sparse/reordered selection. Repeated/ambiguous records, wrong
fixed-surface types, unavailable labels, out-of-range indices, incompatible axes
or changed hybrid definitions across files fail before physical output. Old
individually named 2-D ``variables.surface`` requests remain supported.

Vertical coefficient contract
-------------------------------

The native FA header and EPyGrAM 2.1.0 agree that:

.. math::

   A_{i,\mathrm{Pa}} = \mathrm{PAHYBR}_i\,\mathrm{PREFER},
   \qquad B_i=\mathrm{PBHYBR}_i.

``PAHYBR`` is dimensionless; ``PREFER`` is the source reference pressure in Pa,
not a hard-coded 101325-Pa factor. There are N+1 interface coefficients. EPyGrAM's
pressure-valued A/B arrays are checked against those native words. Tests use a
100000-Pa reference and independently known A values [0,10000,20000,0] Pa to
distinguish normalization and reference-pressure errors. Nonfinite/incomplete
arrays and nonpositive reference pressure fail. Full-level means are not inferred.

Ordinary NetCDF products retain:

* ``fa_hybrid_interface`` labels 1..N+1 and zero-based coefficient storage indices;
* ``fa_hybrid_a_normalized`` (1), ``fa_hybrid_a`` (Pa), ``fa_hybrid_b`` (1);
* ``fa_reference_pressure`` (Pa), native data labels/indices and record IDs.

The complete coefficient axis survives sparse selection and optional polar
sampling as non-horizontal metadata. It does not re-expand data onto unselected
levels. No incomplete CF pressure ``formula_terms`` or hPa/metre labels are added
to model indices. Mass/interface **field association** is an explicit user
declaration; EPyGrAM's header-wide default ``mass`` is not treated as independent
per-field proof. This distinction and its evidence origin remain in descriptors.

Native extraction needs no ln(ps)/ps conversion, MSLP substitution, pressure,
geopotential-height conversion, geometric-height diagnosis, hydrostatic
integration, nonhydrostatic-departure assumption, vertical averaging or extrapolation.
Those are distinct quantities/operations. ``levels: physical`` stays gated.
No physical-coordinate or vertical-sampling method is added because fixed-box
and prescribed-track native extraction require none.

Vectors and optional operations
--------------------------------

Selected cube wind pairs require explicit matching ``vector_basis: earth|grid``
and ``component_scaling: physical_velocity`` as well as center sampling.
Unresolved staggering and map-scaled components fail. The adapter reuses existing
unit/frame validation and selected rotation methods. Declared companions are
loaded before sparse selection; rotation uses the complete horizontal grid before
cropping, retaining boundary neighbours. Native Cartesian and Earth-relative
analysis branches remain independent. Repeated preparation is idempotent.

The existing ``geolocation`` method is a finite-neighbour WGS84 direction
approximation, not an exact producer-specific conformal correction. Independent
spherical Lambert vectors in both hemispheres test signs and physical components;
5e-4 m/s bounds direction-discretization/ellipsoid effects for the specified 1-km,
8-km-wide, 5-m/s fixture. This tolerance is not a production accuracy claim.
Cube wind magnitude is calculated only when ``wind_speed`` is requested.
Existing bilinear continuous polar sampling is retained, with no conservation claim.

FA-driven atmospheric trackers remain gated. Native cubes alone do not provide
verified MSLP, pressure-level diagnostics or tracker input conventions. Use
fixed-box/prescribed-track, or a qualified GRIB/NetCDF tracking source in a coupled run.

Provenance, verification and remaining limits
----------------------------------------------

``fa_inputs`` and preflight retain the selected backend, per-file cube associations,
hybrid convention, exact native words and resolved declarations. Decode logs add
actual selected records, masks, scaling observations and EPyGrAM/native versions.
The representative input descriptor attribute is not a combined multi-time or
post-crop description. Export continues using the existing atomic/final-status
protocol, source-qualified products, precision and compression settings.

The focused ``test_fa_cubes.py`` cases cover independent coefficients/columns,
zero/undefined values, sparse/reordered full/interface indices, two times,
ordinary-reader reopening, sync/spawn export, selected-only decodes, source
conflicts, units/basis/staggering failures, optional dependencies/private config,
rotated vectors/idempotence, CLI metadata and optional bilinear polar metadata.
Base workflows also run with EPyGrAM absent. The maintained family/evidence
manifest is ``testing/catalogs/fa_p5.yaml`` in the installed FrameIt package.

Real producer sampling, release-matched field units/scaling, real spectral
decodes and independent real vertical/vector references remain admission evidence
gaps. No real private FA payload or large production run was used for qualification.
P6 intervals and P7 production resource profiling remain separate work. Synthetic
tests and an established library do not constitute independent human scientific approval.

Verification record
---------------------

Starting revision: ``7258b9e``, with unrelated untracked ``opencode.json`` preserved.
Reference Python is 3.13.16. The local ``build/p5-epygram-env`` is a disposable
overlay environment with EPyGrAM's unmodified upstream dependencies; the reference
environment's falfilfa4py 1.3.0 remains intact. The test-only environment variable
below selects that helper without changing production defaults.

Commands from the checkout (with the reference conda environment's tools):

.. code-block:: bash

   TMPDIR="$PWD/build" \
   FRAMEIT_TEST_EPYGRAM_PYTHON="$PWD/build/p5-epygram-env/bin/python" \
       conda run --no-capture-output -n frameit_env python -m pytest -q \
       --basetemp build/p5-full-tests-01
   TMPDIR="$PWD/build" conda run --no-capture-output -n frameit_env \
       build/p5-epygram-env/bin/python -m pytest -q \
       src/frameit/testing/numerical/test_fa_cubes.py \
       src/frameit/testing/numerical/test_fa_io.py \
       src/frameit/testing/numerical/test_fa_pipeline.py \
       --basetemp build/p5-epygram-stack-tests-final
   TMPDIR="$PWD/build" \
   FRAMEIT_TEST_EPYGRAM_PYTHON="$PWD/build/p5-epygram-env/bin/python" \
       python -m pytest -q src/frameit/testing/numerical/test_fa_cubes.py \
       --basetemp build/p5-cube-tests-10

Observed: full suite **604 passed, 2 subtests passed, 1 skipped** (absent optional
P4 candidate), 722 existing cfgrib/xarray warnings, 301.22 seconds. The alternative
EPyGrAM-stack suite reports **22 passed**, with one NumPy/netCDF runtime warning
and 15 upstream netCDF4/NumPy deprecation warnings. Its initial two failures were
old tests' literal 1.3.0 provenance expectation; assertions now independently
check the distribution actually used by that test interpreter. The reference
environment's two affected sync/spawn cases also pass after that correction.
The strengthened focused P5 suite reports **10 passed**, including an explicitly
selected 3-4-5 wind magnitude and the absence of unrequested magnitude products.

A separate Python-3.13 core environment with FA/EPyGrAM/ecTrans/xESMF absent ran:

.. code-block:: bash

   TMPDIR="$PWD/build" "$CORE_PYTHON" -m pytest -q \
       src/frameit/testing/numerical/test_fa_cubes.py \
       src/frameit/testing/numerical/test_fa_contracts.py \
       src/frameit/testing/numerical/test_fa_baseline.py \
       src/frameit/testing/numerical/test_fa_pipeline.py::test_coupled_netcdf_sources_do_not_need_fa_backend \
       --basetemp build/p5-core-tests-01

Result: **19 passed, 9 dependency-only skips**. Additional checks pass:

.. code-block:: bash

   ruff check src/frameit/io/fa_epygram.py src/frameit/io/fa_cubes.py \
       src/frameit/io/fa_backend.py src/frameit/io/fa_worker.py src/frameit/io/fa_utils.py \
       src/frameit/io/fa_contracts.py src/frameit/core/configuration.py \
       src/frameit/core/preflight.py src/frameit/core/coupled.py src/frameit/core/runner.py \
       src/frameit/testing/fa_fixture.py src/frameit/testing/numerical/test_fa_cubes.py \
       src/frameit/testing/numerical/test_fa_pipeline.py src/frameit/cli.py \
       src/frameit/processing/polar/metadata.py
   frameit validate example/config_file/arome_fa_native_cubes.yaml --schema-only
   frameit validate example/config_file/coupled_fa.yaml --schema-only
   frameit validate example/config_file/coupled_arome_fa_polar.yaml --schema-only
   frameit validate example/config_file/coupled_cyclone_polar.yaml --schema-only
   TMPDIR="$PWD/build" LC_ALL=C LANG=C sphinx-build -q -W --keep-going \
       -b html docs/source build/p5-docs
   TMPDIR="$PWD/build" python -m pip wheel --no-deps --no-build-isolation . -w build/p5-wheel
   git diff --check

Hosted CI is configured but has not been run locally. Reuse fresh test/output
directories. Initial temporary-filesystem exhaustion was handled by using the
checkout's ignored build directory; unrelated workspace/temporary work was preserved.
