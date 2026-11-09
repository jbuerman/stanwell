"""Track local data coverage and pending refresh periods.

Coverage records which calendar days have been fetched from Toggl.
Days may also be marked as pending when they need to be refreshed.

This module manages those states and groups consecutive pending or
missing days into date ranges for synchronisation.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

DateRange = tuple[date, date]


def _dates_in_range(
    start_date: date | str,
    end_date: date | str,
) -> list[date]:
    """Return all dates in an inclusive date range.

    Parameters
    ----------
    start_date : date or str
        First date in the range.
    end_date : date or str
        Last date in the range.

    Returns
    -------
    list[date]
        Dates from ``start_date`` through ``end_date``, inclusive.

    """
    start = (
        date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    )
    end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date

    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _group_consecutive_dates(
    dates: list[date],
) -> list[DateRange]:
    """Group dates into consecutive inclusive ranges.

    Sort the supplied dates and combine adjacent dates into inclusive
    start-and-end ranges. Duplicate dates do not create additional
    ranges.

    Parameters
    ----------
    dates : list[datetime.date]
        Dates to group.

    Returns
    -------
    list[DateRange]
        Consecutive date ranges represented by inclusive start and end
        dates. An empty input produces an empty list.
    """
    ranges: list[DateRange] = []

    sorted_dates = sorted(set(dates))

    if sorted_dates:
        range_start = sorted_dates[0]
        previous_date = sorted_dates[0]

        for current_date in sorted_dates[1:]:
            is_consecutive = current_date == previous_date + timedelta(days=1)

            if is_consecutive:
                previous_date = current_date

            else:
                ranges.append(
                    (
                        range_start,
                        previous_date,
                    )
                )

                range_start = current_date
                previous_date = current_date

        ranges.append(
            (
                range_start,
                previous_date,
            )
        )

    return ranges


def mark_refresh_pending(
    connection: sqlite3.Connection,
    start_date: date | str,
    end_date: date | str,
) -> None:
    """Mark an inclusive date range as requiring refresh.

    Existing coverage rows are updated and missing rows are created.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    start_date : date or str
        First date to mark as pending.
    end_date : date or str
        Last date to mark as pending.

    """
    for day in _dates_in_range(start_date, end_date):
        connection.execute(
            """
            INSERT INTO data_coverage (
                day,
                refresh_pending
            )
            VALUES (?, 1)
            ON CONFLICT(day) DO UPDATE SET
                refresh_pending = 1
            """,
            (day.isoformat(),),
        )

    connection.commit()


def mark_refresh_complete(
    connection: sqlite3.Connection,
    start_date: date | str,
    end_date: date | str,
) -> None:
    """Mark an inclusive date range as successfully refreshed.

    Pending refresh status is cleared and ``refreshed_at`` is updated
    for each existing coverage row in the range.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    start_date : date or str
        First date to mark as complete.
    end_date : date or str
        Last date to mark as complete.

    """
    refreshed_at = datetime.now().astimezone().isoformat()

    for day in _dates_in_range(start_date, end_date):
        connection.execute(
            """
            UPDATE data_coverage
            SET
                refresh_pending = 0,
                refreshed_at = ?
            WHERE day = ?
            """,
            (
                refreshed_at,
                day.isoformat(),
            ),
        )

    connection.commit()


def get_pending_refresh_days(
    connection: sqlite3.Connection,
) -> list[date]:
    """Return all days awaiting refresh.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    list[date]
        Pending refresh dates in ascending order.

    """
    rows = connection.execute("""
        SELECT day
        FROM data_coverage
        WHERE refresh_pending = 1
        ORDER BY day
        """).fetchall()

    return [date.fromisoformat(row["day"]) for row in rows]


def pending_refresh_ranges(
    connection: sqlite3.Connection,
) -> list[DateRange]:
    """Return pending refresh days grouped into consecutive ranges.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    list[DateRange]
        Consecutive ranges of dates awaiting refresh.

    """
    pending_days = get_pending_refresh_days(connection)

    return _group_consecutive_dates(pending_days)


def count_pending_refresh_dates(
    connection: sqlite3.Connection,
) -> int:
    """Return the number of dates awaiting refresh.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    int
        Number of dates marked as pending.

    """
    row = connection.execute("""
        SELECT COUNT(*) AS count
        FROM data_coverage
        WHERE refresh_pending = 1
        """).fetchone()

    return int(row["count"])


def find_missing_ranges(
    connection: sqlite3.Connection,
    start_date: date | str,
    end_date: date | str,
) -> list[DateRange]:
    """Find consecutive date ranges not present in local coverage.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    start_date : date or str
        First date to inspect.
    end_date : date or str
        Last date to inspect.

    Returns
    -------
    list[DateRange]
        Consecutive ranges of dates absent from ``covered_days``.

    """
    requested_days = _dates_in_range(
        start_date,
        end_date,
    )

    if not requested_days:
        return []

    covered_rows = connection.execute(
        """
        SELECT day
        FROM covered_days
        WHERE day BETWEEN ? AND ?
        """,
        (
            requested_days[0].isoformat(),
            requested_days[-1].isoformat(),
        ),
    )

    covered_days = {date.fromisoformat(row["day"]) for row in covered_rows}

    missing_days = [day for day in requested_days if day not in covered_days]

    return _group_consecutive_dates(missing_days)


def pending_sync_ranges(
    connection,
    start_day,
    end_day,
):
    """Return all date ranges that currently require synchronisation.

    Combine dates that have never been successfully synchronised with
    dates that have been marked for refresh. Consecutive dates are
    returned as ranges regardless of why each individual date requires
    synchronisation.

    Parameters
    ----------
    connection : sqlite3.Connection
        Open connection to the Stanwell database.
    start_day : datetime.date
        First date to consider for synchronisation.
    end_day : datetime.date
        Last date to consider for synchronisation.

    Returns
    -------
    list[DateRange]
        Consecutive ranges containing every date that either has no
        successful coverage record or is marked as pending refresh.
        Returns an empty list when no dates require synchronisation.

    Raises
    ------
    ValueError
        If ``end_day`` is earlier than ``start_day``.

    Notes
    -----
    A date may require synchronisation for either of two reasons:

    * it has never been successfully downloaded and therefore has no
      entry in ``covered_days``;
    * it has previously been downloaded but is marked with
      ``refresh_pending = 1`` in ``data_coverage``.

    These states remain distinct in the database, but callers do not
    need to distinguish between them when deciding which dates to
    synchronise.
    """
    if end_day < start_day:
        raise ValueError("end_day must not be before start_day")

    missing_ranges = find_missing_ranges(
        connection,
        start_day,
        end_day,
    )

    refresh_ranges = pending_refresh_ranges(
        connection,
    )

    required_days: set[date] = set()

    for range_start, range_end in missing_ranges:
        current_date = range_start

        while current_date <= range_end:
            required_days.add(current_date)

            current_date += timedelta(days=1)

    for range_start, range_end in refresh_ranges:
        clipped_start = max(
            range_start,
            start_day,
        )

        clipped_end = min(
            range_end,
            end_day,
        )

        current_date = clipped_start

        while current_date <= clipped_end:
            required_days.add(current_date)

            current_date += timedelta(days=1)

    result = _group_consecutive_dates(list(required_days))

    return result


def summarise_sync_ranges(
    ranges: list[tuple[date, date]],
) -> dict[str, Any]:
    """Summarise date ranges that still require synchronisation.

    Parameters
    ----------
    ranges : list[tuple[datetime.date, datetime.date]]
        Consecutive date ranges that require synchronisation.

    Returns
    -------
    dict[str, Any]
        Summary containing the number of individual pending dates,
        the first pending date and the last pending date. The boundary
        dates are returned as ISO-formatted strings.

    Notes
    -----
    The returned count is the number of calendar dates represented by
    the ranges, rather than the number of ranges.
    """
    pending_count = sum(
        (range_end - range_start).days + 1 for range_start, range_end in ranges
    )

    first_pending = ranges[0][0].isoformat() if ranges else None

    last_pending = ranges[-1][1].isoformat() if ranges else None

    return {
        "pending_count": pending_count,
        "first_pending": first_pending,
        "last_pending": last_pending,
    }
