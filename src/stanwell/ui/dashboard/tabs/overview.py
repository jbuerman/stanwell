"""Render the main working-time overview dashboard tab.

The overview presents working-time totals for today and the selected period,
daily and weekly working-time charts and average working hours by weekday.

Data preparation is separated from Streamlit and plotting code so that the
calculation and aggregation behaviour can be tested independently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st

from stanwell.analysis.projections import prepare_week_remaining_projection
from stanwell.analysis.working_time import (
    calculate_working_time,
)
from stanwell.ui.dashboard.constants import (
    WEEKDAY_PALETTE,
)
from stanwell.ui.dashboard.context import (
    DashboardContext,
)
from stanwell.ui.dashboard.helpers import (
    numeric_sum,
)

WEEKDAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


@dataclass(frozen=True)
class WorkingTimeTotals:
    """Summarise working-time totals for a period."""

    actual_hours: float
    """Total recorded working hours."""

    expected_hours: float
    """Total expected working hours."""

    compensation_hours: float
    """Total hours taken as overtime compensation."""

    compensation_equivalent_days: float
    """Compensation expressed as configured working days."""

    balance_hours: float
    """Working-time balance after compensation adjustments."""

    equivalent_days: float
    """Recorded hours expressed as configured working days."""

    balance_equivalent_days: float
    """Working-time balance expressed as configured working days."""


def _calculate_totals(
    daily_summary: pd.DataFrame,
    workday_hours: float,
) -> WorkingTimeTotals:
    """Calculate headline working-time totals.

    Parameters
    ----------
    daily_summary : pandas.DataFrame
        Daily working-time summary.
    workday_hours : float
        Number of hours in a standard working day.

    Returns
    -------
    WorkingTimeTotals
        Calculated working-time totals.

    """
    actual_hours = numeric_sum(
        daily_summary,
        "actual_hours",
    )
    expected_hours = numeric_sum(
        daily_summary,
        "expected_hours",
    )
    compensation_hours = -numeric_sum(
        daily_summary,
        "balance_adjustment_hours",
    )
    balance_hours = numeric_sum(
        daily_summary,
        "balance_hours",
    )

    if workday_hours > 0:
        equivalent_days = actual_hours / workday_hours
        compensation_equivalent_days = compensation_hours / workday_hours
        balance_equivalent_days = balance_hours / workday_hours
    else:
        equivalent_days = math.nan
        compensation_equivalent_days = math.nan
        balance_equivalent_days = math.nan

    totals = WorkingTimeTotals(
        actual_hours=actual_hours,
        expected_hours=expected_hours,
        compensation_hours=compensation_hours,
        compensation_equivalent_days=compensation_equivalent_days,
        balance_hours=balance_hours,
        equivalent_days=equivalent_days,
        balance_equivalent_days=balance_equivalent_days,
    )

    return totals


def _prepare_daily_chart_data(
    daily_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare daily working-time data for plotting.

    Parameters
    ----------
    daily_summary : pandas.DataFrame
        Daily working-time summary.

    Returns
    -------
    pandas.DataFrame
        Copy containing normalised date and numeric columns.

    Raises
    ------
    KeyError
        If a required column is missing.

    """
    chart_data = daily_summary.copy()

    chart_data["day"] = pd.to_datetime(chart_data["day"])

    chart_data["week_start"] = pd.to_datetime(chart_data["week_start"])

    for column in (
        "actual_hours",
        "expected_hours",
        "balance_hours",
        "balance_adjustment_hours",
    ):
        chart_data[column] = pd.to_numeric(
            chart_data[column],
            errors="coerce",
        ).fillna(0.0)

    chart_data["compensation_hours"] = -chart_data["balance_adjustment_hours"]

    return chart_data


def _create_weekly_summary(
    daily_chart_data: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate daily working-time values by week.

    Parameters
    ----------
    daily_chart_data : pandas.DataFrame
        Prepared daily working-time data.

    Returns
    -------
    pandas.DataFrame
        Weekly actual, expected and balance hours.

    Raises
    ------
    KeyError
        If a required column is missing.

    """
    weekly_summary = daily_chart_data.groupby(
        "week_start",
        as_index=False,
    ).agg(
        actual_hours=(
            "actual_hours",
            "sum",
        ),
        expected_hours=(
            "expected_hours",
            "sum",
        ),
        balance_hours=(
            "balance_hours",
            "sum",
        ),
    )

    weekly_summary["week_label"] = weekly_summary["week_start"].dt.strftime("%d %b")

    return weekly_summary


def _create_weekday_summary(
    daily_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate working-time statistics by weekday.

    Parameters
    ----------
    daily_summary : pandas.DataFrame
        Daily working-time summary containing weekday and actual-hour
        values.

    Returns
    -------
    pandas.DataFrame
        Weekday average hours, standard deviation and number of days.

    Raises
    ------
    KeyError
        If ``weekday`` or ``actual_hours`` is missing.

    """
    weekday_data = daily_summary.copy()

    weekday_data["actual_hours"] = pd.to_numeric(
        weekday_data["actual_hours"],
        errors="coerce",
    ).fillna(0.0)

    weekday_summary = (
        weekday_data.groupby(
            "weekday",
            observed=False,
        )["actual_hours"]
        .agg(
            average_hours="mean",
            std_dev="std",
            days="count",
        )
        .reindex(WEEKDAY_ORDER)
        .reset_index()
    )

    weekday_summary["std_dev"] = weekday_summary["std_dev"].fillna(0.0)

    return weekday_summary


def _render_today_summary(
    context: DashboardContext,
) -> None:
    """Render headline working-time metrics for today.

    Parameters
    ----------
    context : DashboardContext
        Shared dashboard configuration and database state.

    Raises
    ------
    sqlite3.Error
        If working-time data cannot be read from the database.
    ValueError
        If stored time-entry data cannot be interpreted.

    """
    today_entries, today_summary = calculate_working_time(
        context.connection,
        context.config,
        context.today.isoformat(),
        context.today.isoformat(),
    )

    today_totals = _calculate_totals(
        daily_summary=today_summary,
        workday_hours=context.workday_hours,
    )

    st.subheader("Today")

    worked_column, required_column, balance_column = st.columns(3)

    with worked_column:
        st.metric(
            "Worked",
            f"{today_totals.actual_hours:.1f} h",
            border=True,
        )

    with required_column:
        st.metric(
            "Required",
            f"{today_totals.expected_hours:.1f} h",
            border=True,
        )

    with balance_column:
        st.metric(
            "Balance",
            f"{today_totals.balance_hours:+.1f} h",
            border=True,
        )

    if today_entries.empty:
        st.info("There are currently no synced time " "entries for today.")


def _render_period_metrics(
    period_start: date,
    period_end: date,
    totals: WorkingTimeTotals,
) -> None:
    """Render headline metrics for the selected period.

    Parameters
    ----------
    period_start : date
        First date in the selected period.
    period_end : date
        Last date in the selected period.
    totals : WorkingTimeTotals
        Calculated totals for the period.

    """
    st.divider()
    st.subheader("Selected period")

    st.caption(f"{period_start:%d %b %Y} – " f"{period_end:%d %b %Y}")

    (
        worked_column,
        worked_days_column,
        required_column,
        balance_column,
        balance_days_column,
        compensation_column,
    ) = st.columns(6)

    with worked_column:
        st.metric(
            "Worked",
            f"{totals.actual_hours:.1f} h",
            border=True,
        )

    with worked_days_column:
        st.metric(
            "Equivalent days",
            f"{totals.equivalent_days:.1f}",
            border=True,
        )

    with required_column:
        st.metric(
            "Required",
            f"{totals.expected_hours:.1f} h",
            border=True,
        )

    with balance_column:
        st.metric(
            "Balance",
            f"{totals.balance_hours:+.1f} h",
            border=True,
        )

    with balance_days_column:
        st.metric(
            "Equivalent days",
            f"{totals.balance_equivalent_days:.1f}",
            border=True,
        )

    with compensation_column:
        st.metric(
            "Compensation days",
            f"{totals.compensation_equivalent_days:.1f}",
            border=True,
        )


def _render_daily_chart(
    daily_chart_data: pd.DataFrame,
) -> None:
    """Render actual and expected daily working hours.

    Parameters
    ----------
    daily_chart_data : pandas.DataFrame
        Prepared daily working-time data.

    Raises
    ------
    KeyError
        If required plotting columns are missing.

    """
    st.markdown("#### Daily working hours")

    figure, axes = plt.subplots(figsize=(8, 4.5))

    figure.patch.set_facecolor("#fafafa")
    axes.set_facecolor("#fafafa")

    sns.lineplot(
        data=daily_chart_data,
        x="day",
        y="actual_hours",
        label="Actual",
        linewidth=2.4,
        color="#4C956C",
        ax=axes,
    )

    sns.lineplot(
        data=daily_chart_data,
        x="day",
        y="expected_hours",
        label="Required",
        linewidth=1.8,
        linestyle="--",
        color="#7B8794",
        ax=axes,
    )

    sns.lineplot(
        data=daily_chart_data,
        x="day",
        y="compensation_hours",
        label="Compensation",
        linewidth=1.8,
        linestyle="--",
        color="#C17C3A",
        ax=axes,
    )

    axes.set_xlabel("")
    axes.set_ylabel("Hours")

    axes.tick_params(
        axis="x",
        rotation=35,
    )

    axes.grid(
        axis="y",
        color="#e8e8e8",
        linewidth=0.8,
    )
    axes.grid(
        axis="x",
        visible=False,
    )

    sns.despine(
        ax=axes,
        left=False,
        bottom=True,
    )

    figure.tight_layout()

    st.pyplot(
        figure,
        width="stretch",
    )

    plt.close(figure)


def _render_weekly_balance_chart(
    weekly_summary: pd.DataFrame,
) -> None:
    """Render weekly working-time balance.

    Parameters
    ----------
    weekly_summary : pandas.DataFrame
        Weekly working-time summary.

    Raises
    ------
    KeyError
        If required plotting columns are missing.

    """
    st.markdown("#### Weekly balance")

    if weekly_summary.empty:
        st.info("No weekly data are available " "for this period.")
    else:
        colours = [
            ("#4C956C" if balance >= 0 else "#C8553D")
            for balance in weekly_summary["balance_hours"]
        ]

        figure, axes = plt.subplots(figsize=(8, 4.5))

        figure.patch.set_facecolor("#fafafa")
        axes.set_facecolor("#fafafa")

        bars = axes.bar(
            weekly_summary["week_label"],
            weekly_summary["balance_hours"],
            color=colours,
            width=0.65,
            edgecolor="none",
        )

        axes.axhline(
            0,
            color="#555555",
            linewidth=1,
        )

        axes.bar_label(
            bars,
            labels=[f"{balance:+.1f}" for balance in weekly_summary["balance_hours"]],
            padding=4,
            fontsize=9,
            color="#444444",
        )

        axes.set_xlabel("")
        axes.set_ylabel("Hours above / below requirement")

        axes.tick_params(
            axis="x",
            rotation=35,
        )

        axes.grid(
            axis="y",
            color="#e8e8e8",
            linewidth=0.8,
        )
        axes.grid(
            axis="x",
            visible=False,
        )

        sns.despine(
            ax=axes,
            left=False,
            bottom=True,
        )

        figure.tight_layout()

        st.pyplot(
            figure,
            width="stretch",
        )

        plt.close(figure)


def _render_daily_and_weekly_charts(
    daily_summary: pd.DataFrame,
) -> None:
    """Render daily working hours and weekly balance charts.

    Parameters
    ----------
    daily_summary : pandas.DataFrame
        Daily working-time summary.

    Raises
    ------
    KeyError
        If required working-time columns are missing.

    """
    has_daily_data = daily_summary.empty is False and "day" in daily_summary.columns

    if has_daily_data:
        daily_chart_data = _prepare_daily_chart_data(daily_summary)
        weekly_summary = _create_weekly_summary(daily_chart_data)

        daily_column, weekly_column = st.columns(2)

        with daily_column:
            _render_daily_chart(daily_chart_data)

        with weekly_column:
            _render_weekly_balance_chart(weekly_summary)
    else:
        st.info("There is no daily data available " "for the selected period.")


def _prepare_weekday_table(
    weekday_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare weekday statistics for display.

    Parameters
    ----------
    weekday_summary : pandas.DataFrame
        Weekday working-time summary.

    Returns
    -------
    pandas.DataFrame
        Formatted copy ready for Streamlit display.

    Raises
    ------
    KeyError
        If expected weekday-summary columns are missing.

    """
    weekday_table = weekday_summary.copy()

    weekday_table.columns = [
        "Weekday",
        "Average hours",
        "Standard deviation",
        "Days in period",
    ]

    weekday_table["Average hours"] = weekday_table["Average hours"].round(1)

    weekday_table["Standard deviation"] = weekday_table["Standard deviation"].round(1)

    return weekday_table


def _render_weekday_pattern(
    daily_summary: pd.DataFrame,
) -> None:
    """Render average working hours by weekday.

    Parameters
    ----------
    daily_summary : pandas.DataFrame
        Daily working-time summary.

    Raises
    ------
    KeyError
        If required weekday-analysis columns are missing after validation.

    """
    st.subheader("Weekday pattern")

    st.caption(
        "Average hours worked on each day of the week "
        "during the selected period. Error bars show "
        "±1 standard deviation."
    )

    has_weekday_data = (
        daily_summary.empty is False
        and "weekday" in daily_summary.columns
        and "actual_hours" in daily_summary.columns
    )

    if has_weekday_data is False:
        st.info("There is no weekday data available " "for the selected period.")
    else:
        weekday_data = daily_summary.copy()

        weekday_data["actual_hours"] = pd.to_numeric(
            weekday_data["actual_hours"],
            errors="coerce",
        ).fillna(0.0)

        weekday_summary = _create_weekday_summary(weekday_data)

        figure, axes = plt.subplots(figsize=(11, 5))

        figure.patch.set_facecolor("#fafafa")
        axes.set_facecolor("#fafafa")

        sns.barplot(
            data=weekday_data,
            x="weekday",
            y="actual_hours",
            order=WEEKDAY_ORDER,
            estimator="mean",
            errorbar="sd",
            capsize=0.12,
            hue="weekday",
            hue_order=WEEKDAY_ORDER,
            palette=WEEKDAY_PALETTE,
            legend=False,
            ax=axes,
        )

        axes.set_xlabel("")
        axes.set_ylabel("Average hours worked")

        axes.grid(
            axis="y",
            color="#e8e8e8",
            linewidth=0.8,
        )
        axes.grid(
            axis="x",
            visible=False,
        )

        axes.tick_params(
            axis="x",
            rotation=0,
        )

        sns.despine(
            ax=axes,
            bottom=True,
        )

        figure.tight_layout()

        st.pyplot(
            figure,
            width="stretch",
        )

        plt.close(figure)

        with st.expander("Weekday details"):
            weekday_table = _prepare_weekday_table(weekday_summary)

            st.dataframe(
                weekday_table,
                hide_index=True,
                width="stretch",
            )


def _render_week_remaining_projection(
    projection: pd.DataFrame,
) -> None:
    st.markdown("### Rest of this week")

    st.caption(
        "If you stopped working now, this is the average "
        "amount you would need to work on each remaining "
        "working day to meet this week's requirement."
    )

    if projection.empty:
        st.info("There are no remaining required working days " "this week.")
        return

    required_per_day = float(projection["required_hours"].iloc[0])

    total_remaining = float(projection["required_hours"].sum())

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Still required",
            f"{total_remaining:.1f} h",
            border=True,
        )

    with col2:
        st.metric(
            "Average per remaining day",
            f"{required_per_day:.1f} h",
            border=True,
        )


def render_overview(
    context: DashboardContext,
    period_start: date,
    period_end: date,
) -> pd.DataFrame:
    """Render the dashboard overview for the selected period.

    Today's working-time metrics, selected-period totals, daily and weekly
    charts and weekday patterns are rendered. The time-entry segments for
    the selected period are returned for reuse by the working-pattern tab.

    Parameters
    ----------
    context : DashboardContext
        Shared dashboard configuration and database state.
    period_start : date
        First date in the selected analysis period.
    period_end : date
        Last date in the selected analysis period.

    Returns
    -------
    pandas.DataFrame
        Time-entry segments belonging to the selected period.

    Raises
    ------
    sqlite3.Error
        If working-time data cannot be read from the database.
    ValueError
        If stored dates, timestamps or configured values cannot be
        interpreted.
    KeyError
        If working-time analysis returns data without required columns.

    """
    _render_today_summary(context)

    period_entries, daily_summary = calculate_working_time(
        context.connection,
        context.config,
        period_start.isoformat(),
        period_end.isoformat(),
    )

    this_monday = context.today - timedelta(days=context.today.weekday())

    this_sunday = this_monday + timedelta(days=6)

    _, this_week_daily = calculate_working_time(
        context.connection,
        context.config,
        this_monday.isoformat(),
        this_sunday.isoformat(),
    )

    projection = prepare_week_remaining_projection(
        this_week_daily,
        context.today,
    )

    st.divider()

    _render_week_remaining_projection(projection)

    period_totals = _calculate_totals(
        daily_summary=daily_summary,
        workday_hours=context.workday_hours,
    )

    _render_period_metrics(
        period_start=period_start,
        period_end=period_end,
        totals=period_totals,
    )

    st.divider()

    _render_daily_and_weekly_charts(daily_summary)

    st.divider()

    _render_weekday_pattern(daily_summary)

    return period_entries
