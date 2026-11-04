"""Render project allocation for the selected dashboard period.

Project totals are loaded from the project repository and displayed as a
percentage-based bar chart together with a detailed table of recorded hours
and equivalent working days.
"""

from __future__ import annotations

from datetime import date
from typing import cast

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st
from matplotlib.patches import Rectangle

from stanwell.data_repository.projects import (
    get_projects,
)
from stanwell.ui.dashboard.context import (
    DashboardContext,
)
from stanwell.ui.dashboard.helpers import (
    numeric_sum,
)


def _prepare_project_table(
    projects: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare project data for display in the detail table.

    Parameters
    ----------
    projects : pandas.DataFrame
        Project allocation data containing project name, percentage,
        recorded hours and equivalent working days.

    Returns
    -------
    pandas.DataFrame
        Formatted copy of the project data with display-oriented column
        names and values rounded to one decimal place.

    Raises
    ------
    KeyError
        If one or more required project columns are missing.

    """
    project_table = projects[
        [
            "project",
            "percent",
            "hours",
            "days",
        ]
    ].copy()

    project_table.columns = [
        "Project",
        "Share (%)",
        "Hours",
        "Equivalent days",
    ]

    project_table["Share (%)"] = project_table["Share (%)"].round(1)
    project_table["Hours"] = project_table["Hours"].round(1)
    project_table["Equivalent days"] = project_table["Equivalent days"].round(1)

    return project_table


def _render_project_chart(
    projects: pd.DataFrame,
) -> None:
    """Render project allocation as a horizontal bar chart.

    Projects are ordered by descending percentage of recorded time. Each
    bar is labelled with its percentage, recorded hours and equivalent
    working days.

    Parameters
    ----------
    projects : pandas.DataFrame
        Project allocation data containing ``project``, ``percent``,
        ``hours`` and ``days`` columns.

    Raises
    ------
    KeyError
        If one or more required project columns are missing.

    """
    project_chart_data = projects.sort_values(
        by="percent",
        ascending=False,
    ).copy()

    figure_height = max(
        4.0,
        len(project_chart_data) * 0.55,
    )

    figure, axes = plt.subplots(
        figsize=(
            11.0,
            figure_height,
        )
    )

    figure.patch.set_facecolor("#fafafa")
    axes.set_facecolor("#fafafa")

    project_palette = sns.color_palette(
        "Set2",
        n_colors=len(project_chart_data),
    )

    sns.barplot(
        data=project_chart_data,
        y="project",
        x="percent",
        hue="project",
        palette=project_palette,
        legend=False,
        edgecolor="none",
        ax=axes,
    )

    for patch, (_, project_row) in zip(
        axes.patches,
        project_chart_data.iterrows(),
        strict=True,
    ):
        project_bar = cast(
            Rectangle,
            patch,
        )

        percentage = float(project_row["percent"])
        hours = float(project_row["hours"])
        equivalent_days = float(project_row["days"])

        axes.text(
            (project_bar.get_width() + 0.6),
            (project_bar.get_y() + project_bar.get_height() / 2),
            (
                f"{percentage:.1f}%"
                f"   ·   {hours:.1f} h"
                f"   ·   "
                f"{equivalent_days:.1f} days"
            ),
            va="center",
            ha="left",
            fontsize=10,
            color="#404040",
        )

    axes.set_xlabel("")
    axes.set_ylabel("")
    axes.set_xticks([])

    axes.tick_params(
        axis="y",
        length=0,
        labelsize=10,
    )

    maximum_percent = float(project_chart_data["percent"].max())

    if pd.notna(maximum_percent) and maximum_percent > 0:
        axes.set_xlim(
            0,
            maximum_percent * 1.7,
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


def _render_project_table(
    projects: pd.DataFrame,
) -> None:
    """Render detailed project allocation data.

    Parameters
    ----------
    projects : pandas.DataFrame
        Project allocation data.

    Raises
    ------
    KeyError
        If one or more required project columns are missing.

    """
    project_table = _prepare_project_table(projects)

    with st.expander("Project details"):
        st.dataframe(
            project_table,
            width="stretch",
            hide_index=True,
        )


def render_projects(
    context: DashboardContext,
    period_start: date,
    period_end: date,
) -> None:
    """Render project allocation for the selected period.

    Project totals are retrieved from the local database. When recorded
    project time is available, the function displays a percentage-based
    allocation chart and a detailed project table. Otherwise an
    informational message is displayed.

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
        If project data cannot be read from the database.
    KeyError
        If project data do not contain the columns required for rendering.

    """
    st.divider()
    st.subheader("Where my time goes")

    projects = get_projects(
        connection=context.connection,
        start_day=period_start,
        end_day=period_end,
        workday_hours=context.workday_hours,
    )

    total_project_hours = numeric_sum(
        projects,
        "hours",
    )

    has_project_data = projects.empty is False and total_project_hours > 0

    if has_project_data:
        _render_project_chart(projects)

        _render_project_table(projects)
    else:
        st.info("There is no project data available " "for the selected period.")
