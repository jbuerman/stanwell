import argparse
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from stanwell.ui.dashboard import context


def make_dashboard_arguments(
    config_path: Path | None,
) -> argparse.Namespace:
    return argparse.Namespace(config=config_path)


def test_dashboard_context_has_synced_data():
    dashboard_context = context.DashboardContext(
        config={},
        connection=Mock(),
        workday_hours=7.5,
        today=date(2026, 10, 27),
        earliest_data=date(2026, 10, 1),
        latest_data=date(2026, 10, 27),
    )

    assert dashboard_context.has_synced_data is True


@pytest.mark.parametrize(
    (
        "earliest_data",
        "latest_data",
    ),
    [
        (
            None,
            date(2026, 10, 27),
        ),
        (
            date(2026, 10, 1),
            None,
        ),
        (
            None,
            None,
        ),
    ],
)
def test_dashboard_context_has_no_synced_data_when_range_incomplete(
    earliest_data,
    latest_data,
):
    dashboard_context = context.DashboardContext(
        config={},
        connection=Mock(),
        workday_hours=7.5,
        today=date(2026, 10, 27),
        earliest_data=earliest_data,
        latest_data=latest_data,
    )

    assert dashboard_context.has_synced_data is False


def test_get_config_path_uses_supplied_path(
    tmp_path,
):
    supplied_path = tmp_path / "config.yml"

    dashboard_arguments = make_dashboard_arguments(supplied_path)

    result = context._get_config_path(dashboard_arguments)

    assert result == supplied_path.resolve()


def test_get_stored_date_range(conn):
    conn.execute(
        """
        INSERT INTO time_entries (
            id,
            start_utc,
            duration_seconds,
            raw_json,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            1,
            "2026-10-05T10:00:00+00:00",
            3600,
            "{}",
            "2026-10-05T12:00:00+00:00",
        ),
    )

    conn.execute(
        """
        INSERT INTO time_entries (
            id,
            start_utc,
            duration_seconds,
            raw_json,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            2,
            "2026-10-20T10:00:00+00:00",
            3600,
            "{}",
            "2026-10-20T12:00:00+00:00",
        ),
    )

    conn.commit()

    earliest_data, latest_data = context._get_stored_date_range(conn)

    assert earliest_data == date(
        2026,
        10,
        5,
    )
    assert latest_data == date(
        2026,
        10,
        20,
    )


def test_get_stored_date_range_returns_none_when_empty(
    conn,
):
    earliest_data, latest_data = context._get_stored_date_range(conn)

    assert earliest_data is None
    assert latest_data is None


def test_create_dashboard_context(
    monkeypatch,
    conn,
    tmp_path,
):
    config_path = tmp_path / "config.yml"

    dashboard_arguments = make_dashboard_arguments(config_path)

    config = {
        "workday_hours": 7.5,
    }

    monkeypatch.setattr(
        context,
        "load_config_and_open_database",
        lambda path: (
            config,
            conn,
        ),
    )

    dashboard_context = context.create_dashboard_context(dashboard_arguments)

    assert dashboard_context.config == config
    assert dashboard_context.connection is conn
    assert dashboard_context.workday_hours == pytest.approx(7.5)
