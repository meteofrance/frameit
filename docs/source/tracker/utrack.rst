Utrack (AI) tracker
===================

.. warning::

   UTrack cannot execute a version-3 tracking request: its selected-input binding
   is not implemented. Configuration and an optional adapter exist, but installing
   dependencies or weights does not enable this path. The beta adapter described
   below is limited to AROME and requires separately obtained weights.

Overview
--------

The Utrack adapter (declared as ``region.tracker.method: utrack``) estimates the cyclone center at each time
step using a convolutional neural network based on the **U-Net architecture**, as introduced
by `Raynaud, et al. (2024) <https://journals.ametsoc.org/view/journals/aies/3/2/AIES-D-23-0059.1.xml>`_.
The model was designed to detect the TC wind structure — including the maximum wind speed area
and the hurricane-force wind speed area — directly from AROME convective-scale NWP outputs,
without relying on heuristic rules or empirical thresholds.

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

Both are integers in the adapter's track dataset. This does not establish a
working version-3 execution path.

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

The optional adapter requires ``torch`` and ``utrack``. Neither is needed for
core extraction. These dependencies do not enable version-3 UTrack execution.

Clone the repository and install the package locally:

.. code-block:: bash

   git clone https://git.meteo.fr/hoarauk/unet_tracker
   cd unet_tracker
   pip install .

Model weights
-------------

A trained model checkpoint file is required. The weights are **not publicly distributed**;
contact the model authors to obtain a copy. Once you have the file, set
``region.tracker.weights_file`` as shown above; paths are YAML-relative.

Known limitations
------------------

* **Beta and external assets:** the UTrack package and separately obtained weights
  are required. Their presence is not verification of a new dataset or regime.
* **AROME scope:** FrameIt's adapter supports AROME inputs; generalisation beyond
  the model's training conditions is not established by these documentation tests.
* **No detection:** the current implementation warns and returns native grid
  indices ``(0,0)`` when no cyclone is found. These are not a confirmed centre or
  geographical zero; downstream users must treat the failure explicitly.
* **Multiple detections:** the adapter selects the first returned detection and
  does not provide researcher-seeded multi-object association.
* **Input conventions:** winds and signed 850-hPa vorticity must share compatible
  geography and the expected conventions; hemisphere correction must not be applied twice.
* **Qualification gap:** unavailable weights and the reduced fixture's limited
  spatial context prevent treating the excluded crop case as passed qualification.
