"""Create and describe shared state for the Streamlit dashboard.

DashboardContext contains configuration, the database connection and basic
date information shared between dashboard components. The context is created
once by the dashboard entry point and passed explicitly to tabs and sidebar
rendering functions.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, NoReturn

import streamlit as st
from loguru import logger

from stanwell.configuration import (
    load_config_and_open_database,
)


@dataclass(frozen=True)
class DashboardContext:
    """Shared application state used by dashboard components."""

    config: dict[str, Any]
    """Loaded application configuration."""

    connection: sqlite3.Connection
    """Open connection to the local application database."""

    workday_hours: float
    """ Configured number of hours in a standard working day."""

    today: date
    """Current local calendar date."""

    earliest_data: date | None
    """Earliest date represented by a stored time entry."""

    latest_data: date | None
    """Latest date represented by a stored time entry."""

    @property
    def has_synced_data(self) -> bool:
        """Return whether the database contains a usable date range.

        Returns
        -------
        bool
            ``True`` when both the earliest and latest stored dates are
            available.

        """
        has_data = self.earliest_data is not None and self.latest_data is not None

        return has_data


def _get_config_path(
    dashboard_arguments: argparse.Namespace,
) -> Path:
    """Determine which configuration file the dashboard should use.

    Parameters
    ----------
    dashboard_arguments : argparse.Namespace
        Parsed dashboard command-line arguments.

    Returns
    -------
    Path
        Absolute path to the supplied configuration file, or the default
        dashboard configuration path when none was supplied.

    """
    if dashboard_arguments.config is not None:
        config_path = dashboard_arguments.config.expanduser().resolve()
    else:
        config_path = Path(__file__).resolve().parent / "config.yml"

    return config_path


def _get_stored_date_range(
    connection: sqlite3.Connection,
) -> tuple[date | None, date | None]:
    """Return the earliest and latest locally stored entry dates.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    tuple[date or None, date or None]
        Earliest and latest stored dates. Both values are ``None`` when
        no time entries are stored.

    Raises
    ------
    sqlite3.Error
        If the database query cannot be completed.
    ValueError
        If a stored date is not in valid ISO format.

    """
    stored_date_range = connection.execute("""
        SELECT
            MIN(DATE(start_utc)) AS earliest_date,
            MAX(DATE(start_utc)) AS latest_date
        FROM time_entries
        """).fetchone()

    earliest_data: date | None = None
    latest_data: date | None = None

    if stored_date_range is not None:
        earliest_date_text = stored_date_range["earliest_date"]
        latest_date_text = stored_date_range["latest_date"]

        if earliest_date_text is not None:
            earliest_data = date.fromisoformat(earliest_date_text)

        if latest_date_text is not None:
            latest_data = date.fromisoformat(latest_date_text)

    stored_dates = (
        earliest_data,
        latest_data,
    )

    return stored_dates


def _stop_for_missing_config(
    config_path: Path,
) -> NoReturn:
    """Display a missing-configuration error and stop the dashboard.

    ``st.stop()`` interrupts execution of the current Streamlit script.
    Consequently, this function does not return to its caller.

    Parameters
    ----------
    config_path : Path
        Configuration path which could not be found.

    Raises
    ------
    streamlit.runtime.scriptrunner.StopException
        Raised internally by Streamlit to stop execution of the current
        dashboard run.

    """
    error_message = (
        "Configurationn file not found.\n\n"
        f"Expected: `{config_path}`\n\n"
        "Run `stanwell init` first."
    )

    st.error(error_message)
    logger.error(error_message)
    st.stop()


def create_dashboard_context(
    dashboard_arguments: argparse.Namespace,
) -> DashboardContext:
    """Create the shared dashboard application context.

    The configured database is opened and its available date range is
    determined. If the configuration file does not exist, an explanatory
    Streamlit error is displayed and execution of the current dashboard
    run is stopped.

    Parameters
    ----------
    dashboard_arguments : argparse.Namespace
        Parsed dashboard command-line arguments.

    Returns
    -------
    DashboardContext
        Shared dashboard configuration and database state.

    Raises
    ------
    streamlit.runtime.scriptrunner.StopException
        Raised internally by Streamlit when the configuration file does
        not exist, stopping execution of the current dashboard run.
    sqlite3.Error
        If the database cannot be opened or its stored date range cannot
        be queried.
    ValueError
        If a stored date or the configured ``workday_hours`` value cannot
        be converted to the required type.

    """
    config_path = _get_config_path(dashboard_arguments)

    try:
        config, connection = load_config_and_open_database(config_path)
    except FileNotFoundError:
        _stop_for_missing_config(config_path)

    earliest_data, latest_data = _get_stored_date_range(connection)

    dashboard_context = DashboardContext(
        config=config,
        connection=connection,
        workday_hours=float(config["workday_hours"]),
        today=date.today(),
        earliest_data=earliest_data,
        latest_data=latest_data,
    )

    return dashboard_context
