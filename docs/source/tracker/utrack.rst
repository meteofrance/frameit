Utrack (AI) tracker
===================

.. warning::

   UTrack cannot execute current tracking requests: its selected-input binding
   is unavailable. Installing dependencies or weights does not enable it.
   The beta adapter below is limited to AROME.

Overview
--------

The ``utrack`` adapter uses the U-Net model of
`Raynaud et al. (2024) <https://journals.ametsoc.org/view/journals/aies/3/2/AIES-D-23-0059.1.xml>`_
to detect cyclone wind structure, including maximum-wind and hurricane-force-wind
areas, in AROME convective-scale forecasts.

The model was trained and evaluated on a dataset of 400 hand-labeled AROME forecasts over the
West Indies domain, covering Atlantic hurricane seasons 2016–2018.

Required input fields
---------------------

This tracker requires the following variables to be available in the dataset:

- 10 m zonal wind component (``u10``),
- 10 m meridional wind component (``v10``),
- Absolute vorticity at 850 hPa (``absv``).

The dataset must also carry a latitude coordinate named ``latitude`` or ``lat``.
Latitude is passed to UTrack to reverse the sign of raw absolute vorticity south
of the equator, matching the model's cyclonic-positive convention. Input
vorticity must retain its raw signed convention to avoid applying this correction
twice.

Output
------

The tracker returns two 1D arrays:

- ``cy(time)``: row index of the estimated center,
- ``cx(time)``: column index of the estimated center,

Both are integers in the adapter's track dataset, not available current-run outputs.

Configuration and usage
-----------------------

The declaration uses the following fragment. These settings do not remove the
execution limitation above.

.. code-block:: yaml

   region:
     tracker:
       method: utrack
       weights_file: ./model_latest.ckpt
       use_gpu: false
       batch_size: 16

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Parameter
     - Default
     - Description
   * - ``region.tracker.weights_file``
     - *(required)*
     - Path to the separately supplied Utrack model checkpoint file.
   * - ``region.tracker.use_gpu``
     - ``false``
     - Whether to run inference on GPU. Set to ``true`` if a CUDA-capable device is
       available.
   * - ``region.tracker.batch_size``
     - ``16``
     - Number of time steps processed in a single forward pass. Reduce this value if
       GPU or CPU memory is limited.

Dependencies
------------

The optional adapter requires ``torch`` and the external
`utrack package <https://git.meteo.fr/hoarauk/unet_tracker>`_.
Neither is needed for core extraction, and neither enables the missing binding.

Model weights
-------------

A trained model checkpoint file is required. The weights are **not publicly distributed**;
contact the model authors to obtain a copy. Once you have the file, set
``region.tracker.weights_file`` as shown above; paths are YAML-relative.

Known limitations
------------------

* **Beta and external assets:** the UTrack package and separately obtained weights
  are required. Their presence is not verification of a new dataset or regime.
* **AROME scope:** generalisation beyond the model's training conditions is
  unestablished.
* **No detection:** the current implementation warns and returns native grid
  indices ``(0,0)`` when no cyclone is found. These are not a confirmed centre or
  geographical zero; downstream users must treat the failure explicitly.
* **Multiple detections:** the adapter selects the first returned detection and
  does not provide researcher-seeded multi-object association.
* **Input conventions:** winds and signed 850-hPa vorticity must share compatible
  geography and the expected conventions; hemisphere correction must not be applied twice.
* **Qualification gap:** separately controlled weights and limited reference
  evidence prevent a general scientific qualification claim.
