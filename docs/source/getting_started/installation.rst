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
The reference environment uses Python 3.13 to install a published
``falfilfa4py`` wheel. The optional ``fa`` pip extra exposes the same dependency
on platforms/Python versions supported by its publisher. FrameIt isolates native
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
