import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "Arbitrum Python SDK"
copyright = "2025, Mert Köklü"
author = "Mert Köklü"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# HTML theme settings
html_theme = "furo"
html_static_path = ["_static"]

# Theme customization
html_theme_options = {
    "light_css_variables": {
        # Modern system font stack
        "font-stack": "'SF Pro Display', 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        "font-stack--monospace": "'SF Mono', 'Fira Code', 'JetBrains Mono', ui-monospace, monospace",
        "font-stack--headings": "'SF Pro Display', 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        # Remove link underlines
        "content-link-text-decoration": "none",
        "content-link-hover-text-decoration": "none",
        # Font sizes
        "font-size--normal": "0.950rem",
        "font-size--small": "0.875rem",
        "code-font-size": "0.875em",
        "code-border-radius": "10px",
    },
    "dark_css_variables": {
        "code-border-radius": "10px",
    },
    # Sidebar behavior
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "announcement": None,
}

# GitHub-style syntax highlighting
pygments_style = "xcode"
pygments_dark_style = "github-dark"

# Make introduction.rst the landing page
# master_doc = 'introduction.rst'
# html_additional_pages = {}

# Add custom CSS
html_css_files = ['custom.css']

# AutoDoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = True
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_ivar = True
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_type_aliases = None
