"""Provide database operations and summaries for Toggl projects."""

from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd

PROJECT_COLUMNS = [
    "project",
    "hours",
    "percent",
    "days",
]


def load_project_names(
    connection: sqlite3.Connection,
) -> dict[int, str]:
    """Load the local project ID-to-name mapping.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    dict[int, str]
        Mapping from Toggl project IDs to project names.

    Raises
    ------
    sqlite3.Error
        If the project data cannot be read from the database.

    """
    rows = connection.execute("""
        SELECT id, name
        FROM projects
        """)

    project_names = {int(row["id"]): row["name"] for row in rows}

    return project_names


def get_projects(
    connection: sqlite3.Connection,
    start_day: date | str,
    end_day: date | str,
    workday_hours: float,
) -> pd.DataFrame:
    """Calculate project totals for a date range.

    Time entries are grouped by their stored project name. Entries without
    a project are grouped under ``No project``. The resulting hours are also
    expressed as a percentage of all recorded time and as equivalent
    configured working days.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    start_day : date or str
        First date to include.
    end_day : date or str
        Last date to include.
    workday_hours : float
        Number of hours in a standard working day.

    Returns
    -------
    pandas.DataFrame
        Project totals with ``project``, ``hours``, ``percent`` and
        ``days`` columns.

    Raises
    ------
    sqlite3.Error
        If project data cannot be read from the database.

    """
    projects = pd.read_sql_query(
        """
        SELECT
            COALESCE(
                project_name,
                'No project'
            ) AS project,
            SUM(duration_seconds) / 3600.0 AS hours
        FROM time_entries
        WHERE DATE(start_utc) BETWEEN ? AND ?
        GROUP BY COALESCE(
            project_name,
            'No project'
        )
        ORDER BY hours DESC
        """,
        connection,
        params=[
            str(start_day),
            str(end_day),
        ],
    )

    projects["hours"] = pd.to_numeric(
        projects["hours"],
        errors="coerce",
    ).fillna(0.0)

    total_hours = float(projects["hours"].sum())

    if total_hours > 0:
        projects["percent"] = projects["hours"] / total_hours * 100.0
    else:
        projects["percent"] = 0.0

    if workday_hours > 0:
        projects["days"] = projects["hours"] / workday_hours
    else:
        projects["days"] = 0.0

    projects = projects[PROJECT_COLUMNS]

    return projects
