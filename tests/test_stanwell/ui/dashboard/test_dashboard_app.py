"""Headless integration tests for the complete Streamlit dashboard."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import yaml
from streamlit.testing.v1 import AppTest

from stanwell.data_repository.database_schema import (
    initialise_database,
)
from stanwell.data_repository.db import (
    connect_db,
)


def _run_dashboard(
    config_path: str,
) -> None:
    """Run the dashboard with a specified configuration file.

    Parameters
    ----------
    config_path : str
        Path to the dashboard configuration file.
    """
    import sys  # noqa: PLC0415

    from stanwell.ui.dashboard.dashboard import (  # noqa: PLC0415
        main,
    )

    sys.argv = [
        "dashboard.py",
        "--config",
        config_path,
    ]

    main()


def _insert_dashboard_test_data(
    connection: sqlite3.Connection,
    entry_day: date,
) -> None:
    """Insert representative dashboard data.

    The inserted entry contains a project and two tags so the projects,
    working-pattern and tag-analysis tabs all have usable data.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the test database.
    entry_day : date
        Date on which the test entry should occur.
    """
    connection.execute(
        """
        INSERT INTO projects (
            id,
            workspace_id,
            name,
            active,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            100,
            1,
            "Dashboard test project",
            1,
            f"{entry_day}T13:00:00+00:00",
        ),
    )

    connection.execute(
        """
        INSERT INTO time_entries (
            id,
            workspace_id,
            project_id,
            project_name,
            description,
            start_utc,
            stop_utc,
            duration_seconds,
            tags_json,
            billable,
            raw_json,
            fetched_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        """,
        (
            1,
            1,
            100,
            "Dashboard test project",
            "Dashboard integration test",
            f"{entry_day}T10:00:00+00:00",
            f"{entry_day}T12:00:00+00:00",
            7200,
            '["development", "research"]',
            0,
            "{}",
            f"{entry_day}T13:00:00+00:00",
        ),
    )

    connection.executemany(
        """
        INSERT INTO time_entry_tags (
            time_entry_id,
            tag
        )
        VALUES (?, ?)
        """,
        [
            (
                1,
                "development",
            ),
            (
                1,
                "research",
            ),
        ],
    )

    connection.commit()


def _create_dashboard_config(
    config_path: Path,
    database_path: Path,
    entry_day: date,
) -> None:
    """Create a complete dashboard test configuration.

    Parameters
    ----------
    config_path : Path
        Path at which to write the configuration.
    database_path : Path
        Path to the test database.
    entry_day : date
        First date covered by the test configuration.
    """
    config = {
        "database_path": str(database_path),
        "timezone": "Europe/London",
        "workday_hours": 7.5,
        "working_days": [
            0,
            1,
            2,
            3,
            4,
        ],
        "core_start": "10:00",
        "core_end": "16:00",
        "recent_refresh_days": 7,
        "api_chunk_days": 30,
        "tracking_start_date": (entry_day.isoformat()),
    }

    config_path.write_text(
        yaml.safe_dump(
            config,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _exception_messages(
    dashboard: AppTest,
) -> list[str]:
    """Return exception messages produced by an AppTest run.

    Parameters
    ----------
    dashboard : AppTest
        Completed dashboard test run.

    Returns
    -------
    list[str]
        Rendered exception messages.
    """
    messages = [str(exception.value) for exception in dashboard.exception]

    return messages


def test_dashboard_runs_with_real_database(
    tmp_path: Path,
) -> None:
    """Run the complete dashboard without a browser.

    This test exercises the dashboard entry point, configuration loading,
    database context, sidebar, overview, projects, working patterns and
    initial tag-analysis state using a real temporary SQLite database.
    """
    database_path = tmp_path / "dashboard.db"
    config_path = tmp_path / "config.yml"

    entry_day = date.today()

    connection = connect_db(database_path)
    initialise_database(connection)
    _insert_dashboard_test_data(
        connection,
        entry_day,
    )
    connection.close()

    _create_dashboard_config(
        config_path=config_path,
        database_path=database_path,
        entry_day=entry_day,
    )

    dashboard = AppTest.from_function(
        _run_dashboard,
        args=(str(config_path),),
        default_timeout=15,
    ).run()

    assert len(dashboard.exception) == 0, _exception_messages(dashboard)

    assert len(dashboard.title) == 1
    assert dashboard.title[0].value == "Time dashboard"

    tab_labels = [tab.label for tab in dashboard.tabs]

    assert tab_labels == [
        "Overview",
        "Projects",
        "Working patterns",
        "Tag balance",
    ]

    rendered_subheaders = {subheader.value for subheader in dashboard.subheader}

    assert "Today" in rendered_subheaders
    assert "Selected period" in rendered_subheaders
    assert "Where my time goes" in rendered_subheaders

    rendered_headers = {header.value for header in dashboard.header}

    assert "Working patterns" in rendered_headers
    assert "Tag analysis" in rendered_headers

    assert len(dashboard.multiselect) == 1

    assert set(dashboard.multiselect[0].options) == {
        "development",
        "research",
    }


def test_dashboard_tag_analysis_runs_after_selection(
    tmp_path: Path,
) -> None:
    """Exercise tag-analysis rendering through its Streamlit widget."""
    database_path = tmp_path / "dashboard.db"
    config_path = tmp_path / "config.yml"

    entry_day = date.today()

    connection = connect_db(database_path)
    initialise_database(connection)
    _insert_dashboard_test_data(
        connection,
        entry_day,
    )
    connection.close()

    _create_dashboard_config(
        config_path=config_path,
        database_path=database_path,
        entry_day=entry_day,
    )

    dashboard = AppTest.from_function(
        _run_dashboard,
        args=(str(config_path),),
        default_timeout=15,
    ).run()

    assert len(dashboard.exception) == 0, _exception_messages(dashboard)

    dashboard.multiselect[0].set_value(
        [
            "development",
            "research",
        ]
    )

    dashboard.run()

    assert len(dashboard.exception) == 0, _exception_messages(dashboard)

    rendered_markdown = {markdown.value for markdown in dashboard.markdown}

    assert "### Over period" in rendered_markdown
    assert "### Over time" in rendered_markdown
    assert "### Tag overlaps" in rendered_markdown

    metric_labels = {metric.label for metric in dashboard.metric}

    assert "development" in metric_labels
    assert "research" in metric_labels
