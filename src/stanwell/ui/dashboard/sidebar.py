"""Render dashboard period selection and stored-data information.

The sidebar allows the user to select the period analysed by the dashboard.
Preset periods are calculated from the date stored in ``DashboardContext``
so the entire dashboard uses the same definition of today.

The sidebar also reports the locally available data range and warns when the
selected period extends beyond stored Toggl data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

import streamlit as st
from dateutil.relativedelta import relativedelta

from stanwell.ui.dashboard.context import (
    DashboardContext,
)
from stanwell.ui.date_periods import (
    monday_of_week,
    n_week_period,
    sunday_of_week,
)

PERIOD_OPTIONS: Final[tuple[str, ...]] = (
    "This week",
    "Last 2 weeks",
    "Last 4 weeks",
    "Last 8 weeks",
    "Last N weeks",
    "Past month",
    "Past 3 months",
    "Past 6 months",
    "Past year",
    "Custom dates",
)

WEEK_BASED_PERIODS: Final[frozenset[str]] = frozenset(
    {
        "This week",
        "Last 2 weeks",
        "Last 4 weeks",
        "Last 8 weeks",
        "Last N weeks",
    }
)


@dataclass(frozen=True)
class AnalysisPeriod:
    """Inclusive date range selected for dashboard analysis."""

    start: date
    """First date in the analysis period."""

    end: date
    """Last date in the analysis period."""


def _preset_period(
    period_option: str,
    today: date,
    number_of_weeks: int | None = None,
) -> AnalysisPeriod:
    """Calculate a predefined dashboard analysis period.

    Parameters
    ----------
    period_option : str
        Selected period label.
    today : date
        Current date used as the end of relative periods.
    number_of_weeks : int or None, optional
        Number of weeks used by ``Last N weeks``.

    Returns
    -------
    AnalysisPeriod
        Calculated inclusive analysis period.

    Raises
    ------
    ValueError
        If the period option is unknown or ``Last N weeks`` is selected
        without a valid number of weeks.

    """
    if period_option == "This week":
        period_start, period_end = n_week_period(
            today,
            1,
        )
    elif period_option == "Last 2 weeks":
        period_start, period_end = n_week_period(
            today,
            2,
        )
    elif period_option == "Last 4 weeks":
        period_start, period_end = n_week_period(
            today,
            4,
        )
    elif period_option == "Last 8 weeks":
        period_start, period_end = n_week_period(
            today,
            8,
        )
    elif period_option == "Last N weeks":
        if number_of_weeks is None:
            raise ValueError("number_of_weeks is required for Last N weeks")

        period_start, period_end = n_week_period(
            today,
            number_of_weeks,
        )
    elif period_option == "Past month":
        period_start = today - relativedelta(months=1)
        period_end = today
    elif period_option == "Past 3 months":
        period_start = today - relativedelta(months=3)
        period_end = today
    elif period_option == "Past 6 months":
        period_start = today - relativedelta(months=6)
        period_end = today
    elif period_option == "Past year":
        period_start = today - relativedelta(years=1)
        period_end = today
    else:
        raise ValueError(f"Unknown period option: {period_option}")

    period = AnalysisPeriod(
        start=period_start,
        end=period_end,
    )

    return period


def _default_custom_start(
    context: DashboardContext,
) -> date:
    """Determine the default start date for a custom period.

    The default is 90 days before today. If stored data begins later than
    that date, the earliest stored date is used instead.

    Parameters
    ----------
    context : DashboardContext
        Shared dashboard state.

    Returns
    -------
    date
        Default custom-period start date.

    """
    default_start = context.today - timedelta(days=90)

    if context.earliest_data is not None and context.earliest_data > default_start:
        default_start = context.earliest_data

    return default_start


def _custom_period(
    selected_range: date | tuple[date, ...] | list[date],
    default_start: date,
    today: date,
) -> AnalysisPeriod:
    """Convert Streamlit custom-date input into an analysis period.

    Streamlit may temporarily return only one date while the user is
    selecting a date range. In that case the selected date is used as
    both the start and end of the period.

    Parameters
    ----------
    selected_range : date or tuple[date, ...] or list[date]
        Value returned by Streamlit's date input.
    default_start : date
        Start date used if an unexpected empty sequence is returned.
    today : date
        Current date used as the fallback end date.

    Returns
    -------
    AnalysisPeriod
        Selected custom analysis period.

    """
    if isinstance(
        selected_range,
        (tuple, list),
    ):
        if len(selected_range) == 2:  # noqa: PLR2004
            period_start = selected_range[0]
            period_end = selected_range[1]
        elif len(selected_range) == 1:
            period_start = selected_range[0]
            period_end = selected_range[0]
        else:
            period_start = default_start
            period_end = today
    else:
        period_start = selected_range
        period_end = selected_range

    period = AnalysisPeriod(
        start=period_start,
        end=period_end,
    )

    return period


def _normalise_period(
    period: AnalysisPeriod,
    today: date,
) -> AnalysisPeriod:
    """Normalise an analysis period and exclude future dates.

    Both dates are limited to ``today`` so an entirely future period
    becomes a single-day period for today. Reversed dates are corrected
    after future dates have been removed.

    Parameters
    ----------
    period : AnalysisPeriod
        Period to normalise.
    today : date
        Latest date permitted in the resulting period.

    Returns
    -------
    AnalysisPeriod
        Normalised analysis period.

    """
    period_start = min(
        period.start,
        today,
    )
    period_end = min(
        period.end,
        today,
    )

    if period_start > period_end:
        period_start, period_end = (
            period_end,
            period_start,
        )

    normalised_period = AnalysisPeriod(
        start=period_start,
        end=period_end,
    )

    return normalised_period


def _render_period_description(
    period_option: str,
    period: AnalysisPeriod,
    today: date,
) -> None:
    """Render details of the selected analysis period.

    Parameters
    ----------
    period_option : str
        Selected sidebar period option.
    period : AnalysisPeriod
        Normalised analysis period.
    today : date
        Current dashboard date.

    """
    st.sidebar.markdown("**Selected period**")
    st.sidebar.write(f"{period.start:%d %b %Y} " f"to {period.end:%d %b %Y}")

    if period_option in WEEK_BASED_PERIODS:
        if period_option == "This week":
            current_week_start = monday_of_week(today)
            current_week_end = sunday_of_week(today)

            st.sidebar.caption(
                "Calendar week: "
                f"{current_week_start:%d %b} "
                "to "
                f"{current_week_end:%d %b %Y}. "
                "Calculations currently run "
                "through today."
            )
        else:
            st.sidebar.caption(
                "Weeks are aligned Monday to Sunday. "
                "The current incomplete week is "
                "calculated through today."
            )


def _render_data_availability(
    context: DashboardContext,
    period: AnalysisPeriod,
) -> None:
    """Render stored-data information and coverage warnings.

    Parameters
    ----------
    context : DashboardContext
        Shared dashboard state.
    period : AnalysisPeriod
        Selected analysis period.

    """
    st.sidebar.divider()

    if context.has_synced_data:
        earliest_data = context.earliest_data
        latest_data = context.latest_data

        if earliest_data is not None and latest_data is not None:
            st.sidebar.markdown("**Available data**")
            st.sidebar.write(f"{earliest_data:%d %b %Y} " f"to {latest_data:%d %b %Y}")

            if period.start < earliest_data:
                st.sidebar.warning(
                    "The selected period starts before "
                    "the earliest stored Toggl data."
                )

            if period.end > latest_data:
                st.sidebar.warning(
                    "The selected period extends beyond "
                    "the latest stored Toggl data."
                )
    else:
        st.sidebar.warning(
            "The database currently contains no "
            "synced Toggl entries. The dashboard "
            "is ready, but tracked-time charts "
            "will remain empty until entries have "
            "been imported."
        )

    st.sidebar.divider()
    st.sidebar.caption(
        "Equivalent working days are calculated "
        f"using {context.workday_hours:g} hours "
        "per day."
    )


def render_sidebar(
    context: DashboardContext,
) -> AnalysisPeriod:
    """Render the dashboard sidebar and return the selected period.

    Period presets are calculated relative to ``context.today``. Custom
    periods are normalised so reversed dates are corrected and future dates
    are excluded. Information about the locally available data range is
    displayed beneath the period controls.

    Parameters
    ----------
    context : DashboardContext
        Shared dashboard configuration and database state.

    Returns
    -------
    AnalysisPeriod
        Inclusive date range selected for dashboard analysis.

    Raises
    ------
    ValueError
        If an unsupported period option is returned or an invalid
        ``Last N weeks`` period is requested.

    """
    st.sidebar.header("Period")

    period_option = st.sidebar.selectbox(
        "Analysis period",
        PERIOD_OPTIONS,
        index=1,
    )

    if period_option == "Last N weeks":
        number_of_weeks = int(
            st.sidebar.number_input(
                "Number of weeks",
                min_value=1,
                max_value=104,
                value=4,
                step=1,
            )
        )

        selected_period = _preset_period(
            period_option=period_option,
            today=context.today,
            number_of_weeks=number_of_weeks,
        )
    elif period_option == "Custom dates":
        default_start = _default_custom_start(context)

        selected_range = st.sidebar.date_input(
            "Dates",
            value=(
                default_start,
                context.today,
            ),
        )

        selected_period = _custom_period(
            selected_range=selected_range,
            default_start=default_start,
            today=context.today,
        )
    else:
        selected_period = _preset_period(
            period_option=period_option,
            today=context.today,
        )

    analysis_period = _normalise_period(
        period=selected_period,
        today=context.today,
    )

    _render_period_description(
        period_option=period_option,
        period=analysis_period,
        today=context.today,
    )

    _render_data_availability(
        context=context,
        period=analysis_period,
    )

    return analysis_period
