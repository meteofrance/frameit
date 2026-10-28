.. note::

   Frozen developer evidence from 9b11d602c4fb05fb2adf74b699439de6a0b8625b.
   Commands, support statements and results below describe historical checkpoints.
   See the `developer index <README.md>`_ for current topics and the removal plan.

FA P4 spectral candidate and admission gates
=============================================

**Status: library evaluation implemented; production spectral FA remains blocked.**
This bounded P4 increment starts from ``cce8934``. P0 observed spectral 103/18
flags for ``S001TEMPERATURE`` and ``S001WIND.U.PHYS``; it did **not** decode their
coefficients. No supplied encoding has the coefficient/scaling/layout and trusted
native-grid reference needed for spectral production admission. Installing a
transform cannot fix the separate native -91 records. See `fa_baseline <fa_baseline_history.rst>`_.

The selected candidate is **ecTrans / ectrans4py 1.6.0**, evaluated in a disposable
Python-3.13 environment. Its regional scalar inverse transform works against
independent analytical modes. This is not completion of P4's real-field gate,
qualification of an FA encoding, scientific approval, or atmospheric cube support.

Actual library and version evidence
-----------------------------------

The publisher's `PyPI metadata <https://pypi.org/pypi/ectrans4py/1.6.0/json>`_
provides a 3.84-MB Linux x86_64 CPython-3.13 wheel. It is the latest published
wrapper observed on 2026-10-26. The maintained
`ecTrans project <https://github.com/ecmwf-ifs/ectrans>`_ has a newer native
`2.0.0 release <https://github.com/ecmwf-ifs/ectrans/releases/tag/2.0.0>`_.
These release schedules and APIs are not interchangeable. No ongoing maintenance
promise for the older wheel, native 2.0 build, or untested wrapper is inferred.
The evaluated wheel prints native 1.6.0 and revision
``2c4c818d79effe56d30bb2896866aba590a5fad8``. Distribution/native identities,
wheel hash, checked source references and finite family statuses are retained in:

.. literalinclude:: ../../../src/frameit/testing/catalogs/fa_p4.yaml
   :language: yaml

The actual `1.6.0 wrapper
<https://github.com/ecmwf-ifs/ectrans/blob/1.6.0/src/ectrans4py/__init__.py>`_
and its Fortran interfaces expose:

* ``etrans_inq4py(nx, ny, physical_nx, physical_ny, tx, ty, max_resolutions, dx, dy)``:
  regional gridpoint count and **real coefficient count**, from ``ETRANS_INQ``.
* ``sp2gp_lam4py``: regional double-Fourier scalar inverse transform; explicit
  coefficient size, derivative flag, reorder flag and spacing. ``LREORDER=True``
  invokes the library's own FA-order to model-order conversion. FrameIt does not
  implement a transform or copy that reorder algorithm.
* ``trans_inq4py`` / ``sp2gp_gauss4py``: distinct global Gaussian/Legendre
  interfaces. Global inquiry and interleaved-complex input sizes have different
  contracts from the LAM real coefficient count. They are inspected, **not run or
  qualified** here; global/reduced FA remains outside this phase.

The wrapper requires ``ctypesForFortran<2``. The evaluation extra pins 1.3.0;
the ordinary reference FA environment retains its 2.2.1 installation. This is an
optional test environment, not an automatic environment update. A future
production version selection needs upstream-supported native/wrapper compatibility
and the same independent acceptance cases before admission.

Reproduce the bounded evaluation
---------------------------------

In a fresh Python-3.13 environment, from the FrameIt checkout:

.. code-block:: bash

   python -m pip install -e '.[test,fa-spectral-test]'
   python -m frameit.testing.fa_spectral_probe --output ./runs/fa-spectral-candidate
   python -m pytest -q src/frameit/testing/numerical/test_fa_spectral.py

Use a fresh output directory. The explicit command launches a disposable native
child; ordinary imports, inventory, gridpoint/GRIB/NetCDF processing and diagnostics
do not load ecTrans or run these tests. The probe reads **no source files** and
accepts no production fields or arbitrary transform parameters. It checks three
small library parameter sets, at most 216 gridpoints and 64 coefficients.
Coefficient allocations use the native inquiry count. Neither ``nx*ny`` nor the
compressed/indexed word count supplies coefficient dimensions.

The child has one native thread, three resolution slots, no core dumps and no
unlimited-stack request. The parent excludes inherited ecCodes definition/sample
overrides only for that child, enforces a 30-second timeout and removes temporary
files. ``report.json`` is atomically published in the new designated directory.
It records failed attempts, missing dependencies, native death and timeouts;
``passed_limited`` always accompanies ``production_spectral_fa: blocked``.
No coefficients or purported physical fields are exported.

Method and independent numerical evidence
------------------------------------------

**Quantity/method/maturity:** scalar inverse regional double-Fourier synthesis
through the published double-precision ecTrans LAM API; candidate evaluation only.
This is a numerical codec/transform investigation, not a stable diagnostic.
Upstream implementation/API documentation specifies the tested library contract;
release-matched producer conventions and human scientific review are missing.

**Inputs/conventions:** explicit grid dimensions, physical dimensions equal to the
complete test grid, spacings 1000 m, truncations (3,3), (5,3), (2,2), unit spectral
coefficients (constant 1.25), ``LREORDER=True``, ``LGRADIENT=False``. The native
inquiries return 44/64/24 reals for 144/216/144 gridpoints. The probe does not
interpret FA header words as truncations or assume a real field uses Fourier
rather than Legendre space. Extension zones and source Earth models are not
qualified by these library-only tests.

**Equations/numerics:** independent closed-form values use
:math:`X=2\pi m i/n_x`, :math:`Y=2\pi n j/n_y`. In the evaluated four-real
coefficient blocks, the scalar basis for positive m,n is

.. math::

   4(A\cos X\cos Y - B\cos X\sin Y
     - C\sin X\cos Y + D\sin X\sin Y).

Pure-X modes are :math:`2(A\cos X-C\sin X)`; pure-Y modes are
:math:`2(A\cos Y-B\sin Y)`. The zero-wavenumber constant is A.
Tests directly populate single coefficients and compare against these equations,
including zero, constant, both sine signs, all four mixed slots and each axis's
truncation edge. There is no forward-transform/round-trip oracle. All 36 cases
pass at ``rtol=0, atol=5e-13``; observed maximum absolute error is
``5.551115123125783e-15``. The tolerance allows float64 roundoff for this small,
unit-amplitude workload (at most five waves); it is not a tolerance for packed
real data, all truncations, another version or production resources.

**Differences/applicability/failures:** no change to upstream transform mathematics,
normalization or coefficient reordering. No custom transform, gradient, vector,
pressure/height calculation, interpolation, conservation claim or method switch.
Missing or different dependencies and nonfinite/incorrect numerical outputs fail
the attempt. SIGSEGV and timeout lifecycle tests use deliberately failing disposable
Python processes; they are not claims to reproduce a particular ecTrans defect.

An exploratory compact native coefficient fixture aborted in native code. Its
header/coefficient contract had not been established; it is not an admitted
fixture, an upstream diagnosis, or evidence that packing-0 spectral FA works.
No speculative native header mapping or supported generator from that attempt is
retained. The library evaluation is deliberately independent of FA decoding.

Production boundary, metadata and compatibility
------------------------------------------------

Selected spectral records still fail **before physical payload decoding**. Raw
inspection preserves encoding flags and additive descriptor-v1
``native.spectral_contract`` metadata: exact native ``KTYPTR``/``KTRONC`` words,
explicitly unresolved coefficient count/order/space/normalization/transform
truncation and a blocked status. FANION ``truncation`` is potential *under-truncation*,
not proof of a complete transform truncation. Indexed word counts remain separate.
The current regional inspector still retains only its admitted rectangular active
header slices; it does not claim complete Gaussian/reduced/spectral active-array
retention, including ``KNOZPA``. Admission requires the correct active-array contract
before retaining or interpreting such work buffers.

The parent additionally rejects a read response whose descriptor is spectral,
unknown or blocked, even if its transferred dtype and shape resemble a grid.
Coefficients cannot masquerade as values. Raw coefficient export has no admitted
public contract. Inspection metadata is portable JSON; existing per-file provenance
retains it through the usual descriptors. The evaluation report adds versions,
code revision/dirty state, effective transform arguments, counts, per-mode errors,
tolerance, resource policy, native diagnostics and unresolved gates.

Existing single-source/coupled YAML, selected-record laziness and native-grid
products retain their contracts. There is no spectral YAML activation key. The
ordinary NetCDF schema, compression, precision, masks and atomic publication do
not change. Common/strict exact-time behavior, optional diagnostics/dependencies
and production bilinear polar sampling remain as documented in `fa_inputs <fa_inputs_history.rst>`_.

Remaining P4 gate and P5 prerequisites
---------------------------------------

For **each** proposed encoding/release, obtain:

#. A P0-proven native coefficient decode with authoritative dimensions, scaling
   and missing-value semantics. FANION flags alone are insufficient; -91 remains
   a separate upstream gate. No compressed-length or grid-size allocation fallback.
#. The actual FA header/active-array to transform contract, coefficient order,
   Fourier/Legendre space, full and under-truncation, normalization, original grid,
   Earth model and CI/C/extension-zone definitions.
#. Independent trusted real coefficient and native-grid fields, matched variables/
   levels/times/masks, redistribution permission for compact fixtures, justified
   packing/transform tolerances and human review of scientific conventions.
#. Compatible maintained native/wrapper versions and measured/bounded memory for
   coefficients, workspaces, masks, complete-grid transforms and transfer. Verify
   selected fields/dependencies, missing packages, crashes and unchanged gridpoint
   outputs before enabling a production path.

P5 may use already admitted gridpoint records independently, but spectral cubes
require those P4 gates first. Cubes/vectors additionally require actual field-level
sampling, full/interface indices, hybrid coefficient units/reference pressure and
producer vector-basis/staggering definitions. No optional physical-coordinate or
diagnostic calculation becomes mandatory because inputs exist.

Verification record
---------------------

Python 3.13.16 reference environment (no ecTrans installed):

.. code-block:: bash

   conda run --no-capture-output -n frameit_env python -m pytest -q
   ruff check src/frameit/io/fa_contracts.py src/frameit/io/fa_worker.py \
       src/frameit/io/fa_backend.py src/frameit/testing/fa_spectral_probe.py \
       src/frameit/testing/numerical/test_fa_spectral.py
   frameit validate example/config_file/coupled_fa.yaml --schema-only
   frameit validate example/config_file/coupled_arome_fa_polar.yaml --schema-only
   frameit validate example/config_file/coupled_cyclone_polar.yaml --schema-only
   LC_ALL=C LANG=C sphinx-build -q -W --keep-going -b html \
       docs/source /tmp/opencode/frameit-fa-p4-docs
   python -m pip wheel --no-deps --no-build-isolation . -w /tmp/opencode/frameit-p4-wheel
   git diff --check

Observed: **594 passed, 2 subtests passed, 1 skipped** (the absent optional
candidate), 722 existing cfgrib/xarray future warnings, 276.23 seconds. Lint,
three schema examples, strict documentation and wheel build pass. Ordinary FA
gridpoint/GRIB/NetCDF, coupled common/strict times, independent native grids,
synchronous/spawn exports and ordinary-reader output checks are in that regression.

In the disposable candidate environment, using its Python as ``P4_PYTHON``:

.. code-block:: bash

   conda run --no-capture-output -n frameit_env "$P4_PYTHON" -m pytest -q \
       src/frameit/testing/numerical/test_fa_spectral.py \
       src/frameit/testing/numerical/test_fa_io.py \
       src/frameit/testing/numerical/test_fa_pipeline.py
   conda run --no-capture-output -n frameit_env "$P4_PYTHON" \
       -m frameit.testing.fa_spectral_probe --output /tmp/opencode/frameit-fa-p4-candidate

Observed: **22 passed**, one NumPy/netCDF binary-size runtime warning. The
standalone report passes all 36 analytical cases with the limitations above.
The overlay environment inherits conda's native-library/data discovery through
``conda run``; an initial direct-overlay attempt could not discover ecCodes/PROJ.
The activated rerun passes without patching libraries or changing the FA/GRIB
boundary. An initial full-suite attempt hit the shell's 120-second limit and
exposed an order-dependent dependency-check test; after correction the complete
long-timeout run above passed.

A separate Python-3.13.16 core environment, with neither FA nor ecTrans nor xESMF,
used its Python as ``CORE_PYTHON``:

.. code-block:: bash

   "$CORE_PYTHON" -m pytest -q \
       src/frameit/testing/numerical/test_fa_spectral.py \
       src/frameit/testing/numerical/test_fa_contracts.py \
       src/frameit/testing/numerical/test_fa_baseline.py \
       src/frameit/testing/numerical/test_fa_pipeline.py::test_coupled_netcdf_sources_do_not_need_fa_backend

Observed: **25 passed, 3 skipped**, only the optional candidate and two native
fixture cases. CI now runs the admission/failure tests with extras absent and
with the existing FA wheel, plus a Python-3.13 pinned-candidate job. Hosted CI has
not been executed locally. No supplied real FA payload, large production run,
private-data upload, EPyGrAM import or stable scientific promotion was performed.
