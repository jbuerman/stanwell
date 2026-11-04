"""Projection calculations for the working-time dashboard."""

from datetime import date, timedelta

import pandas as pd


def prepare_week_remaining_projection(
    daily: pd.DataFrame,
    today: date,
) -> pd.DataFrame:
    """Calculate required work for the remaining days of the week.

    Calculate the outstanding working-time requirement for the week
    containing ``today`` and distribute it equally across the remaining
    working days. The calculation assumes that no further work is done
    on ``today``.

    Days with zero expected hours, such as weekends, annual leave,
    public holidays or closure days, are excluded from the remaining
    working days. If the weekly requirement has already been met or
    exceeded, each remaining working day is assigned zero required
    hours.

    Parameters
    ----------
    daily : pandas.DataFrame
        Daily working-time data. The DataFrame must contain the columns
        ``day``, ``weekday``, ``expected_hours`` and ``actual_hours``.
        It may also contain ``balance_adjustment_hours``.
    today : datetime.date
        Date from which the remaining part of the current week is
        calculated. Work recorded on this date contributes to the
        completed weekly hours, but no further work on this date is
        assumed.

    Returns
    -------
    pandas.DataFrame
        A DataFrame containing one row for each remaining working day
        in the current Monday-to-Sunday week. It contains the columns
        ``day``, ``weekday`` and ``required_hours``. The remaining
        requirement is distributed equally across these days.

        An empty DataFrame with these columns is returned if ``daily``
        is empty, contains no data for the current week or there are no
        remaining working days.

    Notes
    -----
    A remaining day is considered a working day only when its
    ``expected_hours`` value is greater than zero. Consequently, the
    function does not need to identify annual leave, public holidays
    or closure days directly; these are expected to have already been
    reflected in the daily working-time calculation.

    The outstanding requirement is bounded at zero, so working more
    than the weekly requirement never produces negative required hours
    for subsequent days.

    Examples
    --------
    If the normal requirement is 7 hours per weekday and 22 hours have
    been worked by the end of Wednesday, the weekly requirement is
    35 hours. The remaining 13 hours are distributed across Thursday
    and Friday, resulting in 6.5 required hours on each day.
    """
    if daily.empty:
        return pd.DataFrame(
            columns=[
                "day",
                "weekday",
                "required_hours",
            ]
        )

    week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=6)

    weekly = daily.copy()

    weekly["day"] = pd.to_datetime(weekly["day"]).dt.date

    weekly = weekly[(weekly["day"] >= week_start) & (weekly["day"] <= week_end)].copy()

    if weekly.empty:
        return pd.DataFrame(
            columns=[
                "day",
                "weekday",
                "required_hours",
            ]
        )

    total_expected = (
        pd.to_numeric(
            weekly["expected_hours"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )

    actual_so_far = (
        pd.to_numeric(
            weekly.loc[
                weekly["day"] <= today,
                "actual_hours",
            ],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )

    adjustment_so_far = 0.0

    if "balance_adjustment_hours" in weekly.columns:
        adjustment_so_far = (
            pd.to_numeric(
                weekly.loc[
                    weekly["day"] <= today,
                    "balance_adjustment_hours",
                ],
                errors="coerce",
            )
            .fillna(0)
            .sum()
        )

    remaining_hours = max(
        0.0,
        total_expected - actual_so_far - adjustment_so_far,
    )

    remaining_days = weekly[
        (weekly["day"] > today)
        & (
            pd.to_numeric(
                weekly["expected_hours"],
                errors="coerce",
            ).fillna(0)
            > 0
        )
    ].copy()

    if remaining_days.empty:
        return pd.DataFrame(
            columns=[
                "day",
                "weekday",
                "required_hours",
            ]
        )

    required_per_day = remaining_hours / len(remaining_days)

    remaining_days["required_hours"] = required_per_day

    return remaining_days[
        [
            "day",
            "weekday",
            "required_hours",
        ]
    ]
