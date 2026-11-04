import json

from stanwell.data_repository.time_entries import (
    backfill_tags,
    upsert_normalised_rows,
)
from stanwell.toggl.normalisation import (
    NormalisedTimeEntry,
)


def make_normalised_entry(
    *,
    entry_id: int = 123,
    description: str = "Test entry",
    tags: list[str] | None = None,
    duration_seconds: int = 3600,
) -> NormalisedTimeEntry:
    if tags is None:
        tags = []

    return NormalisedTimeEntry(
        id=entry_id,
        workspace_id=1,
        project_id=10,
        project_name="Test project",
        task_id=None,
        description=description,
        start_utc="2026-10-24T09:00:00+00:00",
        stop_utc="2026-10-24T10:00:00+00:00",
        duration_seconds=duration_seconds,
        tags_json=json.dumps(tags),
        billable=0,
        updated_at="2026-10-24T10:00:00+00:00",
        raw_json="{}",
        fetched_at="2026-10-24T11:00:00+00:00",
    )


def test_upsert_normalised_rows_inserts_entry(conn):
    entry = make_normalised_entry()

    upsert_normalised_rows(
        conn,
        [entry],
    )

    row = conn.execute(
        """
        SELECT *
        FROM time_entries
        WHERE id = ?
        """,
        (123,),
    ).fetchone()

    assert row is not None
    assert row["id"] == 123
    assert row["project_name"] == "Test project"
    assert row["description"] == "Test entry"
    assert row["duration_seconds"] == 3600


def test_upsert_normalised_rows_updates_existing_entry(conn):
    upsert_normalised_rows(
        conn,
        [
            make_normalised_entry(
                description="Original",
            )
        ],
    )

    upsert_normalised_rows(
        conn,
        [
            make_normalised_entry(
                description="Updated",
                duration_seconds=7200,
            )
        ],
    )

    row = conn.execute(
        """
        SELECT description, duration_seconds
        FROM time_entries
        WHERE id = ?
        """,
        (123,),
    ).fetchone()

    assert row["description"] == "Updated"
    assert row["duration_seconds"] == 7200


def test_upsert_normalised_rows_inserts_tags(conn):
    entry = make_normalised_entry(
        tags=[
            "research",
            "development",
        ],
    )

    upsert_normalised_rows(
        conn,
        [entry],
    )

    rows = conn.execute(
        """
        SELECT tag
        FROM time_entry_tags
        WHERE time_entry_id = ?
        ORDER BY tag
        """,
        (123,),
    ).fetchall()

    assert [row["tag"] for row in rows] == [
        "development",
        "research",
    ]


def test_upsert_normalised_rows_replaces_existing_tags(conn):
    upsert_normalised_rows(
        conn,
        [
            make_normalised_entry(
                tags=[
                    "old",
                    "keep",
                ],
            )
        ],
    )

    upsert_normalised_rows(
        conn,
        [
            make_normalised_entry(
                tags=[
                    "keep",
                    "new",
                ],
            )
        ],
    )

    rows = conn.execute(
        """
        SELECT tag
        FROM time_entry_tags
        WHERE time_entry_id = ?
        ORDER BY tag
        """,
        (123,),
    ).fetchall()

    assert [row["tag"] for row in rows] == [
        "keep",
        "new",
    ]


def test_upsert_normalised_rows_removes_tags_when_entry_has_none(conn):
    upsert_normalised_rows(
        conn,
        [
            make_normalised_entry(
                tags=["existing"],
            )
        ],
    )

    upsert_normalised_rows(
        conn,
        [
            make_normalised_entry(
                tags=[],
            )
        ],
    )

    rows = conn.execute(
        """
        SELECT tag
        FROM time_entry_tags
        WHERE time_entry_id = ?
        """,
        (123,),
    ).fetchall()

    assert rows == []


def test_upsert_normalised_rows_does_nothing_when_empty(conn):
    upsert_normalised_rows(
        conn,
        [],
    )

    count = conn.execute("""
        SELECT COUNT(*)
        FROM time_entries
        """).fetchone()[0]

    assert count == 0


def test_backfill_tags_creates_tag_relationships(conn):
    entry = make_normalised_entry(
        tags=[
            "research",
            "development",
        ],
    )

    upsert_normalised_rows(
        conn,
        [entry],
    )

    conn.execute("""
        DELETE FROM time_entry_tags
        """)
    conn.commit()

    result = backfill_tags(conn)

    rows = conn.execute(
        """
        SELECT tag
        FROM time_entry_tags
        WHERE time_entry_id = ?
        ORDER BY tag
        """,
        (123,),
    ).fetchall()

    assert [row["tag"] for row in rows] == [
        "development",
        "research",
    ]

    assert result == {
        "entries_updated": 1,
        "tags_added": 2,
    }


def test_backfill_tags_removes_duplicate_tags(conn):
    entry = make_normalised_entry(
        tags=[
            "research",
            "research",
            "development",
        ],
    )

    upsert_normalised_rows(
        conn,
        [entry],
    )

    conn.execute("""
        DELETE FROM time_entry_tags
        """)
    conn.commit()

    result = backfill_tags(conn)

    rows = conn.execute(
        """
        SELECT tag
        FROM time_entry_tags
        WHERE time_entry_id = ?
        ORDER BY tag
        """,
        (123,),
    ).fetchall()

    assert [row["tag"] for row in rows] == [
        "development",
        "research",
    ]

    assert result == {
        "entries_updated": 1,
        "tags_added": 2,
    }


def test_backfill_tags_ignores_entries_without_tags(conn):
    entry = make_normalised_entry(
        tags=[],
    )

    upsert_normalised_rows(
        conn,
        [entry],
    )

    result = backfill_tags(conn)

    assert result == {
        "entries_updated": 0,
        "tags_added": 0,
    }
