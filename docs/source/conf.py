"""Sphinx configuration for the independent CLI."""

import importlib.metadata

project = "coderpad-cli"
author = "Adam Dangoor"
release = importlib.metadata.version("coderpad-cli")
extensions = ["sphinx_click.ext"]
html_theme = "furo"
nitpicky = True
html_theme_options = {
    "source_repository": "https://github.com/adamtheturtle/coderpad-cli/",
    "source_branch": "main",
    "source_directory": "docs/source/",
}
