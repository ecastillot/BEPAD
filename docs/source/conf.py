import os
import sys

conf_dir = os.path.dirname(os.path.abspath(__file__))  # docs/source
project_root = os.path.abspath(os.path.join(conf_dir, "..", ".."))
sys.path.insert(0, project_root)

# Heavy/optional dependencies are mocked so Read the Docs only needs Sphinx.
autodoc_mock_imports = [
    "numpy", "pandas", "scipy", "pyarrow", "matplotlib", "yaml", "torch",
    "utdquake", "pyocto", "huggingface_hub",
]

project = "BEPAD"
copyright = "2026, Emmanuel Castillo"
author = "Emmanuel Castillo"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.autosummary",
    "myst_parser",
    "sphinx_copybutton",
]
autodoc_member_order = "bysource"
autodoc_typehints = "description"
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["css/custom.css"]
html_theme_options = {"collapse_navigation": False, "navigation_depth": 3}
html_title = "BEPAD"
