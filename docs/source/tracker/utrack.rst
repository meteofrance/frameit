Utrack (AI) tracker
===================

.. warning::

   This tracker is currently in **beta**. The underlying model is not publicly available
   and must be obtained separately (see `Model weights`_ below). It is only compatible
   with **AROME** model outputs. In addition, the model frequently fails to detect a cyclone
   on some inputs; in those cases it falls back to coordinates ``(0, 0)``, which should be
   treated as a missing value in downstream processing.

Overview
--------

The Utrack tracker (``tracking.method: utrack``) estimates the cyclone center at each time
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

both returned as integers and packaged in an ``xarray.Dataset``:

.. code-block:: python

   xr.Dataset({"cy": cy, "cx": cx})

Configuration and usage
-----------------------

To activate this tracker, set ``tracking.method: utrack`` in the YAML configuration and
provide the three parameters below.

.. code-block:: yaml

   tracking:
     method: utrack
     utrack:
       weights_file: ./model_latest.ckpt
       use_gpu: false
       batch_size: 16

.. list-table::
   :header-rows: 1
   :widths: 35 15 50

   * - Parameter
     - Default
     - Description
   * - ``tracking.utrack.weights_file``
     - *(required)*
     - Path to the Utrack model checkpoint file. The simulation will raise a
       ``ValueError`` if this parameter is not set.
   * - ``tracking.utrack.use_gpu``
     - ``false``
     - Whether to run inference on GPU. Set to ``true`` if a CUDA-capable device is
       available.
   * - ``tracking.utrack.batch_size``
     - ``16``
     - Number of time steps processed in a single forward pass. Reduce this value if
       GPU or CPU memory is limited.

Dependencies
------------

This tracker requires the ``utrack`` package to be installed. It is not part of the
standard FrameIt dependencies. If ``utrack`` is not installed, the tracker class is
still importable but will raise an error at instantiation time.

Clone the repository and install the package locally:

.. code-block:: bash

   git clone https://git.meteo.fr/hoarauk/unet_tracker
   cd unet_tracker
   pip install .

Model weights
-------------

A trained model checkpoint file is required. The weights are **not publicly distributed**;
contact the model authors to obtain a copy. Once you have the file, set
``tracking.utrack.weights_file`` in your configuration (paths are YAML-relative):

.. code-block:: yaml

   tracking:
     method: utrack
     utrack:
       weights_file: ./model_latest.ckpt
