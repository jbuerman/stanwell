"""Analyse stored time entries and calculate working-time summaries.

A time entry is a complete record stored from Toggl. Entries are converted
from UTC to local time and split at local midnight into daily segments.
Segments are then used to calculate core-hours, weekend time and daily
working-time balances, taking configured working days and exceptions into
account.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from dateutil.parser import isoparse

SEGMENT_COLUMNS = [
    "entry_id",
    "day",
    "weekday",
    "start_local",
    "stop_local",
    "seconds",
    "outside_core_seconds",
    "weekend_seconds",
    "description",
]


def _empty_time_segments() -> pd.DataFrame:
    """Create an empty time-segment DataFrame.

    Returns
    -------
    pandas.DataFrame
        An empty DataFrame with the standard time-segment columns.

    """
    return pd.DataFrame(columns=SEGMENT_COLUMNS)


def _calculate_segment_inside_core_seconds(
    segment_start: datetime,
    segment_end: datetime,
    segment_day: date,
    core_start: time,
    core_end: time,
    timezone: ZoneInfo,
) -> float:
    """Calculate how much of a segment falls within core hours.

    Parameters
    ----------
    segment_start : datetime
        Start of the time segment.
    segment_end : datetime
        End of the time segment.
    segment_day : date
        Local calendar date containing the segment.
    core_start : time
        Start of the configured core-hours period.
    core_end : time
        End of the configured core-hours period.
    timezone : zoneinfo.ZoneInfo
        Local timezone used for the calculation.

    Returns
    -------
    float
        Number of seconds within the configured core-hours period.

    """
    core_period_start = datetime.combine(
        segment_day,
        core_start,
        tzinfo=timezone,
    )
    core_period_end = datetime.combine(
        segment_day,
        core_end,
        tzinfo=timezone,
    )

    overlap_start = max(
        segment_start.astimezone(UTC),
        core_period_start.astimezone(UTC),
    )
    overlap_end = min(
        segment_end.astimezone(UTC),
        core_period_end.astimezone(UTC),
    )

    return max(
        0.0,
        (overlap_end - overlap_start).total_seconds(),
    )


def _split_time_entry_into_daily_segments(
    entry: Any,
    timezone: ZoneInfo,
    core_start: time,
    core_end: time,
) -> Iterator[tuple[Any, ...]]:
    """Split a time entry into local calendar-day segments.

    An entry spanning local midnight produces one segment for each
    calendar day. Elapsed durations are calculated in UTC so that
    daylight-saving transitions do not change the recorded duration.
    """
    segment_start = isoparse(entry.start_utc).astimezone(timezone)
    entry_end = isoparse(entry.stop_utc).astimezone(timezone)

    while segment_start.astimezone(UTC) < entry_end.astimezone(UTC):
        next_midnight = datetime.combine(
            segment_start.date() + timedelta(days=1),
            time.min,
            tzinfo=timezone,
        )

        segment_end = min(
            entry_end,
            next_midnight,
            key=lambda value: value.astimezone(UTC),
        )

        segment_day = segment_start.date()

        segment_seconds = (
            segment_end.astimezone(UTC) - segment_start.astimezone(UTC)
        ).total_seconds()

        inside_core_seconds = _calculate_segment_inside_core_seconds(
            segment_start=segment_start,
            segment_end=segment_end,
            segment_day=segment_day,
            core_start=core_start,
            core_end=core_end,
            timezone=timezone,
        )

        outside_core_seconds = segment_seconds - min(
            segment_seconds,
            inside_core_seconds,
        )

        weekend_seconds = (
            segment_seconds if segment_day.weekday() >= 5 else 0.0  # noqa: PLR2004
        )

        yield (
            entry.id,
            str(segment_day),
            segment_day.strftime("%A"),
            segment_start,
            segment_end,
            segment_seconds,
            outside_core_seconds,
            weekend_seconds,
            entry.description,
        )

        segment_start = segment_end


def load_time_segments(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    """Load completed time entries as daily local-time segments.

    Only entries with a stop time and a non-negative duration are
    loaded. Entries spanning multiple local calendar days are split at
    midnight.

    Each resulting segment includes its duration, the time outside
    configured core hours and the time occurring on a weekend.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Configuration containing ``timezone``, ``core_start`` and
        ``core_end``.

    Returns
    -------
    pandas.DataFrame
        One row per daily time-entry segment.

    """
    entries = pd.read_sql_query(
        """
        SELECT *
        FROM time_entries
        WHERE stop_utc IS NOT NULL
          AND duration_seconds >= 0
        """,
        connection,
    )

    if entries.empty:
        return _empty_time_segments()

    timezone = ZoneInfo(config["timezone"])
    core_start = time.fromisoformat(config["core_start"])
    core_end = time.fromisoformat(config["core_end"])

    segments: list[tuple[Any, ...]] = []

    for entry in entries.itertuples(index=False):
        segments.extend(
            _split_time_entry_into_daily_segments(
                entry=entry,
                timezone=timezone,
                core_start=core_start,
                core_end=core_end,
            )
        )

    return pd.DataFrame(
        segments,
        columns=SEGMENT_COLUMNS,
    )


def _load_day_exceptions(
    connection: sqlite3.Connection,
) -> dict[str, str]:
    """Load configured day exceptions.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    dict[str, str]
        Mapping from ISO-formatted dates to exception kinds.

    """
    rows = connection.execute("""
        SELECT day, kind
        FROM day_exceptions
        """)
    return {row["day"]: row["kind"] for row in rows}


def _expected_hours_for_day(
    day: date,
    config: Mapping[str, Any],
    day_exceptions: Mapping[str, str],
) -> float:
    """Calculate expected working hours for one day.

    Parameters
    ----------
    day : date
        Day for which expected hours are calculated.
    config : collections.abc.Mapping
        Configuration containing ``workday_hours`` and ``working_days``.
    day_exceptions : collections.abc.Mapping
        Mapping from ISO-formatted dates to exception kinds.

    Returns
    -------
    float
        Expected hours for the given day.

    """
    is_working_day = day.weekday() in config["working_days"]
    is_exception = str(day) in day_exceptions

    expected_hours = 0.0

    if is_working_day and not is_exception:
        expected_hours = float(config["workday_hours"])

    return expected_hours


def _balance_adjustment_for_day(
    day: date,
    config: Mapping[str, Any],
    day_exceptions: Mapping[str, str],
) -> float:
    """Calculate the working-time balance adjustment for one day.

    Parameters
    ----------
    day : date
        Day for which the adjustment is calculated.
    config : collections.abc.Mapping
        Configuration containing ``workday_hours`` and ``working_days``.
    day_exceptions : collections.abc.Mapping
        Mapping from ISO-formatted dates to exception kinds.

    Returns
    -------
    float
        Balance adjustment in hours. Overtime compensation on a configured
        working day produces a negative adjustment equal to one workday.
        Other days produce no adjustment.

    """
    is_working_day = day.weekday() in config["working_days"]
    exception_kind = day_exceptions.get(str(day))

    balance_adjustment = 0.0

    if is_working_day and exception_kind == "overtime_compensation":
        balance_adjustment = -float(config["workday_hours"])

    return balance_adjustment


def _create_daily_summary(
    start_date: date,
    end_date: date,
    config: Mapping[str, Any],
    exception_days: Mapping[str, str],
) -> pd.DataFrame:
    """Create the initial daily working-time summary.

    Parameters
    ----------
    start_date : date
        First date to include.
    end_date : date
        Last date to include.
    config : collections.abc.Mapping
        Working-time configuration.
    exception_days : collections.abc.Mapping
        ISO-formatted dates excluded from expected working hours as mapping to exception kinds.

    Returns
    -------
    pandas.DataFrame
        One row per date, including expected working hours.

    """
    date_range = pd.date_range(
        start=start_date,
        end=end_date,
    )

    daily_summary = pd.DataFrame(
        {
            "day": date_range.date,
            "weekday": date_range.day_name(),
        }
    )

    daily_summary["expected_hours"] = [
        _expected_hours_for_day(
            day=day,
            config=config,
            day_exceptions=exception_days,
        )
        for day in daily_summary["day"]
    ]

    daily_summary["balance_adjustment_hours"] = [
        _balance_adjustment_for_day(
            day=day,
            config=config,
            day_exceptions=exception_days,
        )
        for day in daily_summary["day"]
    ]

    return daily_summary


def _aggregate_daily_actual_time(
    segments: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate segment durations by day.

    Parameters
    ----------
    segments : pandas.DataFrame
        Daily time-entry segments.

    Returns
    -------
    pandas.DataFrame
        Total recorded seconds for each day.

    """
    if segments.empty:
        return pd.DataFrame(
            {
                "day": pd.Series(dtype="object"),
                "seconds": pd.Series(dtype="float64"),
            }
        )

    daily_actual_time = segments.groupby(
        "day",
        as_index=False,
    ).agg(seconds=("seconds", "sum"))

    daily_actual_time["day"] = pd.to_datetime(daily_actual_time["day"]).dt.date

    return daily_actual_time


def calculate_working_time(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
    start_day: str | date,
    end_day: str | date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate working-time data for a date range.

    Recorded time entries are converted into local daily segments and
    restricted to the requested date range. Expected and actual hours
    are then calculated for every day in that range.

    Expected hours are zero for days outside the configured working
    week and for dates present in ``day_exceptions``.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Configuration containing timezone, core-hours and working-day
        settings.
    start_day : str
        First date to include, in ISO format.
    end_day : str
        Last date to include, in ISO format.

    Returns
    -------
    tuple[pandas.DataFrame, pandas.DataFrame]
        The filtered daily time-entry segments and a daily working-time
        summary.

    """
    start_date = date.fromisoformat(str(start_day))
    end_date = date.fromisoformat(str(end_day))

    segments = load_time_segments(
        connection,
        config,
    )

    if not segments.empty:
        segments = segments[
            (segments["day"] >= str(start_date)) & (segments["day"] <= str(end_date))
        ].copy()

    exception_days = _load_day_exceptions(connection)

    daily_summary = _create_daily_summary(
        start_date=start_date,
        end_date=end_date,
        config=config,
        exception_days=exception_days,
    )

    daily_actual_time = _aggregate_daily_actual_time(segments)

    daily_summary = daily_summary.merge(
        daily_actual_time,
        on="day",
        how="left",
    )

    daily_summary["seconds"] = daily_summary["seconds"].fillna(0.0)

    daily_summary["actual_hours"] = daily_summary["seconds"] / 3600

    daily_summary["balance_hours"] = (
        daily_summary["actual_hours"]
        - daily_summary["expected_hours"]
        + daily_summary["balance_adjustment_hours"]
    )

    daily_dates = pd.to_datetime(daily_summary["day"])

    daily_summary["week_start"] = daily_dates - pd.to_timedelta(
        daily_dates.dt.weekday,
        unit="D",
    )

    return segments, daily_summary
