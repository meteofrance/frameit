# Configuration file for the Sphinx documentation builder.

from __future__ import annotations

import os
import sys
from datetime import date
from importlib.metadata import version as get_version


# Make the package importable for autodoc (src layout)
sys.path.insert(0, os.path.abspath("../../src"))


# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
project = "FrameIt"
author = "Soufflet Clément"
copyright = f"{date.today().year}, {author}"
release = get_version("frameit")

language = "en"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.mathjax",
]

autosummary_generate = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output


html_theme = "sphinx_rtd_theme"  # or "furo" or "alabaster" sphinx_rtd_theme sphinx_book_theme to install
html_static_path = ["_static"]
html_logo = None
html_css_files = ["custom.css"]
html_title=f"FrameIt {release} documentation"
