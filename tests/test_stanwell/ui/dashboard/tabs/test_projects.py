from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from stanwell.ui.dashboard.tabs import (
    projects,
)


def test_prepare_project_table():
    project_data = pd.DataFrame(
        {
            "project": [
                "Project A",
                "Project B",
            ],
            "percent": [
                66.666,
                33.334,
            ],
            "hours": [
                10.456,
                5.123,
            ],
            "days": [
                1.394,
                0.683,
            ],
        }
    )

    result = projects._prepare_project_table(project_data)

    assert list(result.columns) == [
        "Project",
        "Share (%)",
        "Hours",
        "Equivalent days",
    ]

    assert list(result["Project"]) == [
        "Project A",
        "Project B",
    ]

    assert list(result["Share (%)"]) == pytest.approx(
        [
            66.7,
            33.3,
        ]
    )

    assert list(result["Hours"]) == pytest.approx(
        [
            10.5,
            5.1,
        ]
    )

    assert list(result["Equivalent days"]) == pytest.approx(
        [
            1.4,
            0.7,
        ]
    )


def test_render_projects_requests_selected_period(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        workday_hours=7.5,
    )

    project_data = pd.DataFrame(
        {
            "project": ["Project A"],
            "percent": [100.0],
            "hours": [7.5],
            "days": [1.0],
        }
    )

    get_projects_mock = Mock(return_value=project_data)

    render_chart_mock = Mock()
    render_table_mock = Mock()

    monkeypatch.setattr(
        projects,
        "get_projects",
        get_projects_mock,
    )
    monkeypatch.setattr(
        projects,
        "_render_project_chart",
        render_chart_mock,
    )
    monkeypatch.setattr(
        projects,
        "_render_project_table",
        render_table_mock,
    )
    monkeypatch.setattr(
        projects.st,
        "divider",
        Mock(),
    )
    monkeypatch.setattr(
        projects.st,
        "subheader",
        Mock(),
    )

    projects.render_projects(
        context=context,
        period_start=date(
            2026,
            10,
            20,
        ),
        period_end=date(
            2026,
            10,
            27,
        ),
    )

    get_projects_mock.assert_called_once_with(
        connection=context.connection,
        start_day=date(
            2026,
            10,
            20,
        ),
        end_day=date(
            2026,
            10,
            27,
        ),
        workday_hours=7.5,
    )

    render_chart_mock.assert_called_once_with(project_data)

    render_table_mock.assert_called_once_with(project_data)


def test_render_projects_reports_empty_data(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        workday_hours=7.5,
    )

    empty_projects = pd.DataFrame(
        columns=[
            "project",
            "hours",
            "percent",
            "days",
        ]
    )

    monkeypatch.setattr(
        projects,
        "get_projects",
        Mock(return_value=empty_projects),
    )

    info_mock = Mock()

    monkeypatch.setattr(
        projects.st,
        "divider",
        Mock(),
    )
    monkeypatch.setattr(
        projects.st,
        "subheader",
        Mock(),
    )
    monkeypatch.setattr(
        projects.st,
        "info",
        info_mock,
    )

    render_chart_mock = Mock()
    render_table_mock = Mock()

    monkeypatch.setattr(
        projects,
        "_render_project_chart",
        render_chart_mock,
    )
    monkeypatch.setattr(
        projects,
        "_render_project_table",
        render_table_mock,
    )

    projects.render_projects(
        context=context,
        period_start=date(
            2026,
            10,
            20,
        ),
        period_end=date(
            2026,
            10,
            27,
        ),
    )

    info_mock.assert_called_once_with(
        "There is no project data available " "for the selected period."
    )

    render_chart_mock.assert_not_called()
    render_table_mock.assert_not_called()


def test_render_projects_reports_zero_hours_as_no_data(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        workday_hours=7.5,
    )

    project_data = pd.DataFrame(
        {
            "project": ["Project A"],
            "hours": [0.0],
            "percent": [0.0],
            "days": [0.0],
        }
    )

    monkeypatch.setattr(
        projects,
        "get_projects",
        Mock(return_value=project_data),
    )

    info_mock = Mock()

    monkeypatch.setattr(
        projects.st,
        "divider",
        Mock(),
    )
    monkeypatch.setattr(
        projects.st,
        "subheader",
        Mock(),
    )
    monkeypatch.setattr(
        projects.st,
        "info",
        info_mock,
    )

    render_chart_mock = Mock()
    render_table_mock = Mock()

    monkeypatch.setattr(
        projects,
        "_render_project_chart",
        render_chart_mock,
    )
    monkeypatch.setattr(
        projects,
        "_render_project_table",
        render_table_mock,
    )

    projects.render_projects(
        context=context,
        period_start=date(
            2026,
            10,
            20,
        ),
        period_end=date(
            2026,
            10,
            27,
        ),
    )

    info_mock.assert_called_once()

    render_chart_mock.assert_not_called()
    render_table_mock.assert_not_called()


def test_render_project_table_uses_prepared_table(
    monkeypatch,
):
    project_data = pd.DataFrame(
        {
            "project": ["Project A"],
            "percent": [100.0],
            "hours": [7.5],
            "days": [1.0],
        }
    )

    prepared_table = pd.DataFrame(
        {
            "Project": ["Project A"],
        }
    )

    monkeypatch.setattr(
        projects,
        "_prepare_project_table",
        Mock(return_value=prepared_table),
    )

    dataframe_mock = Mock()

    monkeypatch.setattr(
        projects.st,
        "dataframe",
        dataframe_mock,
    )

    expander = Mock()
    expander.__enter__ = Mock(return_value=expander)
    expander.__exit__ = Mock(return_value=False)

    monkeypatch.setattr(
        projects.st,
        "expander",
        Mock(return_value=expander),
    )

    projects._render_project_table(project_data)

    dataframe_mock.assert_called_once_with(
        prepared_table,
        width="stretch",
        hide_index=True,
    )
