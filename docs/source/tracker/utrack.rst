Utrack (AI) tracker
===================

.. note::

   This beta adapter runs on AROME NetCDF and GRIB inputs only. Meso-NH and
   FA inputs are not supported.

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

FrameIt reads the following inputs independently of the fields selected for
export. Supply all three fields at every selected time on the same grid:

- 10 m Earth-relative wind components (``u10``, ``v10``), compatible with m/s;
- Raw signed absolute vorticity (``absv``), in inverse seconds, at exactly
  850 hPa. FrameIt does not interpolate to 850 hPa.

The dataset must also carry a latitude coordinate named ``latitude`` or ``lat``.
Latitude is passed to UTrack to reverse the sign of raw absolute vorticity south
of the equator, matching the model's cyclonic-positive convention. Input
vorticity must retain its raw signed convention to avoid applying this correction
twice.

Output
------

The tracker uses the first detection's maximum-wind centre at each time.
Fractional pixel coordinates are truncated to native row and column indices,
as in the original adapter. Select ``products.track: true`` to publish the
ordinary FrameIt trajectory with geographic coordinates. If no centre is
detected at a selected time, the run fails without publishing a track.

Configuration and usage
-----------------------

Add the following to an AROME configuration:

.. code-block:: yaml

   region:
     tracker:
       method: utrack
       weights_file: ./model_latest.ckpt
       use_gpu: false
       batch_size: 16

Run ``frameit validate`` before ``frameit run``. Validation checks input
metadata, the checkpoint path and availability of the optional modules. It
does not load the checkpoint or test whether the cyclone will be detected.

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
     - Maximum number of full-grid time steps loaded and sent to the model
       together. Reduce this value if GPU or CPU memory is limited.

Dependencies
------------

The optional adapter requires ``torch`` and the external
`utrack package <https://git.meteo.fr/hoarauk/unet_tracker>`_.
Neither is needed for core extraction.

Model weights
-------------

A trained model checkpoint file is required. The weights are **not publicly distributed**;
contact the model authors to obtain a copy. Once you have the file, set
``region.tracker.weights_file`` as shown above; paths are YAML-relative.

.. warning::

   Run only with a checkpoint whose origin you trust. The external UTrack
   checkpoint loader can deserialize Python objects. Do not run a configuration
   that points to weights obtained from an untrusted source.

Known limitations
------------------

* **Beta and external assets:** the UTrack package and separately obtained weights
  are required. Their presence is not verification of a new dataset or regime.
* **AROME scope:** generalisation beyond the model's training conditions is
  unestablished.
* **Input values:** the tracker requires finite wind and vorticity across
  the input grid. FrameIt does not fill gaps before inference.
* **Multiple detections:** the adapter selects the first returned detection and
  does not provide researcher-seeded multi-object association.
* **Input conventions:** winds and signed 850-hPa vorticity must share compatible
  geography and the expected conventions; hemisphere correction must not be applied twice.
* **Qualification gap:** separately controlled weights and limited reference
  evidence prevent a general scientific qualification claim.
