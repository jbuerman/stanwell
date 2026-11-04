from datetime import date

import pytest

from stanwell.data_repository.projects import (
    get_projects,
    load_project_names,
)


def insert_time_entry(
    connection,
    *,
    entry_id: int,
    project_name: str | None,
    start_utc: str,
    duration_seconds: int,
) -> None:
    """Insert a time entry for project repository tests."""
    connection.execute(
        """
        INSERT INTO time_entries (
            id,
            project_name,
            start_utc,
            stop_utc,
            duration_seconds,
            raw_json,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry_id,
            project_name,
            start_utc,
            start_utc,
            duration_seconds,
            "{}",
            "2026-10-27T12:00:00+00:00",
        ),
    )
    connection.commit()


def test_load_project_names_returns_project_mapping(conn):
    conn.executemany(
        """
        INSERT INTO projects (
            id,
            workspace_id,
            name,
            fetched_at
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                123,
                1,
                "Project A",
                "2026-10-27T12:00:00+00:00",
            ),
            (
                456,
                1,
                "Project B",
                "2026-10-27T12:00:00+00:00",
            ),
        ],
    )
    conn.commit()

    project_names = load_project_names(conn)

    assert project_names == {
        123: "Project A",
        456: "Project B",
    }


def test_load_project_names_returns_empty_mapping(conn):
    assert load_project_names(conn) == {}


def test_get_projects_returns_project_totals(conn):
    insert_time_entry(
        conn,
        entry_id=1,
        project_name="Project A",
        start_utc="2026-10-20T09:00:00+00:00",
        duration_seconds=7200,
    )
    insert_time_entry(
        conn,
        entry_id=2,
        project_name="Project A",
        start_utc="2026-10-20T11:00:00+00:00",
        duration_seconds=3600,
    )
    insert_time_entry(
        conn,
        entry_id=3,
        project_name="Project B",
        start_utc="2026-10-21T09:00:00+00:00",
        duration_seconds=3600,
    )

    projects = get_projects(
        connection=conn,
        start_day=date(2026, 10, 20),
        end_day=date(2026, 10, 21),
        workday_hours=7.5,
    )

    assert list(projects["project"]) == [
        "Project A",
        "Project B",
    ]

    project_a = projects.iloc[0]
    project_b = projects.iloc[1]

    assert project_a["hours"] == pytest.approx(3.0)
    assert project_a["percent"] == pytest.approx(75.0)
    assert project_a["days"] == pytest.approx(0.4)

    assert project_b["hours"] == pytest.approx(1.0)
    assert project_b["percent"] == pytest.approx(25.0)
    assert project_b["days"] == pytest.approx(1.0 / 7.5)


def test_get_projects_groups_entries_without_project(conn):
    insert_time_entry(
        conn,
        entry_id=1,
        project_name=None,
        start_utc="2026-10-20T09:00:00+00:00",
        duration_seconds=3600,
    )

    projects = get_projects(
        connection=conn,
        start_day="2026-10-20",
        end_day="2026-10-20",
        workday_hours=7.5,
    )

    assert len(projects) == 1

    project = projects.iloc[0]

    assert project["project"] == "No project"
    assert project["hours"] == pytest.approx(1.0)
    assert project["percent"] == pytest.approx(100.0)


def test_get_projects_only_includes_requested_period(conn):
    insert_time_entry(
        conn,
        entry_id=1,
        project_name="Before",
        start_utc="2026-10-19T09:00:00+00:00",
        duration_seconds=3600,
    )
    insert_time_entry(
        conn,
        entry_id=2,
        project_name="Included",
        start_utc="2026-10-20T09:00:00+00:00",
        duration_seconds=3600,
    )
    insert_time_entry(
        conn,
        entry_id=3,
        project_name="After",
        start_utc="2026-10-21T09:00:00+00:00",
        duration_seconds=3600,
    )

    projects = get_projects(
        connection=conn,
        start_day=date(2026, 10, 20),
        end_day=date(2026, 10, 20),
        workday_hours=7.5,
    )

    assert list(projects["project"]) == ["Included"]


def test_get_projects_returns_expected_columns_when_empty(conn):
    projects = get_projects(
        connection=conn,
        start_day=date(2026, 10, 20),
        end_day=date(2026, 10, 21),
        workday_hours=7.5,
    )

    assert projects.empty
    assert list(projects.columns) == [
        "project",
        "hours",
        "percent",
        "days",
    ]


def test_get_projects_handles_zero_workday_hours(conn):
    insert_time_entry(
        conn,
        entry_id=1,
        project_name="Project A",
        start_utc="2026-10-20T09:00:00+00:00",
        duration_seconds=3600,
    )

    projects = get_projects(
        connection=conn,
        start_day=date(2026, 10, 20),
        end_day=date(2026, 10, 20),
        workday_hours=0.0,
    )

    assert projects.iloc[0]["days"] == pytest.approx(0.0)
