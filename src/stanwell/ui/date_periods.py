"""Provide calendar-period calculations used by the dashboard."""

from __future__ import annotations

from datetime import date, timedelta


def monday_of_week(day: date) -> date:
    """Return the Monday of the week containing a date.

    Parameters
    ----------
    day : date
        Date for which to determine the week.

    Returns
    -------
    date
        Monday belonging to the same calendar week.

    """
    monday = day - timedelta(days=day.weekday())

    return monday


def sunday_of_week(day: date) -> date:
    """Return the Sunday of the week containing a date.

    Parameters
    ----------
    day : date
        Date for which to determine the week.

    Returns
    -------
    date
        Sunday belonging to the same calendar week.

    """
    sunday = monday_of_week(day) + timedelta(days=6)

    return sunday


def n_week_period(
    end_date: date,
    number_of_weeks: int,
) -> tuple[date, date]:
    """Return an inclusive calendar-aligned period.

    The period begins on a Monday and covers the specified number of
    calendar weeks up to ``end_date``. The current incomplete week
    therefore ends on ``end_date`` rather than the following Sunday.

    Parameters
    ----------
    end_date : date
        Last date to include.
    number_of_weeks : int
        Number of calendar weeks represented by the period.

    Returns
    -------
    tuple[date, date]
        Inclusive start and end dates.

    Raises
    ------
    ValueError
        If ``number_of_weeks`` is less than one.

    """
    if number_of_weeks < 1:
        raise ValueError("number_of_weeks must be at least 1")

    current_week_start = monday_of_week(end_date)

    period_start = current_week_start - timedelta(weeks=number_of_weeks - 1)

    period = (
        period_start,
        end_date,
    )

    return period
