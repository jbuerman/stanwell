"""Provide shared helpers for command-line interface commands."""

from __future__ import annotations

import sqlite3
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import typer

from stanwell.configuration import (
    load_config_and_open_database,
)


def get_dashboard_path() -> Path:
    """Return the installed dashboard module path.

    Returns
    -------
    Path
        Path to the Streamlit dashboard module.

    Raises
    ------
    RuntimeError
        If the dashboard module cannot be located.

    """
    module_spec = find_spec("stanwell.ui.dashboard.dashboard")

    if module_spec is None or module_spec.origin is None:
        raise RuntimeError("Could not locate the dashboard module.")

    dashboard_path = Path(module_spec.origin).resolve()

    return dashboard_path


def load_config_and_open_database_from_context(
    context: typer.Context,
) -> tuple[dict[str, Any], sqlite3.Connection]:
    """Load configuration and open the database for a CLI command.

    Parameters
    ----------
    context : typer.Context
        Typer command context containing the configuration path.

    Returns
    -------
    tuple[dict[str, Any], sqlite3.Connection]
        Loaded configuration and open database connection.

    """
    config_path = Path(context.obj["config_path"])

    config, connection = load_config_and_open_database(config_path)

    return config, connection
