project = "pabo"
html_theme = "furo"
author = "Ujjwal Panda"
exclude_patterns = [""]
html_static_path = ["static"]
templates_path = ["templates"]
copyright = "2022, Ujjwal Panda"
html_baseurl = "https://pabo.readthedocs.io"


extensions = [
    "myst_parser",
    "sphinx_sitemap",
    "sphinx_copybutton",
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
    "sphinx.ext.autosectionlabel",
]
