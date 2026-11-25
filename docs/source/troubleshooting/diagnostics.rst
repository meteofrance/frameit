Post-run diagnostics problems
=============================

.. _e2001:

E2001 — Invalid diagnostic settings
------------------------------------

Check the reported key under ``diagnostics``. Use only the supported agency,
source kind and selectors. A wind selector needs either ``speed`` or both
``u`` and ``v``. Run ``frameit validate frameit.yaml --schema-only --cli`` again
after correcting the YAML.

.. _e2002:

E2002 — Parent cannot supply the diagnostic
-------------------------------------------

Check the parent with ``frameit status``. Use the matching completed directory
with its original request and a saved trajectory. A completed full-domain run
without centres cannot supply a trajectory. Do not change or recreate records
to pass this check.

.. _w2001:

W2001 — Planned crop does not list a selected field
---------------------------------------------------

Check the exact names under ``products.model_grid.fields`` and the diagnostic
field selectors. Validation will not add fields to the crop. For an existing
run, check the recorded product rather than the planned field list.
