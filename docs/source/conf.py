"""
Sphinx configuration for pabo's documentation.
"""

from datetime import date

project = "pabo"
author = "Ujjwal Panda"
copyright = f"2022-{date.today().year}, Ujjwal Panda"
html_theme = "furo"
html_title = "pabo"
html_baseurl = "https://astrogewgaw.github.io/pabo/"

extensions = [
    "myst_parser",
    "sphinx_sitemap",
    "sphinx_copybutton",
    "sphinx.ext.autodoc",
    "sphinx.ext.githubpages",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
    "sphinx.ext.autosectionlabel",
]

myst_enable_extensions = ["colon_fence", "deflist"]
autosectionlabel_prefix_document = True
autodoc_member_order = "bysource"
autodoc_default_options = {"members": True, "show-inheritance": True}
sitemap_url_scheme = "{link}"
exclude_patterns = ["build"]
