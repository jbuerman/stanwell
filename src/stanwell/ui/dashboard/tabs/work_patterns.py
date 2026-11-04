"""Render working-pattern analysis for the dashboard.

The tab summarises work outside configured core hours, weekend work and work
on designated days off. It also presents longer-term smoothed working-pattern
scores and weekly trends.

Analysis is delegated to the working-pattern and scoring modules. This module
prepares their results for presentation and renders them with Streamlit.
"""

from __future__ import annotations

from datetime import date
from typing import cast

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st
from dateutil.relativedelta import relativedelta
from matplotlib.patches import Rectangle

from stanwell.analysis.scoring import (
    add_smoothed_working_scores,
)
from stanwell.analysis.working_patterns import (
    WorkingPattern,
    get_weekly_working_patterns,
    get_working_pattern,
)
from stanwell.analysis.working_time import (
    calculate_working_time,
)
from stanwell.ui.dashboard.constants import (
    WORKING_PATTERN_PALETTE,
)
from stanwell.ui.dashboard.context import (
    DashboardContext,
)

SCORE_COLUMNS = [
    "weekend_score",
    "core_hours_score",
    "day_off_score",
    "overall_score",
]

SCORE_LABELS = {
    "weekend_score": "Weekend",
    "core_hours_score": "Core hours",
    "day_off_score": "Day off / holiday",
    "overall_score": "Overall",
}

SCORE_PALETTE = {
    "Weekend": "#E07A5F",
    "Core hours": "#F2B134",
    "Day off / holiday": "#B56576",
    "Overall": "#2563EB",
}

UNDESIRABLE_SHARE_COLUMNS = [
    "weekend_share",
    "outside_core_share",
    "non_working_day_share",
]

UNDESIRABLE_SHARE_LABELS = {
    "weekend_share": "Weekend",
    "outside_core_share": "Outside core hours",
    "non_working_day_share": "Day off / holiday",
}

UNDESIRABLE_SHARE_PALETTE = {
    "Weekend": "#E07A5F",
    "Outside core hours": "#F2B134",
    "Day off / holiday": "#B56576",
}


def _load_long_term_scores(
    context: DashboardContext,
) -> pd.DataFrame:
    """Load and score the previous year of working-pattern data.

    Parameters
    ----------
    context : DashboardContext
        Shared dashboard configuration and database state.

    Returns
    -------
    pandas.DataFrame
        Weekly working-pattern data with raw quality measures and smoothed
        scores.

    Raises
    ------
    sqlite3.Error
        If working-time or exception data cannot be read from the database.
    ValueError
        If stored timestamps or configuration values cannot be interpreted.
    KeyError
        If analysis data do not contain required columns.

    """
    score_start = context.today - relativedelta(years=1)

    score_entries, _ = calculate_working_time(
        context.connection,
        context.config,
        score_start.isoformat(),
        context.today.isoformat(),
    )

    weekly_score_data = get_weekly_working_patterns(
        entries=score_entries,
        start_date=score_start,
        end_date=context.today,
        connection=context.connection,
    )

    weekly_score_data = add_smoothed_working_scores(
        weekly_score_data,
        half_life_weeks=6.0,
        minimum_week_hours=1.0,
    )

    return weekly_score_data


def _prepare_pattern_data(
    pattern: WorkingPattern,
) -> pd.DataFrame:
    """Prepare selected-period working-pattern data for plotting.

    Categories with no recorded time are excluded. Percentage values are
    calculated from the remaining mutually exclusive categories.

    Parameters
    ----------
    pattern : WorkingPattern
        Selected-period working-pattern summary.

    Returns
    -------
    pandas.DataFrame
        Working-pattern categories with recorded hours and percentages.

    """
    pattern_data = pd.DataFrame(
        {
            "category": [
                "Normal working hours",
                "Outside core hours",
                "Weekend",
                "Day off / holiday",
            ],
            "hours": [
                pattern["normal_hours"],
                pattern["outside_core_hours"],
                pattern["weekend_hours"],
                pattern["non_working_day_hours"],
            ],
        }
    )

    pattern_data = pattern_data[pattern_data["hours"] > 0].copy()

    total_hours = float(pattern_data["hours"].sum())

    if total_hours > 0:
        pattern_data["percent"] = pattern_data["hours"] / total_hours * 100.0
    else:
        pattern_data["percent"] = 0.0

    return pattern_data


def _prepare_score_trend(
    valid_scores: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare smoothed scores for long-term trend plotting.

    Parameters
    ----------
    valid_scores : pandas.DataFrame
        Weekly score data containing complete smoothed scores.

    Returns
    -------
    pandas.DataFrame
        Long-form score trend data.

    Raises
    ------
    KeyError
        If required score columns are missing.

    """
    score_trend = valid_scores[
        [
            "week_start",
            *SCORE_COLUMNS,
        ]
    ].melt(
        id_vars="week_start",
        var_name="measure",
        value_name="score",
    )

    score_trend["measure"] = score_trend["measure"].map(SCORE_LABELS)

    return score_trend


def _prepare_undesirable_time_trend(
    weekly_score_data: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare weekly undesirable-working-time shares for plotting.

    Share values produced by the scoring analysis are proportions between
    zero and one. They are converted to percentages for presentation.

    Parameters
    ----------
    weekly_score_data : pandas.DataFrame
        Weekly working-pattern score data.

    Returns
    -------
    pandas.DataFrame
        Long-form weekly percentage data.

    Raises
    ------
    KeyError
        If required weekly share columns are missing.

    """
    undesirable_time_trend = weekly_score_data[
        [
            "week_start",
            *UNDESIRABLE_SHARE_COLUMNS,
        ]
    ].copy()

    for column in UNDESIRABLE_SHARE_COLUMNS:
        undesirable_time_trend[column] = undesirable_time_trend[column] * 100.0

    undesirable_time_trend = undesirable_time_trend.melt(
        id_vars="week_start",
        var_name="measure",
        value_name="percent",
    )

    undesirable_time_trend["measure"] = undesirable_time_trend["measure"].map(
        UNDESIRABLE_SHARE_LABELS
    )

    return undesirable_time_trend


def _render_pattern_metrics(
    pattern: WorkingPattern,
) -> None:
    """Render headline selected-period working-pattern metrics.

    Parameters
    ----------
    pattern : WorkingPattern
        Selected-period working-pattern summary.

    """
    total_hours = pattern["total_hours"]

    outside_core_percent = pattern["outside_core_hours"] / total_hours * 100.0
    weekend_percent = pattern["weekend_hours"] / total_hours * 100.0
    non_working_day_percent = pattern["non_working_day_hours"] / total_hours * 100.0

    (
        outside_core_column,
        weekend_column,
        day_off_column,
    ) = st.columns(3)

    with outside_core_column:
        st.metric(
            "Outside core hours",
            (f"{pattern['outside_core_hours']:.1f} h"),
            (f"{outside_core_percent:.1f}% " "of working time"),
            border=True,
        )

    with weekend_column:
        st.metric(
            "Weekend work",
            (f"{pattern['weekend_hours']:.1f} h"),
            (f"{weekend_percent:.1f}% " "of working time"),
            border=True,
        )

    with day_off_column:
        st.metric(
            "Work on days off",
            (f"{pattern['non_working_day_hours']:.1f} h"),
            (f"{non_working_day_percent:.1f}% " "of working time"),
            border=True,
        )


def _render_pattern_breakdown(
    pattern: WorkingPattern,
) -> None:
    """Render the selected-period working-pattern breakdown.

    Parameters
    ----------
    pattern : WorkingPattern
        Selected-period working-pattern summary.

    """
    st.markdown("### Where the working time fell")

    pattern_data = _prepare_pattern_data(pattern)

    if pattern_data.empty is False:
        figure, axes = plt.subplots(figsize=(10.0, 4.5))

        figure.patch.set_facecolor("#fafafa")
        axes.set_facecolor("#fafafa")

        sns.barplot(
            data=pattern_data,
            y="category",
            x="percent",
            hue="category",
            palette=WORKING_PATTERN_PALETTE,
            legend=False,
            ax=axes,
        )

        for patch, (_, pattern_row) in zip(
            axes.patches,
            pattern_data.iterrows(),
            strict=True,
        ):
            pattern_bar = cast(
                Rectangle,
                patch,
            )

            percent = float(pattern_row["percent"])
            hours = float(pattern_row["hours"])

            axes.text(
                (pattern_bar.get_width() + 0.5),
                (pattern_bar.get_y() + pattern_bar.get_height() / 2),
                (f"{percent:.1f}%" f"   ·   {hours:.1f} h"),
                va="center",
                fontsize=10,
                color="#404040",
            )

        axes.set_xlabel("")
        axes.set_ylabel("")
        axes.set_xticks([])

        axes.tick_params(
            axis="y",
            length=0,
        )

        maximum_percent = float(pattern_data["percent"].max())

        if maximum_percent > 0:
            axes.set_xlim(
                0,
                maximum_percent * 1.35,
            )

        sns.despine(
            ax=axes,
            left=True,
            bottom=True,
        )

        figure.tight_layout()

        st.pyplot(
            figure,
            width="stretch",
        )

        plt.close(figure)


def _render_latest_scores(
    valid_scores: pd.DataFrame,
) -> None:
    """Render the latest available smoothed working-pattern scores.

    Parameters
    ----------
    valid_scores : pandas.DataFrame
        Weekly data containing complete score values.

    Raises
    ------
    KeyError
        If required score columns are missing.

    """
    latest_score = valid_scores.iloc[-1]

    (
        weekend_column,
        core_hours_column,
        day_off_column,
        overall_column,
    ) = st.columns(4)

    with weekend_column:
        st.metric(
            "Weekend score",
            (f"{latest_score['weekend_score']:.0f}%"),
            help=("Higher is better. Sustained " "weekend work reduces this score."),
            border=True,
        )

    with core_hours_column:
        st.metric(
            "Core-hours score",
            (f"{latest_score['core_hours_score']:.0f}%"),
            help=(
                "Higher is better. Weekday work "
                "outside configured core hours "
                "reduces this score."
            ),
            border=True,
        )

    with day_off_column:
        st.metric(
            "Day-off score",
            (f"{latest_score['day_off_score']:.0f}%"),
            help=(
                "Higher is better. Work on annual "
                "leave, public holidays, closure "
                "days or overtime compensation "
                "days reduces this score."
            ),
            border=True,
        )

    with overall_column:
        st.metric(
            "Overall score",
            (f"{latest_score['overall_score']:.0f}%"),
            help=(
                "Combines weekend work, weekday "
                "outside-core work and work on "
                "designated days off."
            ),
            border=True,
        )


def _render_score_trend(
    valid_scores: pd.DataFrame,
) -> None:
    """Render smoothed working-pattern scores over time.

    Parameters
    ----------
    valid_scores : pandas.DataFrame
        Weekly data containing complete smoothed scores.

    Raises
    ------
    KeyError
        If required score columns are missing.

    """
    st.markdown("### Score over time")

    score_trend = _prepare_score_trend(valid_scores)

    figure, axes = plt.subplots(figsize=(12.0, 5.0))

    figure.patch.set_facecolor("#fafafa")
    axes.set_facecolor("#fafafa")

    sns.lineplot(
        data=score_trend,
        x="week_start",
        y="score",
        hue="measure",
        style="measure",
        markers=True,
        linewidth=2.2,
        palette=SCORE_PALETTE,
        ax=axes,
    )

    axes.set_ylim(
        0,
        100,
    )
    axes.set_xlabel("")
    axes.set_ylabel("Score")

    axes.axhline(
        100,
        color="#d8d8d8",
        linewidth=0.8,
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

    axes.legend(
        title=None,
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
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


def _render_long_term_scores(
    weekly_score_data: pd.DataFrame,
) -> None:
    """Render long-term working-pattern scores.

    Parameters
    ----------
    weekly_score_data : pandas.DataFrame
        Weekly working-pattern data with smoothed score columns.

    Raises
    ------
    KeyError
        If required score columns are missing.

    """
    st.markdown("### Long-term working pattern")
    st.caption(
        "Scores use a six-week half-life. "
        "Recent weeks matter more, but one unusual "
        "week does not reset the longer-term pattern."
    )

    valid_scores = weekly_score_data.dropna(subset=SCORE_COLUMNS)

    if valid_scores.empty:
        st.info(
            "There is not yet enough synced data "
            "to calculate a working-pattern score."
        )
    else:
        _render_latest_scores(valid_scores)

        _render_score_trend(valid_scores)


def _render_undesirable_time_trend(
    weekly_score_data: pd.DataFrame,
) -> None:
    """Render weekly undesirable-working-time percentages.

    Parameters
    ----------
    weekly_score_data : pandas.DataFrame
        Weekly working-pattern score data.

    Raises
    ------
    KeyError
        If required weekly share columns are missing.

    """
    st.markdown("### Weekly undesirable working time")

    if weekly_score_data.empty:
        st.info(
            "There is not yet enough synced data " "to show weekly working-time trends."
        )
    else:
        undesirable_time_trend = _prepare_undesirable_time_trend(weekly_score_data)

        figure, axes = plt.subplots(figsize=(12.0, 4.5))

        figure.patch.set_facecolor("#fafafa")
        axes.set_facecolor("#fafafa")

        sns.lineplot(
            data=undesirable_time_trend,
            x="week_start",
            y="percent",
            hue="measure",
            markers=True,
            linewidth=1.8,
            palette=UNDESIRABLE_SHARE_PALETTE,
            ax=axes,
        )

        axes.set_xlabel("")
        axes.set_ylabel("Share of weekly working time (%)")

        axes.legend(
            title=None,
            frameon=False,
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
            bottom=True,
        )

        figure.tight_layout()

        st.pyplot(
            figure,
            width="stretch",
        )

        plt.close(figure)


def _load_long_term_balance(
    context: DashboardContext,
) -> pd.DataFrame:
    """Load daily working-time data for the previous year.

    Parameters
    ----------
    context : DashboardContext
        Shared dashboard configuration and database state.

    Returns
    -------
    pandas.DataFrame
        Daily working-time summaries for the previous year.

    """
    balance_start = context.today - relativedelta(years=1)

    _, daily_summary = calculate_working_time(
        context.connection,
        context.config,
        balance_start.isoformat(),
        context.today.isoformat(),
    )

    return daily_summary


def _prepare_weekly_balance_history(
    daily_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare weekly balance components and cumulative balance.

    Parameters
    ----------
    daily_summary : pandas.DataFrame
        Daily working-time summary.

    Returns
    -------
    pandas.DataFrame
        Weekly overtime, shortfall, compensation and cumulative balance.

    """
    balance_data = daily_summary.copy()

    balance_data["week_start"] = pd.to_datetime(balance_data["week_start"])

    for column in (
        "actual_hours",
        "expected_hours",
        "balance_adjustment_hours",
    ):
        balance_data[column] = pd.to_numeric(
            balance_data[column],
            errors="coerce",
        ).fillna(0.0)

    worked_balance = balance_data["actual_hours"] - balance_data["expected_hours"]

    balance_data["overtime_hours"] = worked_balance.clip(lower=0.0)
    balance_data["shortfall_hours"] = worked_balance.clip(upper=0.0)
    balance_data["compensation_hours"] = balance_data["balance_adjustment_hours"]

    weekly_balance = (
        balance_data.groupby(
            "week_start",
            as_index=False,
        )
        .agg(
            overtime_hours=(
                "overtime_hours",
                "sum",
            ),
            shortfall_hours=(
                "shortfall_hours",
                "sum",
            ),
            compensation_hours=(
                "compensation_hours",
                "sum",
            ),
        )
        .sort_values("week_start")
        .reset_index(drop=True)
    )

    weekly_balance["weekly_balance_hours"] = (
        weekly_balance["overtime_hours"]
        + weekly_balance["shortfall_hours"]
        + weekly_balance["compensation_hours"]
    )

    weekly_balance["cumulative_balance_hours"] = weekly_balance[
        "weekly_balance_hours"
    ].cumsum()

    return weekly_balance


def _render_balance_trend(
    weekly_balance: pd.DataFrame,
) -> None:
    """Render weekly balance components and cumulative balance.

    Parameters
    ----------
    weekly_balance : pandas.DataFrame
        Weekly balance components and cumulative balance.

    """
    st.markdown("### Working-time balance over time")

    if weekly_balance.empty:
        st.info(
            "There is not yet enough synced data "
            "to show the working-time balance trend."
        )
        return

    figure, balance_axes = plt.subplots(figsize=(12.0, 5.0))
    figure.patch.set_facecolor("#fafafa")
    balance_axes.set_facecolor("#fafafa")

    change_axes = balance_axes.twinx()

    change_axes.bar(
        weekly_balance["week_start"],
        weekly_balance["overtime_hours"],
        width=5.0,
        color="#4C956C",
        alpha=0.80,
        label="Overtime",
    )

    change_axes.bar(
        weekly_balance["week_start"],
        weekly_balance["shortfall_hours"],
        width=5.0,
        color="#C8553D",
        alpha=0.80,
        label="Shortfall",
    )

    change_axes.bar(
        weekly_balance["week_start"],
        weekly_balance["compensation_hours"],
        bottom=weekly_balance["shortfall_hours"],
        width=5.0,
        color="#D6A419",
        alpha=0.85,
        label="Compensation",
    )

    balance_axes.plot(
        weekly_balance["week_start"],
        weekly_balance["cumulative_balance_hours"],
        color="#34495E",
        linewidth=2.4,
        marker="o",
        markersize=3.5,
        label="Running balance",
        zorder=4,
    )

    change_axes.axhline(
        0.0,
        color="#555555",
        linewidth=1.0,
    )

    balance_axes.set_xlabel("")
    balance_axes.set_ylabel("Running balance (hours)")
    change_axes.set_ylabel("Weekly change (hours)")

    balance_axes.grid(
        axis="y",
        color="#e8e8e8",
        linewidth=0.8,
    )
    balance_axes.grid(
        axis="x",
        visible=False,
    )
    change_axes.grid(False)

    line_handles, line_labels = balance_axes.get_legend_handles_labels()
    bar_handles, bar_labels = change_axes.get_legend_handles_labels()

    balance_axes.legend(
        line_handles + bar_handles,
        line_labels + bar_labels,
        title=None,
        frameon=False,
        ncol=4,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
    )

    sns.despine(
        ax=balance_axes,
        bottom=True,
    )

    figure.tight_layout()

    st.pyplot(
        figure,
        width="stretch",
    )
    plt.close(figure)


def _render_long_term_balance(
    context: DashboardContext,
) -> None:
    """Render the long-term weekly working-time balance."""
    daily_summary = _load_long_term_balance(context)

    if daily_summary.empty:
        st.info(
            "There is not yet enough synced data "
            "to show the working-time balance trend."
        )
        return

    weekly_balance = _prepare_weekly_balance_history(daily_summary)
    _render_balance_trend(weekly_balance)


def render_work_patterns(
    context: DashboardContext,
    period_start: date,
    period_end: date,
    period_entries: pd.DataFrame,
) -> None:
    """Render working-pattern analysis for the selected period.

    Selected-period entries are classified into normal work, work outside
    core hours, weekend work and work on designated days off. A one-year
    history is also loaded to calculate smoothed long-term scores and weekly
    trends.

    Parameters
    ----------
    context : DashboardContext
        Shared dashboard configuration and database state.
    period_start : date
        First date in the selected analysis period.
    period_end : date
        Last date in the selected analysis period.
    period_entries : pandas.DataFrame
        Time-entry segments belonging to the selected period.

    Raises
    ------
    sqlite3.Error
        If working-time or exception data cannot be read from the database.
    ValueError
        If stored timestamps or configuration values cannot be interpreted.
    KeyError
        If analysis results do not contain required columns.

    """
    st.header("Working patterns")

    core_start = context.config["core_start"]
    core_end = context.config["core_end"]

    st.caption(
        f"Core hours: {core_start}–{core_end} "
        "· Selected period: "
        f"{period_start:%d %b %Y} to "
        f"{period_end:%d %b %Y}"
    )

    pattern = get_working_pattern(
        entries=period_entries,
        start_date=period_start,
        end_date=period_end,
        connection=context.connection,
    )

    total_hours = pattern["total_hours"]

    if total_hours > 0:
        _render_pattern_metrics(pattern)

        _render_pattern_breakdown(pattern)
    else:
        st.info("There is no synced working-time " "data for the selected period.")

    weekly_score_data = _load_long_term_scores(context)

    _render_long_term_scores(weekly_score_data)

    _render_undesirable_time_trend(weekly_score_data)

    _render_long_term_balance(context)
