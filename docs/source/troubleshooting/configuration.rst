Commands and YAML
=================

Use the same configuration file in every check. Start with
``frameit validate frameit.yaml --schema-only``. This checks the settings
without opening input files. Replace ``frameit.yaml`` if you gave the
file another name.

.. _e1101:

E1101: FrameIt could not read the YAML file
-------------------------------------------------------------

Check the path in the error and run ``pwd`` to see your current
directory. Pass the path to the YAML file explicitly. If the file
exists, check that you can open it and that it is not a directory.
Run schema-only validation on that path.

.. _e1102:

E1102: FrameIt could not parse the YAML
---------------------------------------

Open the YAML at the line and column in the error. Check indentation,
quotes, and brackets on that line and the line above it. Use spaces,
not tabs, for indentation. The file must contain one set of named
settings, not a list or an empty document. If the error names a forbidden
character, remove it at the reported position. Save the file as UTF-8
and run schema-only validation again.

.. _e1103:

E1103: The same YAML key appears twice
--------------------------------------

Open the YAML file at the line in the error. Keep one copy of the named
key under that section. If ``files`` was repeated, put the paths you
want in a list under one ``files:`` key. Run schema-only validation
again. The duplicate-key error should be gone.

.. _e1104:

E1104: The schema version is not the number 3
-------------------------------------------------------------

Open the YAML file. Set the top-level line to ``schema_version: 3``.
Do not put quotes around ``3``. If the rest of the file does not match
:doc:`../user_guide/configuration_file`, create a fresh starter and
enter your settings there. Run schema-only validation again.

.. _e1105:

E1105: A YAML setting is not accepted
-------------------------------------

Read the setting name and the expected value in the report. Check the
name, indentation, and allowed values in
:doc:`../user_guide/configuration_file`. If the setting uses a path,
remember that a YAML path starts at the YAML file's directory.
Command-line paths start at the directory where you ran the command.
Run schema-only validation again. For a working configuration,
``frameit config show frameit.yaml --effective`` shows the settings
that FrameIt will use.

.. _e1106:

E1106: The starter file already exists
--------------------------------------

``frameit init`` did not replace the file. Use ``--output`` with a new
path. Use ``--force`` only if you mean to replace that one file.
Check that the command reports the new path before editing.

.. _e1107:

E1107: This starter and these options cannot be used together
-------------------------------------------------------------

For a named starter such as ``nemo-native``, remove ``--tracking``
and ``--coupling``. To combine options, start with a model name such
as ``arome``. Check the supported combinations in
:ref:`starter-catalogue`, then retry with a new output path.
