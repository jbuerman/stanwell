"""Render tag-based working-time analysis for the dashboard.

The tab shows the share of recorded working time associated with selected
tags, how those shares change over time and how selected tags overlap on
individual time entries.

Tag shares are independent because one time entry may contain multiple tags.
The overlap analysis groups entries by their exact combination of selected
tags so each entry contributes only once to that visualisation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, cast

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st
from matplotlib.axes import Axes

from stanwell.analysis.tag_analysis import (
    get_available_tags,
    get_tag_analysis,
    has_tag,
    tag_trend_delta,
)
from stanwell.ui.dashboard.context import (
    DashboardContext,
)

MAX_TAG_COMBINATIONS = 12


def _calculate_tag_totals(
    tag_entries: pd.DataFrame,
    selected_tags: Sequence[str],
    workday_hours: float,
) -> pd.DataFrame:
    """Calculate totals for each selected tag.

    Tag percentages are calculated independently against all recorded hours
    in the period. Percentages may therefore sum to more than 100 per cent
    when entries contain multiple selected tags.

    Parameters
    ----------
    tag_entries : pandas.DataFrame
        Per-entry tag-analysis data.
    selected_tags : Sequence[str]
        Tags selected for analysis.
    workday_hours : float
        Number of hours in a standard working day.

    Returns
    -------
    pandas.DataFrame
        Tag name, recorded hours, percentage of total working time and
        equivalent working days.

    Raises
    ------
    KeyError
        If required tag-analysis columns are missing.

    """
    total_hours = float(
        pd.to_numeric(
            tag_entries["hours"],
            errors="coerce",
        )
        .fillna(0.0)
        .sum()
    )

    tag_total_rows: list[dict[str, str | float]] = []

    for tag in selected_tags:
        tag_mask = tag_entries["selected_tags"].apply(
            has_tag,
            args=(tag,),
        )

        tag_hours = float(
            pd.to_numeric(
                tag_entries.loc[
                    tag_mask,
                    "hours",
                ],
                errors="coerce",
            )
            .fillna(0.0)
            .sum()
        )

        if total_hours > 0:
            percentage = tag_hours / total_hours * 100.0
        else:
            percentage = 0.0

        if workday_hours > 0:
            equivalent_days = tag_hours / workday_hours
        else:
            equivalent_days = 0.0

        tag_total_rows.append(
            {
                "tag": tag,
                "hours": tag_hours,
                "percent": percentage,
                "days": equivalent_days,
            }
        )

    tag_totals = pd.DataFrame(
        tag_total_rows,
        columns=[
            "tag",
            "hours",
            "percent",
            "days",
        ],
    )

    return tag_totals


def _create_tag_trend(
    tag_entries: pd.DataFrame,
    selected_tags: Sequence[str],
) -> pd.DataFrame:
    """Calculate weekly hours and shares for selected tags.

    Parameters
    ----------
    tag_entries : pandas.DataFrame
        Per-entry tag-analysis data.
    selected_tags : Sequence[str]
        Tags selected for analysis.

    Returns
    -------
    pandas.DataFrame
        Weekly hours and percentage share for each selected tag.

    Raises
    ------
    KeyError
        If required tag-analysis columns are missing.

    """
    weekly_total_hours = (
        tag_entries.groupby("week_start")["hours"].sum().rename("total_hours")
    )

    trend_rows: list[dict[str, Any]] = []

    for tag in selected_tags:
        tagged_entries = tag_entries[
            tag_entries["selected_tags"].apply(
                has_tag,
                args=(tag,),
            )
        ]

        weekly_tag_hours = tagged_entries.groupby("week_start")["hours"].sum()

        for (
            week_start,
            total_hours,
        ) in weekly_total_hours.items():
            tag_hours = float(
                weekly_tag_hours.get(
                    week_start,
                    0.0,
                )
            )
            numeric_total_hours = float(total_hours)

            if numeric_total_hours > 0:
                share = tag_hours / numeric_total_hours * 100.0
            else:
                share = 0.0

            trend_rows.append(
                {
                    "week_start": week_start,
                    "tag": tag,
                    "hours": tag_hours,
                    "share": share,
                }
            )

    trend_data = pd.DataFrame(
        trend_rows,
        columns=[
            "week_start",
            "tag",
            "hours",
            "share",
        ],
    )

    return trend_data


def _create_tag_combinations(
    tag_entries: pd.DataFrame,
    selected_tags: Sequence[str],
) -> pd.DataFrame:
    """Aggregate hours by exact combination of selected tags.

    Entries without any selected tags are excluded. The order of tags in
    each combination follows ``selected_tags`` so combinations have a stable
    and predictable representation.

    Parameters
    ----------
    tag_entries : pandas.DataFrame
        Per-entry tag-analysis data.
    selected_tags : Sequence[str]
        Tags selected for overlap analysis.

    Returns
    -------
    pandas.DataFrame
        Exact tag combinations and their aggregated recorded hours.

    Raises
    ------
    KeyError
        If ``selected_tags`` or ``hours`` is missing from ``tag_entries``.

    """
    overlap_entries = tag_entries[
        tag_entries["selected_tags"].apply(lambda tags: len(tags) > 0)
    ].copy()

    combinations = pd.DataFrame(
        columns=[
            "combination",
            "hours",
        ]
    )

    if overlap_entries.empty is False:
        overlap_entries["combination"] = overlap_entries["selected_tags"].apply(
            lambda tags: tuple(tag for tag in selected_tags if tag in tags)
        )

        combinations = (
            overlap_entries.groupby(
                "combination",
                as_index=False,
            )
            .agg(
                hours=(
                    "hours",
                    "sum",
                )
            )
            .sort_values(
                by="hours",
                ascending=False,
            )
            .reset_index(drop=True)
        )

    return combinations


def _render_tag_cards(
    tag_entries: pd.DataFrame,
    tag_totals: pd.DataFrame,
) -> None:
    """Render headline metrics for selected tags.

    Parameters
    ----------
    tag_entries : pandas.DataFrame
        Per-entry tag-analysis data used to calculate tag trends.
    tag_totals : pandas.DataFrame
        Aggregate values for the selected tags.

    Raises
    ------
    KeyError
        If required tag-total or tag-analysis columns are missing.

    """
    st.markdown("### Over period")

    number_of_columns = min(
        len(tag_totals),
        4,
    )

    card_columns = st.columns(number_of_columns)

    for card_index, (
        _,
        tag_row,
    ) in enumerate(tag_totals.iterrows()):
        tag = str(tag_row["tag"])

        trend_change = tag_trend_delta(
            tag_entries,
            tag,
        )

        if trend_change is None:
            trend_text = None
        else:
            trend_text = f"{trend_change:+.1f} pp/week"

        column_index = card_index % len(card_columns)

        with card_columns[column_index]:
            st.metric(
                label=tag,
                value=(f"{float(tag_row['percent']):.1f}%"),
                delta=trend_text,
                delta_color="normal",
                border=True,
            )

            st.caption(
                f"{float(tag_row['hours']):.1f} h "
                "· "
                f"{float(tag_row['days']):.1f} days"
            )

    st.caption(
        "Percentages are independent. They may "
        "sum to more than 100% because tags can "
        "overlap."
    )


def _render_tag_trend(
    trend_data: pd.DataFrame,
) -> None:
    """Render weekly selected-tag trends.

    The user may switch between percentage share of weekly working time and
    absolute recorded hours.

    Parameters
    ----------
    trend_data : pandas.DataFrame
        Weekly tag hours and percentage shares.

    Raises
    ------
    KeyError
        If required trend columns are missing.

    """
    st.markdown("### Over time")

    measure = st.radio(
        "Measure",
        [
            "Share of working time",
            "Hours",
        ],
        horizontal=True,
    )

    if measure == "Share of working time":
        value_column = "share"
        value_label = "Share of weekly working time (%)"
    else:
        value_column = "hours"
        value_label = "Hours"

    figure, axes = plt.subplots(figsize=(12.0, 5.0))

    figure.patch.set_facecolor("#fafafa")
    axes.set_facecolor("#fafafa")

    sns.lineplot(
        data=trend_data,
        x="week_start",
        y=value_column,
        hue="tag",
        marker="o",
        linewidth=2.0,
        ax=axes,
    )

    axes.set_xlabel("")
    axes.set_ylabel(value_label)

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


def _render_combination_bars(
    axes: Axes,
    combinations: pd.DataFrame,
) -> None:
    """Render hours for each exact tag combination.

    Parameters
    ----------
    axes : matplotlib.axes.Axes
        Axes on which to draw the bars.
    combinations : pandas.DataFrame
        Tag combinations and aggregated hours.

    Raises
    ------
    KeyError
        If the ``hours`` column is missing.

    """
    number_of_combinations = len(combinations)

    x_positions = range(number_of_combinations)

    bars = axes.bar(
        x_positions,
        combinations["hours"],
        color="#4C956C",
        width=0.7,
    )

    maximum_hours = float(combinations["hours"].max())

    for bar, hours in zip(
        bars,
        combinations["hours"],
        strict=True,
    ):
        numeric_hours = float(hours)

        axes.text(
            (bar.get_x() + bar.get_width() / 2),
            (bar.get_height() + maximum_hours * 0.02),
            f"{numeric_hours:.1f} h",
            ha="center",
            va="bottom",
            fontsize=9,
            color="#404040",
        )

    axes.set_ylabel("Hours")
    axes.set_xticks([])

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


def _render_combination_matrix(
    axes: Axes,
    combinations: pd.DataFrame,
    selected_tags: Sequence[str],
) -> None:
    """Render tag membership for each exact combination.

    Parameters
    ----------
    axes : matplotlib.axes.Axes
        Axes on which to draw the membership matrix.
    combinations : pandas.DataFrame
        Tag combinations to display.
    selected_tags : Sequence[str]
        Selected tags in display order.

    Raises
    ------
    KeyError
        If the ``combination`` column is missing.

    """
    number_of_combinations = len(combinations)
    number_of_tags = len(selected_tags)

    for combination_index, combination in enumerate(combinations["combination"]):
        active_tag_rows: list[int] = []

        typed_combination = cast(
            tuple[str, ...],
            combination,
        )

        for tag_index, tag in enumerate(selected_tags):
            is_active = tag in typed_combination

            if is_active:
                colour = "#4C956C"
                marker_size = 70
                active_tag_rows.append(tag_index)
            else:
                colour = "#D8D8D8"
                marker_size = 35

            axes.scatter(
                combination_index,
                tag_index,
                s=marker_size,
                color=colour,
                zorder=3,
            )

        if len(active_tag_rows) > 1:
            axes.plot(
                [
                    combination_index,
                    combination_index,
                ],
                [
                    min(active_tag_rows),
                    max(active_tag_rows),
                ],
                color="#4C956C",
                linewidth=2,
                zorder=2,
            )

    axes.set_yticks(range(number_of_tags))
    axes.set_yticklabels(selected_tags)
    axes.set_xticks(range(number_of_combinations))
    axes.set_xticklabels([])

    axes.tick_params(
        axis="both",
        length=0,
    )

    axes.set_ylim(
        number_of_tags - 0.5,
        -0.5,
    )

    axes.grid(visible=False)

    sns.despine(
        ax=axes,
        left=True,
        bottom=True,
    )


def _render_tag_overlaps(
    combinations: pd.DataFrame,
    selected_tags: Sequence[str],
    total_combination_count: int,
) -> None:
    """Render exact overlaps between selected tags.

    Parameters
    ----------
    combinations : pandas.DataFrame
        Tag combinations ordered by recorded hours.
    selected_tags : Sequence[str]
        Selected tags in display order.
    total_combination_count : int
        Number of combinations before the display limit is applied.

    Raises
    ------
    KeyError
        If required combination columns are missing.

    """
    st.markdown("### Tag overlaps")

    st.caption(
        "Bars show hours spent on each exact "
        "combination of the selected tags. Each "
        "time entry contributes to one combination "
        "only, so time is not double-counted."
    )

    if combinations.empty:
        st.info("None of the selected tags occur " "during this period.")
    else:
        displayed_combinations = combinations.head(MAX_TAG_COMBINATIONS)

        number_of_combinations = len(displayed_combinations)
        number_of_tags = len(selected_tags)

        figure_width = max(
            10.0,
            number_of_combinations * 0.8,
        )
        figure_height = max(
            5.0,
            3.0 + number_of_tags * 0.45,
        )

        figure = plt.figure(
            figsize=(
                figure_width,
                figure_height,
            ),
            layout="constrained",
        )

        figure.patch.set_facecolor("#fafafa")

        grid = figure.add_gridspec(
            2,
            1,
            height_ratios=[
                3.0,
                max(
                    1.5,
                    number_of_tags * 0.45,
                ),
            ],
            hspace=0.05,
        )

        bar_axes = figure.add_subplot(grid[0])

        matrix_axes = figure.add_subplot(
            grid[1],
            sharex=bar_axes,
        )

        _render_combination_bars(
            axes=bar_axes,
            combinations=(displayed_combinations),
        )

        _render_combination_matrix(
            axes=matrix_axes,
            combinations=(displayed_combinations),
            selected_tags=selected_tags,
        )

        st.pyplot(
            figure,
            width="stretch",
        )

        plt.close(figure)

        if total_combination_count > MAX_TAG_COMBINATIONS:
            st.caption(
                f"Showing the " f"{MAX_TAG_COMBINATIONS} " "largest tag combinations."
            )


def render_tag_balances(
    context: DashboardContext,
    period_start: date,
    period_end: date,
) -> None:
    """Render tag-based analysis for the selected period.

    Available tags are loaded from the local database and the user may select
    one or more for analysis. The selected tags are shown as period totals,
    weekly trends and exact overlap combinations.

    Parameters
    ----------
    context : DashboardContext
        Shared dashboard configuration and database state.
    period_start : date
        First date in the selected analysis period.
    period_end : date
        Last date in the selected analysis period.

    Raises
    ------
    sqlite3.Error
        If tags or time-entry data cannot be read from the database.
    ValueError
        If stored timestamps or configuration values cannot be interpreted.
    KeyError
        If tag-analysis data do not contain required columns.

    """
    st.header("Tag analysis")

    st.caption(
        "Explore how different activities contribute "
        "to your working time and how that changes "
        "over time. Tag shares may overlap because "
        "a time entry can have multiple tags."
    )

    available_tags = get_available_tags(context.connection)

    if len(available_tags) == 0:
        st.info("No tags are currently stored " "in the database.")
    else:
        selected_tags = st.multiselect(
            "Tags to analyse",
            options=available_tags,
            placeholder="Choose tags...",
        )

        if len(selected_tags) == 0:
            st.info("Select one or more tags " "to analyse.")
        else:
            tag_entries = get_tag_analysis(
                connection=context.connection,
                config=context.config,
                start_date=period_start,
                end_date=period_end,
                selected_tags=selected_tags,
            )

            if tag_entries.empty:
                st.info("No time entries are available " "for the selected period.")
            else:
                tag_totals = _calculate_tag_totals(
                    tag_entries=tag_entries,
                    selected_tags=selected_tags,
                    workday_hours=(context.workday_hours),
                )

                _render_tag_cards(
                    tag_entries=tag_entries,
                    tag_totals=tag_totals,
                )

                trend_data = _create_tag_trend(
                    tag_entries=tag_entries,
                    selected_tags=selected_tags,
                )

                _render_tag_trend(trend_data)

                combinations = _create_tag_combinations(
                    tag_entries=tag_entries,
                    selected_tags=selected_tags,
                )

                _render_tag_overlaps(
                    combinations=combinations,
                    selected_tags=selected_tags,
                    total_combination_count=(len(combinations)),
                )
