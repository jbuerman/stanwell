"""Store normalised time entries and their tag relationships.

Time entries are stored in ``time_entries`` while their tags are also
maintained in ``time_entry_tags`` to support tag-based queries.

Normalised entries are currently represented as tuples whose field order
matches the ``time_entries`` database insert. The tuple layout is shared
with the Toggl normalisation code.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from stanwell.toggl.normalisation import (
    NormalisedTimeEntry,
)


def backfill_tags(
    connection: sqlite3.Connection,
) -> dict[str, int]:
    """Rebuild tag relationships from stored time entries.

    Existing tag relationships are replaced using the tags stored in
    each entry's ``tags_json`` field. Duplicate tags within an entry
    are removed.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    dict[str, int]
        Counts of entries updated and unique tags added.

    """
    entries = connection.execute("""
        SELECT
            id,
            tags_json
        FROM time_entries
        """).fetchall()

    entries_updated = 0
    tags_added = 0

    for entry in entries:
        tags = json.loads(entry["tags_json"] or "[]")

        if not tags:
            continue

        unique_tags = sorted(set(tags))

        _replace_entry_tags(
            connection=connection,
            entry_id=entry["id"],
            tags=unique_tags,
        )

        entries_updated += 1
        tags_added += len(unique_tags)

    connection.commit()

    return {
        "entries_updated": entries_updated,
        "tags_added": tags_added,
    }


def _replace_entry_tags(
    connection: sqlite3.Connection,
    entry_id: int,
    tags: Sequence[str],
) -> None:
    """Replace the tag relationships for a time entry.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    entry_id : int
        ID of the time entry whose tags should be replaced.
    tags : Sequence[str]
        Tags associated with the time entry.

    """
    connection.execute(
        """
        DELETE FROM time_entry_tags
        WHERE time_entry_id = ?
        """,
        (entry_id,),
    )

    connection.executemany(
        """
        INSERT OR IGNORE INTO time_entry_tags (
            time_entry_id,
            tag
        )
        VALUES (?, ?)
        """,
        [(entry_id, tag) for tag in tags],
    )


def upsert_normalised_rows(
    connection: sqlite3.Connection,
    normalised_entries: Sequence[NormalisedTimeEntry],
) -> None:
    """Insert or update normalised Toggl time entries.

    Existing entries with matching IDs are updated. Tag relationships
    are replaced to match the tags contained in each normalised entry.

    The transaction is not committed by this function, allowing the
    caller to include the operation within a larger synchronisation
    transaction.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    normalised_entries : Sequence[NormalisedTimeEntry]
        Normalised time entries ready for database storage.

    """
    if len(normalised_entries) > 0:
        connection.executemany(
            """
            INSERT INTO time_entries (
                id,
                workspace_id,
                project_id,
                project_name,
                task_id,
                description,
                start_utc,
                stop_utc,
                duration_seconds,
                tags_json,
                billable,
                updated_at,
                raw_json,
                fetched_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                workspace_id = excluded.workspace_id,
                project_id = excluded.project_id,
                project_name = excluded.project_name,
                task_id = excluded.task_id,
                description = excluded.description,
                start_utc = excluded.start_utc,
                stop_utc = excluded.stop_utc,
                duration_seconds = excluded.duration_seconds,
                tags_json = excluded.tags_json,
                billable = excluded.billable,
                updated_at = excluded.updated_at,
                raw_json = excluded.raw_json,
                fetched_at = excluded.fetched_at
            """,
            normalised_entries,
        )

        for normalised_entry in normalised_entries:
            tags = json.loads(normalised_entry.tags_json or "[]")

            _replace_entry_tags(
                connection=connection,
                entry_id=normalised_entry.id,
                tags=tags,
            )
