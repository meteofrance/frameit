Input files and readers
=============================

Run ``frameit inspect frameit.yaml`` to list the files, fields and
times FrameIt can see. Inspection does not prove that the data support
every requested calculation.

.. _e1201:

E1201: No input files match
-----------------------------------------------------------

Read the source name and pattern in the error. A path in the YAML
starts at the YAML file's directory. Check that the files exist and
that ``exclude`` does not remove them. Put a pattern such as
``"./data/*.nc"`` in the YAML, not on the command line in place of
the YAML path. Run inspection and check the selected file list.

.. _e1202:

E1202: FrameIt could not read an input file
-----------------------------------------------------------

Check the named file first. Can the account running FrameIt read it?
Is the copy complete, and can the reader for that format open it?
An extension such as ``.nc`` does not prove that a file is NetCDF.
Select a readable copy or the right file, then inspect again.
See :doc:`../reference/inputs` for supported inputs.

.. _e1203:

E1203: The selected files do not establish one source type
-----------------------------------------------------------

Check the model, format, and profile in the YAML against the file
headers and the producer's notes. Do not group different models or
file types in one source. FrameIt also allows only one source of each
physical type: atmosphere, ocean, or surface. Keep only the compatible
files for the request and inspect again. Do not rename a file to make
it look like a different format.

.. _e1204:

E1204: The input grid is not supported
-----------------------------------------------------------

Read the grid or coordinate name in the error. Compare the dimensions,
coordinate values, and grid description of the named files. FrameIt
does not make different grids equal when it reads them. Use files on
a supported grid for the requested operation. Inspect again and check
the reported grids for each field.

.. _e1205:

E1205: The selected FA profile, grid, or record is not supported
----------------------------------------------------------------

Check the producer, profile, and native record name in
:doc:`../user_guide/fa_inputs`. A readable header does not mean the
record can be decoded. FrameIt does not turn spectral coefficients
into grid values or reconstruct packed SURFEX fields. Check eligibility
with inspection before selecting a different, scientifically suitable input.

.. _e1206:

E1206: FrameIt could not establish FA scaling
-----------------------------------------------------------

Read the native record name and the scaling evidence in the decoder
message. Check the record with the producer. Do not assume it needs no
scaling. Use an explicit unscaled declaration only when you can justify
it for that record. See :doc:`../user_guide/fa_contracts` for the
declaration and the provenance to check on a small retry.

.. _e1207:

E1207: FrameIt could not use a selected file's metadata
----------------------------------------------------------------------

Read the file name and the first metadata error. Check that the
reader can open the file. Compare the named header, axis or record
with a supported example in :doc:`../reference/inputs`. Inspect one
file at a time to find the incompatible file. Do not edit the
source metadata unless you can verify the correction.

.. _e1007:

E1007: An FA decoder request timed out
-----------------------------------------------------------

Try inspection with one file. Check that the input can be read from
the machine running FrameIt. If the request is sound but slow,
check ``reader.timeout_seconds`` for that source. Set a longer timeout
only if you understand the cost. Retry the small request first.

.. _e1008:

E1008: An FA record is larger than the point limit
-----------------------------------------------------------

Check the native grid size and ``reader.max_points``. Even a small crop
can require reading a whole native field. A point limit is not a memory
limit. Use a smaller suitable input, or change the limit only after
checking the memory allocation. Retry with one small selection.

.. _w1201:

W1201: FrameIt used the default FA Earth radius
-----------------------------------------------------------

FrameIt used 6,371,229 m for a supported FA grid. Check the producer's
Earth radius. If it differs, declare ``sources.<name>.fa.earth_radius_m``
and validate again. Check the effective radius in provenance.

.. _w1202:

W1202: The request allows a record to be used without FA scaling
----------------------------------------------------------------

The declaration permits a fallback. It does not prove that it was
needed or that unscaled values are correct. Check the decoder scaling
status and the producer's evidence before using the field. Remove an
unjustified declaration and validate again.

.. _w1203:

W1203: The FA decoder printed a warning
-----------------------------------------------------------

Read the decoder text after the code. A warning about ``FMULTM`` or
``FMULTE`` does not prove that factors are missing. Check the recorded
scaling status and any error that follows. See
:doc:`../user_guide/fa_environment` for native decoder messages.
