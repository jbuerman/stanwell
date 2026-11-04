"""Coordinate synchronisation between Toggl and the local database.

This module orchestrates project and time-entry synchronisation. Requested
periods are split into API-sized chunks, downloaded, normalised and stored
locally. Complete periods are recorded as covered, while incomplete periods
remain pending so they can be retried after an API quota reset.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.parser import isoparse

from stanwell.data_repository.data_coverage import (
    find_missing_ranges,
    get_pending_refresh_days,
    pending_refresh_ranges,
)
from stanwell.data_repository.data_util import date_ranges
from stanwell.data_repository.projects import load_project_names
from stanwell.data_repository.time_entries import (
    upsert_normalised_rows,
)
from stanwell.toggl.client import (
    fetch_range,
    fetch_workspace_projects,
)
from stanwell.toggl.exceptions import TogglQuotaExhaustedError
from stanwell.toggl.normalisation import (
    NormalisedTimeEntry,
    normalise,
)

DateInput = date | str
SyncResult = dict[str, Any]


@dataclass(frozen=True)
class ChunkRefreshResult:
    """Describe the result of refreshing one API chunk."""

    entry_count: int
    is_complete: bool
    quota_error: TogglQuotaExhaustedError | None


def _current_timestamp() -> str:
    """Return the current local timestamp in ISO format."""
    timestamp = datetime.now().astimezone().isoformat()
    return timestamp


def _parse_date(value: DateInput, parameter_name: str) -> date:
    """Convert an ISO date string or date object to a date.

    Parameters
    ----------
    value : date or str
        Date to parse.
    parameter_name : str
        Parameter name used in validation messages.

    Returns
    -------
    date
        Parsed date.

    """
    if isinstance(value, str):
        parsed_date = date.fromisoformat(value)
    elif isinstance(value, date):
        parsed_date = value
    else:
        raise TypeError(f"{parameter_name} must be an ISO date string or datetime.date")

    return parsed_date


def _dates_in_period(period_start: date, period_end: date) -> list[date]:
    """Return every date in an inclusive period."""
    period_dates = [
        period_start + timedelta(days=offset)
        for offset in range((period_end - period_start).days + 1)
    ]
    return period_dates


def _start_sync_log(
    connection: sqlite3.Connection,
    period_start: date,
    period_end: date,
    mode: str,
) -> int:
    """Create a running synchronisation log record."""
    cursor = connection.execute(
        """
        INSERT INTO sync_log (
            started_at,
            start_day,
            end_day,
            mode,
            status
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            _current_timestamp(),
            period_start.isoformat(),
            period_end.isoformat(),
            mode,
            "running",
        ),
    )
    connection.commit()

    if cursor.lastrowid is None:
        raise RuntimeError("The synchronisation log record has no ID.")

    log_id = int(cursor.lastrowid)
    return log_id


def _finish_sync_log(
    connection: sqlite3.Connection,
    log_id: int,
    request_count: int,
    entry_count: int,
    status: str,
    message: str | None,
) -> None:
    """Update a synchronisation log record with its final state."""
    connection.execute(
        """
        UPDATE sync_log
        SET finished_at = ?,
            requests = ?,
            entries = ?,
            status = ?,
            message = ?
        WHERE id = ?
        """,
        (
            _current_timestamp(),
            request_count,
            entry_count,
            status,
            message,
            log_id,
        ),
    )
    connection.commit()


def _mark_period_pending(
    connection: sqlite3.Connection,
    period_start: date,
    period_end: date,
) -> None:
    """Mark every date in a period as awaiting refresh."""
    pending_rows = [
        (pending_date.isoformat(),)
        for pending_date in _dates_in_period(period_start, period_end)
    ]

    connection.executemany(
        """
        INSERT INTO data_coverage (
            day,
            refresh_pending
        )
        VALUES (?, 1)
        ON CONFLICT(day) DO UPDATE SET
            refresh_pending = 1
        """,
        pending_rows,
    )
    connection.commit()


def _mark_chunk_complete(
    connection: sqlite3.Connection,
    chunk_start: date,
    chunk_end: date,
    mode: str,
) -> None:
    """Record a completely downloaded chunk as covered and refreshed."""
    fetched_at = _current_timestamp()
    chunk_dates = _dates_in_period(chunk_start, chunk_end)

    covered_rows = [
        (chunk_date.isoformat(), fetched_at, mode) for chunk_date in chunk_dates
    ]
    connection.executemany(
        """
        INSERT INTO covered_days (
            day,
            fetched_at,
            fetch_mode
        )
        VALUES (?, ?, ?)
        ON CONFLICT(day) DO UPDATE SET
            fetched_at = excluded.fetched_at,
            fetch_mode = excluded.fetch_mode
        """,
        covered_rows,
    )

    refreshed_rows = [
        (chunk_date.isoformat(), fetched_at, fetched_at) for chunk_date in chunk_dates
    ]
    connection.executemany(
        """
        INSERT INTO data_coverage (
            day,
            synced_at,
            refresh_pending,
            refreshed_at
        )
        VALUES (?, ?, 0, ?)
        ON CONFLICT(day) DO UPDATE SET
            refresh_pending = 0,
            refreshed_at = excluded.refreshed_at
        """,
        refreshed_rows,
    )


def _normalise_entries(
    raw_entries: list[Any],
    project_names: Mapping[int, str],
    chunk_start: date,
    chunk_end: date,
) -> list[NormalisedTimeEntry]:
    """Normalise entries returned for one API chunk."""
    normalised_entries: list[NormalisedTimeEntry] = []

    for position, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            raise TypeError(
                "Toggl returned an entry that is not an "
                f"object at position {position} for "
                f"{chunk_start} to {chunk_end}: "
                f"{type(raw_entry).__name__}"
            )

        try:
            normalised_entry = normalise(
                raw_entry,
                project_names=project_names,
            )
        except Exception as error:
            raise ValueError(
                "Could not normalise a Toggl entry for "
                f"{chunk_start} to {chunk_end}.\n"
                f"Entry position: {position}\n"
                f"Available fields: {sorted(raw_entry.keys())}\n"
                f"Original error: {error}"
            ) from error

        normalised_entries.append(normalised_entry)

    return normalised_entries


def _find_local_entry_ids(
    connection: sqlite3.Connection,
    timezone: ZoneInfo,
    chunk_start: date,
    chunk_end: date,
) -> set[int]:
    """Find locally stored entries whose local start date is in a chunk."""
    local_entries = connection.execute("""
        SELECT id, start_utc
        FROM time_entries
        WHERE start_utc IS NOT NULL
        """).fetchall()

    local_entry_ids: set[int] = set()

    for local_entry in local_entries:
        local_entry_start = isoparse(local_entry["start_utc"]).astimezone(timezone)
        local_entry_date = local_entry_start.date()

        if chunk_start <= local_entry_date <= chunk_end:
            local_entry_ids.add(int(local_entry["id"]))

    return local_entry_ids


def _delete_stale_entries(
    connection: sqlite3.Connection,
    normalised_entries: list[NormalisedTimeEntry],
    timezone: ZoneInfo,
    chunk_start: date,
    chunk_end: date,
) -> None:
    """Delete local entries absent from a complete remote chunk."""
    remote_entry_ids = {normalised_entry.id for normalised_entry in normalised_entries}
    local_entry_ids = _find_local_entry_ids(
        connection,
        timezone,
        chunk_start,
        chunk_end,
    )
    stale_entry_ids = local_entry_ids - remote_entry_ids

    if len(stale_entry_ids) > 0:
        connection.executemany(
            """
            DELETE FROM time_entries
            WHERE id = ?
            """,
            [(entry_id,) for entry_id in stale_entry_ids],
        )


def refresh_recent(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
    end_day: str | None = None,
) -> SyncResult:
    """Refresh the configured number of recent days.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Application configuration.
    end_day : str, optional
        Last date to refresh. Defaults to today.

    Returns
    -------
    dict[str, Any]
        Result returned by :func:`refresh_period`.

    """
    if end_day is None:
        period_end = date.today()
    else:
        period_end = date.fromisoformat(end_day)

    period_start = period_end - timedelta(days=int(config["recent_refresh_days"]) - 1)
    result = refresh_period(
        connection,
        config,
        period_start,
        period_end,
        "recent",
    )
    return result


def refresh_pending(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
) -> SyncResult:
    """Retry all dates currently marked as pending.

    Consecutive pending dates are grouped into ranges and processed in
    chronological order. Processing stops when the Toggl quota is exhausted.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Application configuration.

    Returns
    -------
    dict[str, Any]
        Aggregate refresh result.

    """
    refresh_ranges = pending_refresh_ranges(connection)
    ranges_attempted = 0
    request_count = 0
    entry_count = 0
    quota_result: SyncResult | None = None

    for range_start, range_end in refresh_ranges:
        if quota_result is None:
            ranges_attempted += 1
            range_result = refresh_period(
                connection,
                config,
                range_start,
                range_end,
                mode="pending",
            )
            request_count += int(range_result.get("requests", 0))
            entry_count += int(range_result.get("entries_saved", 0))

            if range_result["status"] == "quota_exhausted":
                quota_result = range_result

    remaining_pending_days = get_pending_refresh_days(connection)

    if quota_result is None:
        if len(refresh_ranges) == 0:
            message = "There are no pending refreshes."
        else:
            message = "Pending refresh completed."

        result: SyncResult = {
            "status": "ok",
            "ranges_attempted": ranges_attempted,
            "requests": request_count,
            "entries_saved": entry_count,
            "pending_count": len(remaining_pending_days),
            "message": message,
        }
    else:
        if len(remaining_pending_days) > 0:
            first_pending = remaining_pending_days[0].isoformat()
            last_pending = remaining_pending_days[-1].isoformat()
        else:
            first_pending = None
            last_pending = None

        result = {
            "status": "quota_exhausted",
            "ranges_attempted": ranges_attempted,
            "requests": request_count,
            "entries_saved": entry_count,
            "pending_count": len(remaining_pending_days),
            "first_pending": first_pending,
            "last_pending": last_pending,
            "quota_remaining": quota_result.get("quota_remaining"),
            "quota_resets_in_seconds": quota_result.get("quota_resets_in_seconds"),
            "message": quota_result.get("message"),
        }

    return result


def _prepare_project_names(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
) -> tuple[Mapping[int, str], int]:
    """Synchronise projects and return the available project names.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Application configuration.

    Returns
    -------
    tuple[collections.abc.Mapping[int, str], int]
        Available project names and the number of API requests made.

    Raises
    ------
    RuntimeError
        If the Toggl quota is exhausted and no local project catalogue exists.
    """
    request_count = 0

    try:
        request_count = synchronise_projects(
            connection,
            config,
        )
    except TogglQuotaExhaustedError as error:
        project_names = load_project_names(connection)

        if len(project_names) == 0:
            raise RuntimeError(
                "The Toggl project catalogue could not be downloaded "
                "because the API quota was exhausted, and no local "
                "project catalogue is available."
            ) from error
    else:
        project_names = load_project_names(connection)

    return project_names, request_count


def _refresh_chunk(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
    project_names: Mapping[int, str],
    timezone: ZoneInfo,
    chunk_start: date,
    chunk_end: date,
    mode: str,
) -> ChunkRefreshResult:
    """Download, normalise and store one API chunk.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Application configuration.
    project_names : collections.abc.Mapping
        Mapping from project IDs to project names.
    timezone : zoneinfo.ZoneInfo
        Local timezone used to identify existing entries.
    chunk_start : date
        First date in the chunk.
    chunk_end : date
        Last date in the chunk.
    mode : str
        Synchronisation mode recorded in coverage data.

    Returns
    -------
    ChunkRefreshResult
        Outcome of refreshing the chunk.

    Raises
    ------
    TypeError
        If Toggl returns an unexpected response type.
    """
    try:
        raw_entries = fetch_range(
            config,
            chunk_start,
            chunk_end,
        )
        chunk_is_complete = True
        quota_error: TogglQuotaExhaustedError | None = None
    except TogglQuotaExhaustedError as error:
        raw_entries = error.partial_entries
        chunk_is_complete = False
        quota_error = error

    if raw_entries is None:
        raw_entries = []

    if not isinstance(raw_entries, list):
        raise TypeError(
            "Toggl returned an unexpected response type for "
            f"{chunk_start} to {chunk_end}: "
            f"{type(raw_entries).__name__}"
        )

    normalised_entries = _normalise_entries(
        raw_entries,
        project_names,
        chunk_start,
        chunk_end,
    )

    try:
        if chunk_is_complete:
            _delete_stale_entries(
                connection,
                normalised_entries,
                timezone,
                chunk_start,
                chunk_end,
            )

        upsert_normalised_rows(
            connection,
            normalised_entries,
        )

        if chunk_is_complete:
            _mark_chunk_complete(
                connection,
                chunk_start,
                chunk_end,
                mode,
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return ChunkRefreshResult(
        entry_count=len(normalised_entries),
        is_complete=chunk_is_complete,
        quota_error=quota_error,
    )


def _create_quota_exhausted_result(  # noqa: PLR0913
    connection: sqlite3.Connection,
    *,
    log_id: int,
    period_start: date,
    period_end: date,
    mode: str,
    chunk_start: date,
    chunk_end: date,
    completed_through: date | None,
    request_count: int,
    entry_count: int,
    quota_error: TogglQuotaExhaustedError,
    partial_entry_count: int,
) -> SyncResult:
    """Finish the sync log and create a quota-exhausted result."""
    message = (
        "Quota exhausted while downloading "
        f"{chunk_start} to {chunk_end}. "
        f"Saved {partial_entry_count} entries from "
        "complete pages received before the limit. "
        "The incomplete period was not marked as covered. "
        f"{quota_error}"
    )

    _finish_sync_log(
        connection,
        log_id,
        request_count,
        entry_count,
        "quota_exhausted",
        message,
    )

    completed_through_text = (
        completed_through.isoformat() if completed_through is not None else None
    )

    return {
        "status": "quota_exhausted",
        "start": period_start.isoformat(),
        "end": period_end.isoformat(),
        "mode": mode,
        "requests": request_count,
        "entries_saved": entry_count,
        "partial_chunk_start": chunk_start.isoformat(),
        "partial_chunk_end": chunk_end.isoformat(),
        "completed_through": completed_through_text,
        "quota_remaining": quota_error.remaining,
        "quota_resets_in_seconds": quota_error.resets_in,
        "message": message,
    }


def refresh_period(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
    start_day: DateInput,
    end_day: DateInput,
    mode: str = "force",
) -> SyncResult:
    """Download and reconcile a period.

    Complete chunks are saved and marked as covered. When quota is exhausted
    part-way through a paginated chunk, entries from complete pages are saved,
    but existing local entries are not deleted and the chunk remains pending.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Application configuration.
    start_day : date or str
        First date to refresh.
    end_day : date or str
        Last date to refresh.
    mode : str, default="force"
        Synchronisation mode recorded in coverage and log data.

    Returns
    -------
    dict[str, Any]
        Synchronisation result.
    """
    period_start = _parse_date(start_day, "start_day")
    period_end = _parse_date(end_day, "end_day")

    if period_end < period_start:
        raise ValueError("end_day must not be before start_day")

    chunk_size_days = int(config["api_chunk_days"])

    if chunk_size_days < 1:
        raise ValueError("api_chunk_days must be at least 1")

    timezone = ZoneInfo(config["timezone"])

    log_id = _start_sync_log(
        connection,
        period_start,
        period_end,
        mode,
    )

    _mark_period_pending(
        connection,
        period_start,
        period_end,
    )

    request_count = 0
    entry_count = 0
    completed_through: date | None = None
    result: SyncResult | None = None

    try:
        project_names, project_request_count = _prepare_project_names(
            connection,
            config,
        )
        request_count += project_request_count

        for chunk_start, chunk_end in date_ranges(
            period_start,
            period_end,
            chunk_size_days,
        ):
            if result is None:
                chunk_result = _refresh_chunk(
                    connection,
                    config,
                    project_names,
                    timezone,
                    chunk_start,
                    chunk_end,
                    mode,
                )

                request_count += 1
                entry_count += chunk_result.entry_count

                if chunk_result.is_complete:
                    completed_through = chunk_end

                    if chunk_end < period_end:
                        time.sleep(1.05)
                else:
                    quota_error = chunk_result.quota_error

                    if quota_error is None:
                        raise RuntimeError("An incomplete chunk has no quota error.")

                    result = _create_quota_exhausted_result(
                        connection,
                        log_id=log_id,
                        period_start=period_start,
                        period_end=period_end,
                        mode=mode,
                        chunk_start=chunk_start,
                        chunk_end=chunk_end,
                        completed_through=completed_through,
                        request_count=request_count,
                        entry_count=entry_count,
                        quota_error=quota_error,
                        partial_entry_count=chunk_result.entry_count,
                    )

        if result is None:
            _finish_sync_log(
                connection,
                log_id,
                request_count,
                entry_count,
                "ok",
                None,
            )

            result = {
                "status": "ok",
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "mode": mode,
                "requests": request_count,
                "entries_saved": entry_count,
                "completed_through": period_end.isoformat(),
            }
    except Exception as error:
        connection.rollback()

        _finish_sync_log(
            connection,
            log_id,
            request_count,
            entry_count,
            "failed",
            str(error),
        )
        raise

    return result


def synchronise_projects(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
) -> int:
    """Download and store the Toggl project catalogue.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Toggl configuration containing the workspace ID.

    Returns
    -------
    int
        Number of Toggl API requests made.

    """
    projects, request_count = fetch_workspace_projects(config)
    default_workspace_id = int(config["workspace_id"])
    fetched_at = _current_timestamp()
    project_rows: list[tuple[int, int, str, int, Any, str]] = []

    for project in projects:
        if isinstance(project, dict):
            project_id = project.get("id")
            project_name = project.get("name")

            if project_id is not None and project_name is not None:
                project_workspace_id = project.get("workspace_id")
                if project_workspace_id is None:
                    project_workspace_id = project.get("wid")
                if project_workspace_id is None:
                    project_workspace_id = default_workspace_id

                project_rows.append(
                    (
                        int(project_id),
                        int(project_workspace_id),
                        str(project_name),
                        int(bool(project.get("active", True))),
                        project.get("at"),
                        fetched_at,
                    )
                )

    if len(project_rows) > 0:
        connection.executemany(
            """
            INSERT INTO projects (
                id,
                workspace_id,
                name,
                active,
                updated_at,
                fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                workspace_id = excluded.workspace_id,
                name = excluded.name,
                active = excluded.active,
                updated_at = excluded.updated_at,
                fetched_at = excluded.fetched_at
            """,
            project_rows,
        )

    connection.execute("""
        UPDATE time_entries
        SET project_name = (
            SELECT projects.name
            FROM projects
            WHERE projects.id = time_entries.project_id
        )
        WHERE project_id IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM projects
              WHERE projects.id = time_entries.project_id
          )
        """)
    connection.commit()
    return request_count


def sync_missing(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
    start_day: str | None = None,
    end_day: str | None = None,
) -> SyncResult:
    """Download uncovered periods in chronological order.

    Processing stops when the Toggl quota is exhausted. Completed periods
    remain committed and covered.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Application configuration.
    start_day : str, optional
        First date to inspect. Defaults to ``tracking_start_date``.
    end_day : str, optional
        Last date to inspect. Defaults to yesterday.

    Returns
    -------
    dict[str, Any]
        Aggregate synchronisation result.

    """
    if start_day is None:
        period_start = date.fromisoformat(config["tracking_start_date"])
    else:
        period_start = date.fromisoformat(start_day)

    if end_day is None:
        period_end = date.today() - timedelta(days=1)
    else:
        period_end = date.fromisoformat(end_day)

    missing_ranges = find_missing_ranges(
        connection,
        period_start,
        period_end,
    )
    period_results: list[SyncResult] = []
    quota_was_exhausted = False

    for missing_start, missing_end in missing_ranges:
        if quota_was_exhausted is False:
            period_result = refresh_period(
                connection,
                config,
                missing_start,
                missing_end,
                mode="missing",
            )
            period_results.append(period_result)

            if period_result["status"] == "quota_exhausted":
                quota_was_exhausted = True

    if quota_was_exhausted:
        result: SyncResult = {
            "status": "quota_exhausted",
            "requested_start": period_start.isoformat(),
            "requested_end": period_end.isoformat(),
            "periods_processed": len(period_results),
            "results": period_results,
            "message": (
                "The available Toggl quota was exhausted. "
                "All complete chunks and all entries received "
                "from complete pages have been saved. Run "
                "sync_missing(connection, config) again after "
                "the quota has reset."
            ),
        }
    else:
        result = {
            "status": "ok",
            "requested_start": period_start.isoformat(),
            "requested_end": period_end.isoformat(),
            "periods_processed": len(period_results),
            "results": period_results,
            "message": "All missing periods were downloaded.",
        }

    return result
