"""Provide connections and basic operations for the local database.

Database connections are configured to return rows by column name and to
enforce SQLite foreign-key constraints. Schema creation is provided by the
``database_schema`` module.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def connect_db(
    path: str | Path,
) -> sqlite3.Connection:
    """Open and configure an SQLite database connection.

    The connection uses ``sqlite3.Row`` so query results can be accessed by
    column name. SQLite foreign-key enforcement is enabled for the
    connection.

    Parameters
    ----------
    path : str or Path
        Path to the SQLite database. ``":memory:"`` may be used for an
        in-memory database.

    Returns
    -------
    sqlite3.Connection
        Configured SQLite database connection.

    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def sync_exceptions(
    connection: sqlite3.Connection,
    exceptions: Sequence[Mapping[str, Any]] | None,
) -> None:
    """Replace the stored day exceptions with configured exceptions.

    Existing day exceptions are removed before the supplied set is inserted.
    Passing ``None`` or an empty sequence therefore clears all stored day
    exceptions.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    exceptions : Sequence[Mapping[str, Any]] or None
        Day exceptions to store. Each exception must contain ``date`` and
        ``kind`` values and may optionally contain a ``note``.

    """
    exception_rows: list[tuple[str, Any, Any]] = []

    if exceptions is not None:
        exception_rows = [
            (
                str(exception["date"]),
                exception["kind"],
                exception.get("note"),
            )
            for exception in exceptions
        ]

    connection.execute("DELETE FROM day_exceptions")

    connection.executemany(
        """
        INSERT INTO day_exceptions (
            day,
            kind,
            note
        )
        VALUES (?, ?, ?)
        """,
        exception_rows,
    )

    connection.commit()
