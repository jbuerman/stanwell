
import os
import sys
import tomllib
from datetime import date
from pathlib import Path

DOCS_DIR = Path(__file__).parent
sys.path.insert(
    0,
    str(DOCS_DIR / "_ext"),
)

PROJECT_ROOT = os.path.abspath(os.path.join(__file__, "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

def authors_to_comma_list(pyproject_data, include_emails=False):
    """Convert PEP 621 authors into a comma-separated string."""
    authors = pyproject_data.get("project", {}).get("authors", []) or []
    parts = []

    for a in authors:
        if isinstance(a, dict):
            name = (a.get("name") or "").strip()
            email = (a.get("email") or "").strip()
            if name or email:
                if include_emails and name and email:
                    parts.append(f"{name} <{email}>")
                elif name:
                    parts.append(name)
                elif email:
                    parts.append(f"<{email}>")
        elif isinstance(a, str):
            s = a.strip()
            if s:
                parts.append(s)
    return ", ".join(parts)

with open(os.path.join(PROJECT_ROOT, "pyproject.toml"), "rb") as f:
    pyproject_data = tomllib.load(f)
project_version = pyproject_data.get("project", {}).get("version", "-")
project_name = pyproject_data.get("project", {}).get("name", "-")

project = project_name
author = authors_to_comma_list(pyproject_data, include_emails=False)
copyright = f"{date.today().year}, {author}"
release = project_version
version = project_version

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_paramlinks",
    "myst_parser",
    "cli_commands",
]

autosummary_generate = True

autodoc_typehints = "signature"

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}
templates_path = ["_templates"]
exclude_patterns = []
html_static_path = ["_static"]

html_theme = 'sphinx_rtd_theme'

html_logo = "_static/stanwell_logo.png"
html_favicon = "_static/stanwell_favicon.png"
