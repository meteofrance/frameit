Spectral FA support and limitations
===================================

**Production spectral FA execution is blocked.** FrameIt can retain selected
encoding/header facts, but it does not decode, export raw coefficients, transform,
extract or polar-sample a spectral physical field. There is no spectral YAML
activation key. Installing ecTrans or EPyGrAM does not establish a qualified
coefficient/producer contract. Native atmospheric cubes use admitted gridpoint
records only; see :doc:`fa_atmosphere` and :doc:`fa_baseline`.

Coefficients are not gridpoint values
-------------------------------------

Observed spectral flags such as 103/18 on ``S001TEMPERATURE`` or
``S001WIND.U.PHYS`` identify representation/encoding facts, not independently
decoded coefficients. Indexed/compressed word counts and ``nx*ny`` cannot supply
coefficient dimensions. A plausible grid-shaped array is not proof of a valid transform.

Selected spectral records fail before physical payload decoding or construction
of a transform-bearing H2D field. The parent also rejects spectral, unknown or
blocked read descriptors even if transferred dtype/shape resemble grid values.
A transform installation does not resolve separate native -91 header/encoding
failures; those need their own upstream explanation and trusted decode.

Inspection preserves exact ``KTYPTR``/``KTRONC`` words in
``native.spectral_contract``, with unresolved coefficient count/order/space/
normalization/transform truncation and explicit blocked status. FANION
``truncation`` can mean *under-truncation*, not a complete transform truncation.
The regional inspector retains only its admitted active rectangular header
prefixes; it does not claim complete Gaussian/reduced/spectral active-array
retention, including ``KNOZPA``. Those layouts require authoritative active counts
before interpretation, not a rectangular reshape.

Requirements for each encoding and producer release
---------------------------------------------------

#. A readable native coefficient decode with authoritative dimensions, scaling,
   missing-value semantics and native build/release identity. Flags alone do not
   qualify it; no compressed-length or grid-size allocation fallback is allowed.
#. A documented FA header/active-array-to-transform contract: coefficient order,
   Fourier versus Legendre space, full/under-truncation, normalization, original
   grid, Earth model and CI/C/extension zones.
#. Independently trusted coefficient and transformed native-grid fields, matched
   by quantity/level/time/mask, with justified packing/transform tolerances,
   appropriate fixture permissions and human scientific review.
#. Compatible maintained wrapper/native versions and bounded/measured coefficient,
   workspace, mask, full-grid and transfer resources. Failure, missing dependency,
   crash and unchanged gridpoint contracts need verification before admission.

Additional vector/physical-coordinate operations require their own field sampling,
full/interface coefficients, units/reference pressure and basis/staggering evidence.
No pressure/height, gradient, vector conversion or diagnostic becomes mandatory
because coefficients or dependencies exist.

Separate library evaluation: scope and equations
------------------------------------------------

The optional **ecTrans / ectrans4py 1.6.0 regional scalar double-Fourier evaluation**
uses prescribed analytical coefficients, not FA input files. It is candidate
numerical-library evidence, **not supported spectral field extraction or a stable
scientific diagnostic**. The
`versioned wrapper source <https://github.com/ecmwf-ifs/ectrans/blob/1.6.0/src/ectrans4py/__init__.py>`_
and `publisher metadata <https://pypi.org/pypi/ectrans4py/1.6.0/json>`_ define the
evaluated software/API contract. Other native releases, including
`ecTrans 2.0.0 <https://github.com/ecmwf-ifs/ectrans/releases/tag/2.0.0>`_, have
distinct schedules/APIs and are not interchangeable qualifications.

The bounded evaluation uses complete 12x12, 18x12 and 12x12 grids at 1000-m
spacing, truncations (3,3), (5,3), (2,2), and native-inquiry counts of 44/64/24
real coefficients for 144/216/144 gridpoints. Coefficient allocations use the
inquiry count. The library owns coefficient reordering (``LREORDER=True``);
derivatives are disabled (``LGRADIENT=False``). These choices do not map unknown
FA header words to truncations or qualify extension zones/Earth models.

Independent closed-form truth uses :math:`X=2\pi m i/n_x` and
:math:`Y=2\pi n j/n_y`. For the evaluated four-real coefficient blocks and
positive m,n the scalar basis is:

.. math::

   4(A\cos X\cos Y - B\cos X\sin Y
     - C\sin X\cos Y + D\sin X\sin Y).

Pure-X modes are :math:`2(A\cos X-C\sin X)`; pure-Y modes are
:math:`2(A\cos Y-B\sin Y)`. The zero-wavenumber constant is A.
Zero, constant 1.25, unit-amplitude cosine/sine signs, all four mixed slots and
each axis's truncation edge are compared directly to these equations, not to a
forward-transform/round-trip oracle. The specified bound is ``rtol=0, atol=5e-13``:
float64 roundoff allowance for at most five waves and 216 points. The recorded
small-mode maximum error ``5.551115123125783e-15`` is limited library evidence,
not a tolerance or accuracy claim for packed real fields, all truncations,
another version or production resources.

The evaluation changes no upstream mathematics/normalization/reordering and
does not exercise global Gaussian/Legendre, gradient, vector or physical-coordinate
operations. It reads no source fields and accepts no arbitrary production
parameters. A bounded fresh child uses one native thread, three resolution slots,
no core dumps/unlimited-stack request, and a 30-second timeout. Missing/different
dependencies, nonfinite/incorrect results, timeout or native death fail the attempt.
Failure-injection cases are lifecycle checks, not diagnoses of a particular native
library defect. No spectral FA generator or real-field decode is qualified by them.

The optional evaluation requires ctypesForFortran 1.3.0 with the pinned wrapper;
the reference FA environment already uses that bridge. This is not an instruction
to alter an environment or activate a transform. Gridpoint FA workers reject
ecTrans imports. Release-matched producer conventions and scientific review
remain missing even if the analytical evaluation succeeds.

Metadata and output boundary
----------------------------

Inspection facts are portable JSON and remain in ordinary per-file provenance;
they are not physical output variables. Explicit library-evaluation reports record
versions/revision/effective arguments, counts, per-mode errors/tolerance, resource
policy, diagnostics and unresolved gates. Even ``passed_limited`` is paired with
``production_spectral_fa: blocked``. Neither coefficients nor purported physical
fields are exported by that evaluation.

Ordinary GRIB/NetCDF/gridpoint FA, exact-common/strict times, independent grids,
selected-only diagnostics and continuous bilinear polar sampling retain the
contracts in :doc:`fa_inputs`. There is no silent spectral-to-grid fallback,
conservation claim or new method selection. Native coefficient/scaling/mask,
real transformed-field and production-resource evidence remain unresolved.
