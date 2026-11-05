Contributing documentation
==========================

Before each commit
------------------

Review what a researcher needs to know about the change: commands, settings and
defaults, processing, outputs, installation and limitations. Update the affected
canonical pages, examples, template comments and figures in the same change. If
none are affected, record ``Docs: no user-facing impact because ...`` in the
commit or handover. A prose edit with no useful information is not required.

Build documentation strictly in ``frameit_env``, run the publication check and
inspect the affected HTML. Show visual changes in the OpenCode GUI browser and
keep the preview available for feedback. This is a contributor obligation, not a
local Git hook or a dependency of scientific processing.

Writing for researchers
-----------------------

Write for a graduate-level researcher familiar with a README, Conda and bash;
do not assume Python programming experience. Use plain, professional language,
without slogans or artificial encouragement. Explain consequential scientific
choices where the reader makes them, then link to the equations, evidence and
reference details rather than repeating them throughout the site.

Keep the README short. Use a guided first run followed by task-oriented guides,
with scientific concepts, reference and troubleshooting available separately.
Reuse sound explanations, method notes and figures; preserve useful page URLs
and anchors when changing navigation. Development records belong outside
``docs/source`` and must not be included in published search, downloads or
inventories.

Distinguish implemented behavior, planned work, experimental methods and
remaining validation gaps. Check claims against the implementation and actual
evidence, not just the roadmap. A passing test or plausible figure is not proof
of scientific validity or human scientific approval.

Templates and executable examples
----------------------------------

Every guide explaining a starter template must show its exact generation
command, tested against the documented revision. Keep starter templates minimal
but retain relevant comments about adaptation points, units, assumptions and
non-obvious consequences. Do not hide a consequential scientific declaration
merely to shorten the YAML. Exhaustive settings belong in reference/inspection;
the effective configuration belongs in provenance, not in a starter catalogue.

The v2.1 key map and concrete template catalogue are still subject to maintainer
approval. Until implemented and verified, describe them as proposals, not runnable
commands. Do not silently substitute quantities, infer ambiguous units, change
defaults, fill missing samples or enable unrequested processing to make an
example work. Preserve the distinction between missing and zero, sampling
location, vector basis, reference-frame motion and time support.

Use compact synthetic fixtures first and label them instructional rather than
real-producer qualification. Keep source data read-only, use fresh output
directories and check values and metadata with ordinary readers. Do not include
private paths, credentials or unapproved data in examples or preview artifacts.

Figures
-------

Place a figure beside the decision it clarifies. Give it meaningful alternative
text, a caption, labels, units and a legend where needed; do not rely on color
alone. Identify schematics, synthetic examples, real results and validation
evidence accurately. Keep the editable SVG or a reproducible generation recipe
with the figure. Avoid decorative illustrations and do not change scientific
data colormaps to match documentation branding.

The supplied FrameIt artwork and the planned shared accessible styling will be
reviewed with the editorial pilots. Preserve that artwork and existing scientific
distinctions; do not introduce another logo or theme during an unrelated edit.

Local HTML preview
------------------

Run commands from the repository root. Use the required Python 3.13 environment
for builds and checks; if it is unavailable, report the blocker rather than
switching interpreters:

.. code-block:: bash

   conda run --no-capture-output -n frameit_env python -c 'import sys; assert sys.version_info[:2] == (3, 13); print(sys.version)'
   conda run --no-capture-output -n frameit_env sphinx-build -q -W --keep-going -b html docs/source build/docs-preview/baseline-01
   conda run --no-capture-output -n frameit_env python docs/check_publication.py build/docs-preview/baseline-01
   conda run --no-capture-output -n frameit_env python -m unittest discover -s docs -p test_check_publication.py

Choose a new iteration directory for each meaningful revision, such as
``baseline-02``. Do not overwrite an earlier iteration or delete a broad build
directory. A failed strict build is not a successful preview: report the failure
and label any last successful iteration accurately.

After the build and publication check succeed, serve only generated public HTML:

.. code-block:: bash

   conda run --no-capture-output -n frameit_env python -m http.server 8765 --bind 127.0.0.1 --directory build/docs-preview

Agents must start this command through OpenCode's shell tool in background mode.
If the port is occupied, choose a free one; do not terminate another process.
Never serve the repository root or source datasets, and do not bind publicly.

Load the browser skill and open
``http://127.0.0.1:8765/baseline-01/index.html`` in the OpenCode GUI browser/Review
pane. Keep the returned tab ID for subsequent operations, verify the page loads
and share the actual clickable URL. Inspect the changed pages at desktop and
narrow widths. Manual rebuild and navigation to the next iteration are sufficient;
no frontend, plugin or hot-reload dependency is needed.

Keep the server running until feedback is finished or the maintainer requests a
stop. Put the owned server process, current iteration URL and restart command in
the session handover, not in committed machine state. If the GUI is disconnected,
report the visual-review blocker; screenshots do not replace the live page or
establish that the maintainer reviewed it.
