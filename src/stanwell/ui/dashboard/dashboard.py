"""Compose and run the Streamlit working-time dashboard."""

from __future__ import annotations

import seaborn as sns
import streamlit as st

from stanwell.ui.dashboard.context import (
    create_dashboard_context,
)
from stanwell.ui.dashboard.helpers import (
    parse_dashboard_args,
)
from stanwell.ui.dashboard.sidebar import (
    render_sidebar,
)
from stanwell.ui.dashboard.tabs.overview import (
    render_overview,
)
from stanwell.ui.dashboard.tabs.projects import (
    render_projects,
)
from stanwell.ui.dashboard.tabs.tag_balances import (
    render_tag_balances,
)
from stanwell.ui.dashboard.tabs.work_patterns import (
    render_work_patterns,
)


def main() -> None:
    """Configure and render the Streamlit dashboard."""
    st.set_page_config(
        page_title="Time dashboard",
        page_icon="⏱",
        layout="wide",
    )

    sns.set_theme(
        style="white",
        context="notebook",
        font_scale=1.05,
    )

    st.title("Time dashboard")
    st.caption("Working time, balance and project allocation")

    dashboard_arguments = parse_dashboard_args()

    dashboard_context = create_dashboard_context(dashboard_arguments)

    period = render_sidebar(dashboard_context)

    overview_tab, project_tab, patterns_tab, tags_tab = st.tabs(
        [
            "Overview",
            "Projects",
            "Working patterns",
            "Tag balance",
        ]
    )

    with overview_tab:
        period_entries = render_overview(
            dashboard_context,
            period.start,
            period.end,
        )

    with project_tab:
        render_projects(
            dashboard_context,
            period.start,
            period.end,
        )

    with patterns_tab:
        render_work_patterns(
            dashboard_context,
            period.start,
            period.end,
            period_entries,
        )

    with tags_tab:
        render_tag_balances(
            dashboard_context,
            period.start,
            period.end,
        )


if __name__ == "__main__":
    main()
