"""Analyse when recorded work occurs.

Working time is classified into mutually exclusive categories: work on
configured non-working days, weekend work, weekday work outside core hours
and normal weekday core-hours work.

Non-working days take priority over weekends, and weekends take priority over
outside-core classification, preventing recorded time from being counted in
multiple categories.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import TypedDict

import pandas as pd

NON_WORKING_EXCEPTION_TYPES = (
    "public_holiday",
    "annual_leave",
    "closure_day",
    "overtime_compensation",
)

WEEKLY_PATTERN_COLUMNS = [
    "week_start",
    "total_hours",
    "normal_hours",
    "outside_core_hours",
    "weekend_hours",
    "non_working_day_hours",
]


class WorkingPattern(TypedDict):
    """Summary of working time by working-pattern category."""

    total_hours: float
    outside_core_hours: float
    weekend_hours: float
    non_working_day_hours: float
    normal_hours: float


def _empty_working_pattern() -> WorkingPattern:
    """Return an empty working-pattern summary."""
    result: WorkingPattern = {
        "total_hours": 0.0,
        "outside_core_hours": 0.0,
        "weekend_hours": 0.0,
        "non_working_day_hours": 0.0,
        "normal_hours": 0.0,
    }

    return result


def _load_non_working_days(
    connection: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> set[date]:
    """Load configured non-working dates within a period.

    Sick leave is deliberately excluded because it does not represent
    a day which was planned as non-working. Overtime compensation is
    included because it represents planned time off.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    start_date : date
        First date to inspect.
    end_date : date
        Last date to inspect.

    Returns
    -------
    set[date]
        Configured non-working dates.

    """
    rows = connection.execute(
        """
        SELECT day
        FROM day_exceptions
        WHERE day BETWEEN ? AND ?
          AND kind IN (
              'public_holiday',
              'annual_leave',
              'closure_day',
              'overtime_compensation'
          )
        """,
        (
            start_date.isoformat(),
            end_date.isoformat(),
        ),
    ).fetchall()

    non_working_days = {date.fromisoformat(row["day"]) for row in rows}

    return non_working_days


def _prepare_pattern_entries(
    entries: pd.DataFrame,
    connection: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Prepare time segments for working-pattern analysis.

    Parameters
    ----------
    entries : pandas.DataFrame
        Daily time segments produced by working-time analysis.
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    start_date : date
        First date in the analysis period.
    end_date : date
        Last date in the analysis period.

    Returns
    -------
    pandas.DataFrame
        Prepared copy of the supplied entries.

    """
    data = entries.copy()

    data["day"] = pd.to_datetime(data["day"]).dt.date

    for column in (
        "seconds",
        "outside_core_seconds",
        "weekend_seconds",
    ):
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        ).fillna(0.0)

    non_working_days = _load_non_working_days(
        connection=connection,
        start_date=start_date,
        end_date=end_date,
    )

    data["is_non_working_day"] = data["day"].isin(non_working_days)
    data["is_weekend"] = data["weekend_seconds"] > 0

    return data


def get_working_pattern(
    entries: pd.DataFrame,
    start_date: date,
    end_date: date,
    connection: sqlite3.Connection,
) -> WorkingPattern:
    """Summarise working time by mutually exclusive category.

    Parameters
    ----------
    entries : pandas.DataFrame
        Daily time segments produced by working-time analysis.
    start_date : date
        First date in the analysis period.
    end_date : date
        Last date in the analysis period.
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    WorkingPattern
        Hours spent in each working-pattern category.

    """
    result = _empty_working_pattern()

    if entries.empty is False:
        data = _prepare_pattern_entries(
            entries=entries,
            connection=connection,
            start_date=start_date,
            end_date=end_date,
        )

        total_seconds = float(data["seconds"].sum())

        non_working_day_seconds = float(
            data.loc[
                data["is_non_working_day"],
                "seconds",
            ].sum()
        )

        weekend_seconds = float(
            data.loc[
                ~data["is_non_working_day"],
                "weekend_seconds",
            ].sum()
        )

        normal_weekday_mask = ~data["is_weekend"] & ~data["is_non_working_day"]

        outside_core_seconds = float(
            data.loc[
                normal_weekday_mask,
                "outside_core_seconds",
            ].sum()
        )

        exceptional_seconds = (
            non_working_day_seconds + weekend_seconds + outside_core_seconds
        )

        normal_seconds = max(
            0.0,
            total_seconds - exceptional_seconds,
        )

        result = {
            "total_hours": total_seconds / 3600.0,
            "outside_core_hours": (outside_core_seconds / 3600.0),
            "weekend_hours": (weekend_seconds / 3600.0),
            "non_working_day_hours": (non_working_day_seconds / 3600.0),
            "normal_hours": (normal_seconds / 3600.0),
        }

    return result


def get_weekly_working_patterns(
    entries: pd.DataFrame,
    start_date: date,
    end_date: date,
    connection: sqlite3.Connection,
) -> pd.DataFrame:
    """Summarise mutually exclusive working-pattern categories by week.

    Parameters
    ----------
    entries : pandas.DataFrame
        Daily time segments produced by working-time analysis.
    start_date : date
        First date in the analysis period.
    end_date : date
        Last date in the analysis period.
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    pandas.DataFrame
        Weekly hours in each working-pattern category.

    """
    weekly = pd.DataFrame(columns=WEEKLY_PATTERN_COLUMNS)

    if entries.empty is False:
        data = _prepare_pattern_entries(
            entries=entries,
            connection=connection,
            start_date=start_date,
            end_date=end_date,
        )

        entry_dates = pd.to_datetime(data["day"])
        data["week_start"] = entry_dates - pd.to_timedelta(
            entry_dates.dt.weekday,
            unit="D",
        )

        data["non_working_day_seconds"] = 0.0
        data["exclusive_weekend_seconds"] = 0.0
        data["exclusive_outside_core_seconds"] = 0.0
        data["normal_seconds"] = 0.0

        non_working_mask = data["is_non_working_day"]

        data.loc[
            non_working_mask,
            "non_working_day_seconds",
        ] = data.loc[
            non_working_mask,
            "seconds",
        ]

        weekend_mask = data["is_weekend"] & ~data["is_non_working_day"]

        data.loc[
            weekend_mask,
            "exclusive_weekend_seconds",
        ] = data.loc[
            weekend_mask,
            "seconds",
        ]

        ordinary_weekday_mask = ~data["is_weekend"] & ~data["is_non_working_day"]

        data.loc[
            ordinary_weekday_mask,
            "exclusive_outside_core_seconds",
        ] = data.loc[
            ordinary_weekday_mask,
            "outside_core_seconds",
        ]

        data.loc[
            ordinary_weekday_mask,
            "normal_seconds",
        ] = (
            data.loc[
                ordinary_weekday_mask,
                "seconds",
            ]
            - data.loc[
                ordinary_weekday_mask,
                "outside_core_seconds",
            ]
        ).clip(lower=0)

        weekly = data.groupby(
            "week_start",
            as_index=False,
        ).agg(
            total_seconds=(
                "seconds",
                "sum",
            ),
            normal_seconds=(
                "normal_seconds",
                "sum",
            ),
            outside_core_seconds=(
                "exclusive_outside_core_seconds",
                "sum",
            ),
            weekend_seconds=(
                "exclusive_weekend_seconds",
                "sum",
            ),
            non_working_day_seconds=(
                "non_working_day_seconds",
                "sum",
            ),
        )

        hour_columns = {
            "total_seconds": "total_hours",
            "normal_seconds": "normal_hours",
            "outside_core_seconds": ("outside_core_hours"),
            "weekend_seconds": "weekend_hours",
            "non_working_day_seconds": ("non_working_day_hours"),
        }

        for seconds_column, hours_column in hour_columns.items():
            weekly[hours_column] = weekly[seconds_column] / 3600.0

        weekly = weekly[WEEKLY_PATTERN_COLUMNS]

    return weekly
