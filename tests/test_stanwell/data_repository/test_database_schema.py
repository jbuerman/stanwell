from stanwell.data_repository.database_schema import (
    DEFAULT_EXCEPTION_TYPES,
    initialise_database,
)
from stanwell.data_repository.db import connect_db

EXPECTED_TABLES = {
    "time_entries",
    "projects",
    "time_entry_tags",
    "data_coverage",
    "covered_days",
    "exception_types",
    "day_exceptions",
    "sync_log",
}


def test_initialise_database_creates_expected_tables():
    connection = connect_db(":memory:")

    initialise_database(connection)

    rows = connection.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """).fetchall()

    table_names = {row["name"] for row in rows}

    assert EXPECTED_TABLES.issubset(table_names)

    connection.close()


def test_initialise_database_is_idempotent():
    connection = connect_db(":memory:")

    initialise_database(connection)
    initialise_database(connection)

    rows = connection.execute("""
        SELECT kind
        FROM exception_types
        """).fetchall()

    assert len(rows) == len(DEFAULT_EXCEPTION_TYPES)

    connection.close()


def test_initialise_database_creates_expected_exception_types():
    connection = connect_db(":memory:")

    initialise_database(connection)

    rows = connection.execute("""
        SELECT kind, description
        FROM exception_types
        ORDER BY kind
        """).fetchall()

    exception_types = {row["kind"]: row["description"] for row in rows}

    assert exception_types == {
        "annual_leave": "Annual leave",
        "closure_day": "Organisation closure day",
        "overtime_compensation": ("Time off in lieu of overtime"),
        "public_holiday": "Public holiday",
        "sick": "Sick leave",
    }

    connection.close()


def test_deleting_time_entry_deletes_its_tags():
    connection = connect_db(":memory:")
    initialise_database(connection)

    connection.execute(
        """
        INSERT INTO time_entries (
            id,
            start_utc,
            duration_seconds,
            raw_json,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            123,
            "2026-10-23T10:00:00Z",
            3600,
            "{}",
            "2026-10-23T11:00:00Z",
        ),
    )

    connection.execute(
        """
        INSERT INTO time_entry_tags (
            time_entry_id,
            tag
        )
        VALUES (?, ?)
        """,
        (
            123,
            "development",
        ),
    )

    connection.commit()

    connection.execute(
        """
        DELETE FROM time_entries
        WHERE id = ?
        """,
        (123,),
    )

    connection.commit()

    tags = connection.execute(
        """
        SELECT *
        FROM time_entry_tags
        WHERE time_entry_id = ?
        """,
        (123,),
    ).fetchall()

    assert tags == []

    connection.close()
