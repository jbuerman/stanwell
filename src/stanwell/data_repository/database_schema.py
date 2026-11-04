"""Define and initialise the application's SQLite database schema.

The schema contains locally stored Toggl time entries and projects together
with synchronisation state, data coverage, tags and working-day exceptions.

Database initialisation is idempotent and may safely be performed whenever
the application opens an existing or newly created database.
"""

from __future__ import annotations

import sqlite3

DEFAULT_EXCEPTION_TYPES = [
    (
        "public_holiday",
        "Public holiday",
    ),
    (
        "annual_leave",
        "Annual leave",
    ),
    (
        "sick",
        "Sick leave",
    ),
    (
        "closure_day",
        "Organisation closure day",
    ),
    (
        "overtime_compensation",
        "Time off in lieu of overtime",
    ),
]


DATABASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS time_entries (
    id INTEGER PRIMARY KEY,
    workspace_id INTEGER,
    project_id INTEGER,
    project_name TEXT,
    task_id INTEGER,
    description TEXT,
    start_utc TEXT NOT NULL,
    stop_utc TEXT,
    duration_seconds INTEGER NOT NULL,
    tags_json TEXT,
    billable INTEGER,
    updated_at TEXT,
    raw_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_start
ON time_entries(start_utc);


CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    active INTEGER,
    updated_at TEXT,
    fetched_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_workspace
ON projects(workspace_id);


CREATE TABLE IF NOT EXISTS time_entry_tags (
    time_entry_id INTEGER NOT NULL,
    tag TEXT NOT NULL,

    PRIMARY KEY (
        time_entry_id,
        tag
    ),

    FOREIGN KEY (
        time_entry_id
    )
    REFERENCES time_entries (
        id
    )
    ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS data_coverage (
    day TEXT PRIMARY KEY,
    synced_at TEXT,
    refresh_pending INTEGER NOT NULL DEFAULT 0,
    refreshed_at TEXT
);


CREATE TABLE IF NOT EXISTS covered_days (
    day TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    fetch_mode TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS exception_types (
    kind TEXT PRIMARY KEY,
    description TEXT
);


CREATE TABLE IF NOT EXISTS day_exceptions (
    day TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    note TEXT,

    FOREIGN KEY (
        kind
    )
    REFERENCES exception_types (
        kind
    )
);


CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    start_day TEXT NOT NULL,
    end_day TEXT NOT NULL,
    mode TEXT NOT NULL,
    requests INTEGER DEFAULT 0,
    entries INTEGER DEFAULT 0,
    status TEXT,
    message TEXT
);
"""


def initialise_database(
    connection: sqlite3.Connection,
) -> None:
    """Initialise the application database schema.

    All application tables and indexes are created if they do not already
    exist. The standard working-day exception types are also inserted if
    missing.

    The operation is idempotent and does not replace existing data.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    """
    connection.executescript(DATABASE_SCHEMA)

    connection.executemany(
        """
        INSERT OR IGNORE INTO exception_types (
            kind,
            description
        )
        VALUES (?, ?)
        """,
        DEFAULT_EXCEPTION_TYPES,
    )

    connection.commit()
