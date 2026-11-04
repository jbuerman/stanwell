"""Normalise Toggl API data for local database storage.

The Toggl recent-entries and Reports APIs use different field names.
This module converts data from either source into a consistent
``NormalisedTimeEntry`` whose field order matches the ``time_entries``
database table.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, NamedTuple

from dateutil.parser import isoparse


class NormalisedTimeEntry(NamedTuple):
    """Time entry prepared for storage in the local database."""

    id: int
    workspace_id: int | None
    project_id: int | None
    project_name: str | None
    task_id: int | None
    description: str | None
    start_utc: str
    stop_utc: str | None
    duration_seconds: int
    tags_json: str
    billable: int
    updated_at: str | None
    raw_json: str
    fetched_at: str


def _first_present(
    entry: Mapping[str, Any],
    *field_names: str,
) -> Any:
    """Return the first present, non-None field value.

    Unlike chained ``or`` expressions, this preserves valid falsey
    values such as integer zero.

    Parameters
    ----------
    entry : collections.abc.Mapping
        Toggl entry containing fields from either API.
    *field_names : str
        Field names in order of preference.

    Returns
    -------
    Any
        First non-None value, or ``None`` if none is available.

    """
    for field_name in field_names:
        value = entry.get(field_name)

        if value is not None:
            return value

    return None


def _calculate_duration_seconds(
    entry: Mapping[str, Any],
    start_utc: str,
    stop_utc: str | None,
) -> int:
    """Determine the duration of a Toggl entry.

    The explicit ``seconds`` or ``duration`` value is preferred. If
    neither is available for a completed entry, the duration is
    calculated from its start and stop times.

    Parameters
    ----------
    entry : collections.abc.Mapping
        Raw Toggl entry.
    start_utc : str
        Entry start timestamp.
    stop_utc : str or None
        Entry stop timestamp.

    Returns
    -------
    int
        Entry duration in seconds.

    """
    duration = _first_present(
        entry,
        "seconds",
        "duration",
    )

    if duration is not None:
        return int(duration)

    if stop_utc is not None:
        return int((isoparse(stop_utc) - isoparse(start_utc)).total_seconds())

    return 0


def normalise(
    entry: Mapping[str, Any],
    project_names: Mapping[int, str] | None = None,
) -> NormalisedTimeEntry:
    """Normalise a Toggl API entry for database storage.

    Entries from either the recent-entries API or the Reports API are
    accepted. Alternative field names used by those APIs are mapped to
    the common local representation.

    Parameters
    ----------
    entry : collections.abc.Mapping
        Raw or flattened Toggl API entry.
    project_names : collections.abc.Mapping, optional
        Mapping from project IDs to locally stored project names.

    Returns
    -------
    NormalisedTimeEntry
        Entry whose fields and field order match the ``time_entries``
        database table.

    Raises
    ------
    ValueError
        If the entry has no ID or start timestamp.

    """
    entry_id = entry.get("id")

    if entry_id is None:
        raise ValueError(
            "Toggl entry has no ID. " f"Available fields: {sorted(entry.keys())}"
        )

    start_utc = entry.get("start")

    if start_utc is None:
        raise ValueError(
            "Toggl entry has no start time. "
            f"Entry ID: {entry_id}; "
            f"available fields: {sorted(entry.keys())}"
        )

    stop_utc = entry.get("stop")

    duration_seconds = _calculate_duration_seconds(
        entry=entry,
        start_utc=start_utc,
        stop_utc=stop_utc,
    )

    tags = (
        _first_present(
            entry,
            "tags",
            "tag_names",
        )
        or []
    )

    workspace_id = _first_present(
        entry,
        "workspace_id",
        "wid",
    )
    project_id = _first_present(
        entry,
        "project_id",
        "pid",
    )
    task_id = _first_present(
        entry,
        "task_id",
        "tid",
    )
    updated_at = _first_present(
        entry,
        "at",
        "updated_at",
        "at_tz",
    )

    project_name = entry.get("project_name")

    if project_name is None and project_id is not None:
        project_name = (project_names or {}).get(int(project_id))

    fetched_at = datetime.now().astimezone().isoformat()

    return NormalisedTimeEntry(
        id=int(entry_id),
        workspace_id=(int(workspace_id) if workspace_id is not None else None),
        project_id=(int(project_id) if project_id is not None else None),
        project_name=project_name,
        task_id=(int(task_id) if task_id is not None else None),
        description=entry.get("description"),
        start_utc=start_utc,
        stop_utc=stop_utc,
        duration_seconds=duration_seconds,
        tags_json=json.dumps(tags),
        billable=int(bool(entry.get("billable", False))),
        updated_at=updated_at,
        raw_json=json.dumps(
            entry,
            sort_keys=True,
        ),
        fetched_at=fetched_at,
    )
