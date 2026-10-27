Installation of FrameIt
=======================

In this section, we describe the minimal steps required to install **FrameIt** for development and reproducible scientific workflows.

1. Prerequisites
----------------

- **Python**: 3.10 or newer.
- **Git**: to clone the repository.
- **a dedicated environment manager** : conda/mamba.

2. Get the source code
----------------------

In a terminal, go to your installation directory and run:

.. code-block:: bash

   git clone <FrameIt_REPO_URL>
   cd frameit

You should end up with a structure similar to:

.. code-block:: text

   .
   ├── docs
   ├── environment.yaml
   ├── pyproject.toml
   ├── scripts
   └── src

The file ``environment.yaml`` define the dependencies required by **FrameIt**.
The reference parent environment uses Python 3.13 for GRIB/NetCDF/ESMF. FA uses a
separate helper with EPyGrAM 2.1.0 and its unmodified upstream dependencies, plus
the qualified ctypesForFortran 1.3.0 bridge. The optional ``fa`` pip extra supplies
this stack; ``fa-epygram`` is an identical installation alias. ``environment.yaml``
includes the helper setup recipe; select it with ``input.fa.python_executable``.
The C4 record documents an existing overlay matrix shutdown failure, so a shared
GRIB/ESMF/EPyGrAM-pin environment is not distribution-qualified by the passing
helper tests. See :doc:`../user_guide/fa_epygram_c4` for migration
from the retired raw reader/extra. FrameIt isolates native
FA decoding from conda's GRIB/ecCodes reader automatically; matching version
numbers alone did not resolve their observed same-process native-library conflict.
See :doc:`../user_guide/fa_inputs` for the implemented scope and declarations.

3. Create and activate the Python environment using a conda/mamba environment
-----------------------------------------------------------------------------


If you already have conda/mamba installed, use the file ``environment.yaml``:

.. code-block:: bash

   conda env create -f environment.yaml
   conda activate frameit_env


4. Install the FrameIt package
------------------------------

From the repository root (where ``pyproject.toml`` is located):

.. code-block:: bash

   pip install -e .

Quick verification:

.. code-block:: bash

   python -c "import frameit; print('frameit import OK')"
