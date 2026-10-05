How to add a new tracker
========================

FrameIt uses a plugin-based system that makes it straightforward to integrate a new tracking method.
This guide walks you through the four steps required: creating the tracker class, registering it,
declaring the required input variables, and exposing the configuration parameters.

The ``UtrackTracker`` is used as a concrete reference throughout.

Overview of the tracker system
-------------------------------

All trackers inherit from the abstract base class ``TcTracker`` defined in
``src/frameit/tracking/tracker_core.py``. A tracker must:

- be decorated with ``@register_tracker`` so the factory can discover it;
- declare a ``name`` attribute that matches the value of ``tracking_method`` in the configuration;
- declare a ``logical_fields`` tuple listing the logical names of the fields it consumes;
- implement ``from_config(cls, conf: SimulationConfig)`` to build itself from the global configuration;
- implement ``_track_method(self, ds: xr.Dataset) -> xr.Dataset`` to perform the actual tracking.

Step 1 — Create the tracker file
---------------------------------

Create a new file in ``src/frameit/tracking/``. The convention is ``<MethodName>_Tracker.py``.

Minimal skeleton::

    import xarray as xr
    import logging

    logger = logging.getLogger(__name__)

    from .tracker_core import TcTracker, register_tracker
    from frameit.core.settings_class import SimulationConfig


    @register_tracker
    class MyTracker(TcTracker):
        name = "my_tracker"                  # must match tracking_method in the config
        logical_fields = ("u10m", "v10m")    # logical names passed to self._field()

        def __init__(self, var_aliases, **kwargs):
            super().__init__(var_aliases=var_aliases)
            # initialise your tracker here

        @classmethod
        def from_config(cls, conf: SimulationConfig) -> "MyTracker":
            var_aliases = getattr(conf, "tracking_var_aliases", {}) or {}
            # read any extra parameters from conf here
            return cls(var_aliases=var_aliases)

        def _track_method(self, ds: xr.Dataset) -> xr.Dataset:
            u10 = self._field(ds, "u10m")
            v10 = self._field(ds, "v10m")

            # ... your tracking logic ...

            # The output dataset MUST expose "cx" (column index) and "cy" (row index)
            # as integer DataArrays with a "time" dimension.
            out = xr.Dataset({
                "cy": xr.DataArray([...], dims=("time",), coords={"time": ds["time"]}).astype(int),
                "cx": xr.DataArray([...], dims=("time",), coords={"time": ds["time"]}).astype(int),
            })
            return out

Output contract
^^^^^^^^^^^^^^^

``_track_method`` must return an ``xr.Dataset`` with exactly two variables:

- ``cx`` — the **column** (longitude) index of the detected cyclone centre, dtype ``int``.
- ``cy`` — the **row** (latitude) index of the detected cyclone centre, dtype ``int``.

Both must share a ``time`` coordinate aligned with ``ds["time"]``.
If no cyclone is detected at a given time step, return ``0`` rather than ``NaN``, since the output is cast to ``int``.

Optional dependencies
^^^^^^^^^^^^^^^^^^^^^

If your tracker depends on a library that is not always installed, guard the import with a bare
``try/except`` so that FrameIt can still be imported without the optional dependency::

    try:
        from my_optional_lib import SomeClass
    except ImportError:
        pass

Step 2 — Register the tracker
------------------------------

Open ``src/frameit/tracking/__init__.py`` and add an import for your new class.
The ``@register_tracker`` decorator runs at import time, so the import is all that is needed::

    from .PrescribedTrack_Tracker import PrescribedTrack
    from .PressureWind_Tracker import PressureWindTracker
    from .tracker_core import TcTracker, build_tracker_from_config, register_tracker
    from .Utrack_Tracker import UtrackTracker
    from .MyTracker import MyTracker     # <-- add this line

Step 3 — Declare the required variables
----------------------------------------

Input variables are declared in the preset YAML file for the model you are targeting.
For AROME this is ``src/frameit/presets/AROME/vars_trackers.yaml``.

Add a block under ``requested_variables_by_method`` using your tracker's ``name`` as the key.
Specify each vertical coordinate type (``surface``, ``isobaricInhPa``, …), the variable names,
and, for pressure-level variables, the level selection strategy.

Example (from the ``utrack`` entry)::

    requested_variables_by_method:

      my_tracker:
        surface:
          variables: ["u10", "v10"]
        isobaricInhPa:
          variables: ["absv"]
          level_selection: "values"   # "values" | "indices" | "all"
          level_values:  [850]        # used when level_selection = "values"
          level_indices: []           # used when level_selection = "indices"

If your tracker only uses surface fields, omit the ``isobaricInhPa`` block entirely.

Variable aliases
^^^^^^^^^^^^^^^^

Every variable name used internally by your tracker **must** have an entry in
``src/frameit/presets/AROME/model_name_map.yaml`` under ``tracking_var_aliases``, even when the
internal name and the model-file name are identical::

    tracking_var_aliases:
      u10m:  "u10"
      v10m:  "v10"
      absv:  "absv"     # <-- add any alias your tracker needs

Logical names and native names
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A tracker never uses model-file names directly. It works with *logical* names
(``mslp``, ``u10m``, ``v10m``, ...), which ``tracking_var_aliases`` maps to the *native*
names of each model (``prmsl`` for AROME, ``MSLP`` for Meso-NH).

- ``logical_fields`` lists the logical names your tracker needs. It must contain every
  name passed to ``self._field()`` in ``_track_method``.
- Before tracking, the base class translates ``logical_fields`` into native names and
  checks that all of them are present in the dataset. Missing variables are reported
  together, in a single error.
- The attribute must be named ``logical_fields``. Any other name (for example
  ``required_fields``) is silently ignored, and the check is then skipped.

Step 4 — Expose configuration parameters
-----------------------------------------

If your tracker requires parameters beyond the standard ones, add them to the ``SimulationConfig`` dataclass in
``src/frameit/core/settings_class.py``::

    # My tracker options
    my_tracker_weights_file: str = None
    my_tracker_use_gpu: bool = False
    my_tracker_batch_size: int = 16

Update ``__init__`` to accept the new parameters::
 
    def __init__(self, var_aliases, weights_file, use_gpu=False, batch_size=16):
        super().__init__(var_aliases=var_aliases)
        self.weights_file = weights_file
        self.use_gpu      = use_gpu
        self.batch_size   = batch_size
 
Then read them back in ``from_config`` and forward them to ``__init__``::
 
    @classmethod
    def from_config(cls, conf: SimulationConfig) -> "MyTracker":
        var_aliases = getattr(conf, "tracking_var_aliases", {}) or {}
 
        weights = getattr(conf, "my_tracker_weights_file", None)
        if weights is None:
            raise ValueError(
                "tracking_method='my_tracker' requires "
                "'my_tracker_weights_file' to be set in the configuration."
            )
 
        use_gpu    = getattr(conf, "my_tracker_use_gpu", False)
        batch_size = getattr(conf, "my_tracker_batch_size", 16)
 
        return cls(
            var_aliases=var_aliases,
            weights_file=weights,
            use_gpu=use_gpu,
            batch_size=batch_size,
        )

Summary of files to modify
----------------------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - File
     - Change
   * - ``src/frameit/tracking/<Name>_Tracker.py``
     - Create — implement ``TcTracker`` subclass.
   * - ``src/frameit/tracking/__init__.py``
     - Add import of your new class.
   * - ``src/frameit/presets/<MODEL>/vars_trackers.yaml``
     - Add variable declarations under ``requested_variables_by_method``.
   * - ``src/frameit/presets/<MODEL>/model_name_map.yaml``
     - Add any variable aliases your tracker needs.
   * - ``src/frameit/core/settings_class.py``
     - Add configuration fields for tracker-specific parameters.
