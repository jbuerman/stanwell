import sqlite3

import pytest

from stanwell.data_repository.database_schema import (
    initialise_database,
)
from stanwell.data_repository.db import (
    connect_db,
    sync_exceptions,
)


@pytest.fixture
def db():
    connection = connect_db(":memory:")
    initialise_database(connection)

    yield connection

    connection.close()


def test_connect_db_sets_row_factory():
    connection = connect_db(":memory:")

    assert connection.row_factory is sqlite3.Row

    connection.close()


def test_connect_db_enables_foreign_keys():
    connection = connect_db(":memory:")

    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert foreign_keys == 1

    connection.close()


def test_sync_exceptions_inserts_exceptions(db):
    exceptions = [
        {
            "date": "2026-10-20",
            "kind": "annual_leave",
            "note": "Holiday",
        },
        {
            "date": "2026-10-21",
            "kind": "sick",
        },
    ]

    sync_exceptions(
        db,
        exceptions,
    )

    rows = db.execute("""
        SELECT day, kind, note
        FROM day_exceptions
        ORDER BY day
        """).fetchall()

    assert [dict(row) for row in rows] == [
        {
            "day": "2026-10-20",
            "kind": "annual_leave",
            "note": "Holiday",
        },
        {
            "day": "2026-10-21",
            "kind": "sick",
            "note": None,
        },
    ]


def test_sync_exceptions_replaces_existing_exceptions(db):
    sync_exceptions(
        db,
        [
            {
                "date": "2026-10-20",
                "kind": "annual_leave",
            }
        ],
    )

    sync_exceptions(
        db,
        [
            {
                "date": "2026-10-21",
                "kind": "sick",
            }
        ],
    )

    rows = db.execute("""
        SELECT day, kind
        FROM day_exceptions
        """).fetchall()

    assert [dict(row) for row in rows] == [
        {
            "day": "2026-10-21",
            "kind": "sick",
        }
    ]


@pytest.mark.parametrize(
    "exceptions",
    [
        None,
        [],
    ],
)
def test_sync_exceptions_with_no_exceptions_clears_existing_exceptions(
    db,
    exceptions,
):
    sync_exceptions(
        db,
        [
            {
                "date": "2026-10-20",
                "kind": "annual_leave",
            }
        ],
    )

    sync_exceptions(
        db,
        exceptions,
    )

    count = db.execute("""
        SELECT COUNT(*)
        FROM day_exceptions
        """).fetchone()[0]

    assert count == 0
