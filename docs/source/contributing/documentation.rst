Contributing documentation
==========================

Before each commit
------------------

Review what a researcher needs to know about the change: commands, settings and
defaults, processing, outputs, installation and limitations. Update the affected
canonical pages, examples, template comments and figures in the same change. If
none are affected, record ``Docs: no user-facing impact because ...`` in the
commit or handover.

Build documentation strictly in ``frameit_env``, run the publication check and
inspect the affected HTML. Show visual changes in a browser and
keep the preview available for feedback.

Writing for researchers
-----------------------

Write for researchers who know bash, YAML, Python and their data, but not FrameIt.
Use plain, professional language, without slogans or artificial encouragement.
Explain consequential scientific
choices where the reader makes them, then link to the equations, evidence and
reference details rather than repeating them throughout the site.

Use short sentences and direct verbs. Put one main idea in each sentence.
Explain FrameIt, not basic YAML, bash or meteorology. Remove repeated cautions
and words that do not help the reader make a choice. Keep a sentence only if it
helps the reader choose settings, run a task, interpret results or solve a problem.
Remove recaps of what the preceding steps do not require, defensive asides,
development progress reports and unsupported feature plans. Keep consequential
scientific assumptions, limits and failure behavior beside the relevant choice;
link to the full method record instead of repeating it.

Keep **Your first run** and **Quick start** distinct. The first run teaches the
YAML through a checked example. Quick start is a short template/edit/check/run
reminder for users who know their data. Installation should show one clear route;
advanced setup belongs in the environment reference. Show the commands to run,
not commentary about alternative steps the reader was never asked to take.

Keep analysis and display in downstream tools. Documentation figures may explain
the data and methods. HPC instructions must use site-neutral paths and settings.

Document the current ``schema_version: "2.1"`` only. Do not publish schema history,
conversion instructions or upgrade pages. Internal development and provenance
records are separate from user guidance.

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

Describe commands as runnable only after verification. Do not silently substitute
quantities, infer ambiguous units, change
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

Check every figure at desktop and narrow widths, including 320 px. Check its
displayed bounds **and** the SVG drawing/text bounds; a correct image box does not
prove that labels fit. Keep space around text and strokes. Fit the image to the
page and viewport without distortion, and add a full-size image target. Do not
use a fixed height that crops content. Remove the screen-height limit for print.

Use the supplied FrameIt artwork and shared accessible styling throughout the
documentation. Preserve that artwork and existing scientific
distinctions; do not introduce another logo or theme during an unrelated edit.

Brand assets and restrained styling
------------------------------------

The unchanged masters are ``_static/logo/frameit_logo_vector.svg`` and
``frameit_logo_symbol_vector.svg``. The **full wordmark** identifies the site on a
light background; the **symbol** is the favicon/compact mark. Keep the original
colors, aspect ratio and clear space. Do not crop, stretch, invert or recolor them.

``html_logo`` uses the outlined ``_static/logo/frameit_logo.svg``, not the
text-bearing master. The source uses **Simpletix**, Version 1. Its 2172×724
composition, centred baseline and colors are preserved by ``docs/outline_logo.py``.
Regeneration needs FontTools and that
exact font face. From the repository root:

.. code-block:: bash

   fc-match -f '%{family} %{style}\n%{file}\n' simpletix
   FONT=$(fc-match -f '%{file}' simpletix)
   conda run --no-capture-output -n frameit_env python docs/outline_logo.py --font "$FONT" --output docs/source/_static/logo/frameit_logo.svg

Verify the font identity, compare the outlined result to the supplied artwork,
and run the asset checks. If the exact face cannot be verified, request an
outlined master; never accept font substitution. The published wordmark must
contain no live text, script, bitmap or external font/resource dependency. Keep
the unchanged source masters separate from the served derivative.

Shared tokens live in ``_static/custom.css``:

* Navy ``#021633``: text, headings and structure.
* Teal ``#00978F``: artwork/diagram accent; darker ``#006B65`` for text links.
* Orange ``#EC7600``: sparse artwork emphasis; ``#9A4400`` for text/focus on light surfaces.
* Light orange ``#F79335``: trajectory details and focus on dark navigation.

Keep normal text/link contrast at least 4.5:1 and large text/relevant control
boundaries at least 3:1. Retain underlined links and visible keyboard focus.
The small ``_templates/layout.html`` override keeps the existing theme's menu
behavior while supplying heading levels and a native keyboard-operable mobile
button. Keep that control labelled and check menu targets at narrow widths.
Notes, warnings and errors keep distinct labels and contrast-tested headings;
color alone must not carry status. Keep body text in a readable face. Do not add
hosted fonts or change the Sphinx theme.
Explanatory SVGs share these tokens and readable labels, but **scientific data
colormaps retain their scientific meaning** rather than adopting a brand palette.

``python docs/check_publication.py <artifact>`` checks configured source/build
marks, publication boundaries and local HTML links/assets/fragments. Downloads
and URL-encoded filenames must resolve inside the artifact. External URLs are
not fetched; this does not verify scientific references. Use relative local URLs:
root-relative ``/_static/...`` links drop the site's hosting prefix and are rejected.

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

Open ``http://127.0.0.1:8765/baseline-01/index.html`` in your browser. Check the
affected pages at desktop and narrow widths. Rebuild into a new iteration
directory after edits.

If port 8765 is occupied, choose another free port. Serve only generated HTML,
not the repository root or source datasets, and keep the server bound to
``127.0.0.1``. Stop the preview server with ``Ctrl+C`` when finished.
