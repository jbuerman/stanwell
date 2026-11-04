"""Track local data coverage and pending refresh periods.

Coverage records which calendar days have been fetched from Toggl.
Days may also be marked as pending when they need to be refreshed.

This module manages those states and groups consecutive pending or
missing days into date ranges for synchronisation.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

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

    Parameters
    ----------
    dates : list[date]
        Dates to group.

    Returns
    -------
    list[DateRange]
        Consecutive date ranges represented by start and end dates.

    """
    if not dates:
        return []

    sorted_dates = sorted(dates)

    ranges: list[DateRange] = []

    range_start = sorted_dates[0]
    previous_date = sorted_dates[0]

    for current_date in sorted_dates[1:]:
        if current_date == previous_date + timedelta(days=1):
            previous_date = current_date
            continue

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
