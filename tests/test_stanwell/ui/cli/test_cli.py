from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from stanwell.ui.cli import cli


@pytest.fixture
def runner():
    runner = CliRunner()

    return runner


@pytest.fixture
def mock_database():
    connection = Mock()
    config = {
        "database_path": "test.db",
        "recent_refresh_days": 7,
    }

    return config, connection


def test_callback_stores_config_path(
    runner,
    monkeypatch,
    tmp_path,
    mock_database,
):
    config_path = tmp_path / "config.yml"

    def fake_load(context):
        assert context.obj["config_path"] == config_path

        return mock_database

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        fake_load,
    )

    connection = mock_database[1]

    status_row = {
        "entry_count": 0,
        "first_date": None,
        "last_date": None,
    }

    cursor = Mock()
    cursor.fetchone.return_value = status_row
    connection.execute.return_value = cursor

    result = runner.invoke(
        cli.app,
        [
            "--config",
            str(config_path),
            "status",
        ],
    )

    assert result.exit_code == 0


def test_status_displays_database_information(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    cursor = Mock()
    cursor.fetchone.return_value = {
        "entry_count": 10,
        "first_date": "2026-10-01",
        "last_date": "2026-10-20",
    }
    connection.execute.return_value = cursor

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    result = runner.invoke(
        cli.app,
        ["status"],
    )

    assert result.exit_code == 0
    assert "Entries: 10" in result.output
    assert "First entry: 2026-10-01" in result.output
    assert "Latest entry: 2026-10-20" in result.output
    assert "Database: test.db" in result.output

    connection.close.assert_called_once()


def test_status_displays_none_for_empty_database(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    cursor = Mock()
    cursor.fetchone.return_value = {
        "entry_count": 0,
        "first_date": None,
        "last_date": None,
    }
    connection.execute.return_value = cursor

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    result = runner.invoke(
        cli.app,
        ["status"],
    )

    assert result.exit_code == 0
    assert "First entry: none" in result.output
    assert "Latest entry: none" in result.output


def test_sync_missing_success(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    monkeypatch.setattr(
        cli,
        "sync_missing",
        lambda connection, config: {
            "status": "ok",
        },
    )

    result = runner.invoke(
        cli.app,
        ["sync-missing"],
    )

    assert result.exit_code == 0
    assert "Missing-data sync complete." in result.output

    connection.close.assert_called_once()


def test_sync_missing_reports_quota_exhaustion(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    monkeypatch.setattr(
        cli,
        "sync_missing",
        lambda connection, config: {
            "status": "quota_exhausted",
            "message": "Quota exhausted.",
        },
    )

    result = runner.invoke(
        cli.app,
        ["sync-missing"],
    )

    assert result.exit_code == 0
    assert "Toggl quota exhausted." in result.output
    assert "Quota exhausted." in result.output


def test_sync_missing_failure_returns_exit_code_one(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    def fail_sync(
        connection,
        config,
    ):
        raise RuntimeError("Something failed")

    monkeypatch.setattr(
        cli,
        "sync_missing",
        fail_sync,
    )

    result = runner.invoke(
        cli.app,
        ["sync-missing"],
    )

    assert result.exit_code == 1
    assert "Sync failed: Something failed" in result.output

    connection.close.assert_called_once()


def test_refresh_recent_success(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    monkeypatch.setattr(
        cli,
        "refresh_recent",
        lambda connection, config: {
            "status": "ok",
        },
    )

    result = runner.invoke(
        cli.app,
        ["refresh-recent"],
    )

    assert result.exit_code == 0
    assert "Refreshing the last 7 days..." in result.output
    assert "Recent-data refresh complete." in result.output


def test_refresh_success(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    def fake_refresh(
        connection,
        config,
        start_day,
        end_day,
    ):
        assert start_day == "2026-10-01"
        assert end_day == "2026-10-07"

        return {
            "status": "ok",
        }

    monkeypatch.setattr(
        cli,
        "refresh_period",
        fake_refresh,
    )

    result = runner.invoke(
        cli.app,
        [
            "refresh",
            "2026-10-01",
            "2026-10-07",
        ],
    )

    assert result.exit_code == 0
    assert "Refresh complete." in result.output


def test_refresh_quota_exhaustion_returns_exit_code_two(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    monkeypatch.setattr(
        cli,
        "refresh_period",
        lambda *args, **kwargs: {
            "status": "quota_exhausted",
            "quota_resets_in_seconds": 120,
        },
    )

    monkeypatch.setattr(
        cli,
        "get_pending_refresh_days",
        lambda connection: [
            date(2026, 10, 3),
            date(2026, 10, 4),
        ],
    )

    result = runner.invoke(
        cli.app,
        [
            "refresh",
            "2026-10-01",
            "2026-10-07",
        ],
    )

    assert result.exit_code == 2
    assert "2 date(s) remain pending." in result.output
    assert "Pending range: 2026-10-03 " "to 2026-10-04" in result.output

    connection.close.assert_called_once()


def test_refresh_pending_when_nothing_is_pending(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    monkeypatch.setattr(
        cli,
        "get_pending_refresh_days",
        lambda connection: [],
    )

    result = runner.invoke(
        cli.app,
        ["refresh-pending"],
    )

    assert result.exit_code == 0
    assert "There are no pending refreshes." in result.output

    connection.close.assert_called_once()


def test_refresh_pending_success(
    runner,
    monkeypatch,
    mock_database,
):
    config, connection = mock_database

    monkeypatch.setattr(
        cli,
        "load_config_and_open_database_from_context",
        lambda context: (
            config,
            connection,
        ),
    )

    monkeypatch.setattr(
        cli,
        "get_pending_refresh_days",
        lambda connection: [
            date(2026, 10, 19),
        ],
    )

    monkeypatch.setattr(
        cli,
        "refresh_pending",
        lambda connection, config: {
            "status": "ok",
            "entries_saved": 5,
        },
    )

    result = runner.invoke(
        cli.app,
        ["refresh-pending"],
    )

    assert result.exit_code == 0
    assert "Pending refresh complete." in result.output
    assert "5 entries processed." in result.output


def test_dashboard_reports_missing_dashboard(
    runner,
    monkeypatch,
    tmp_path,
):
    missing_dashboard = tmp_path / "missing.py"

    monkeypatch.setattr(
        cli,
        "get_dashboard_path",
        lambda: missing_dashboard,
    )

    result = runner.invoke(
        cli.app,
        ["dashboard"],
    )

    assert result.exit_code == 1
    assert "Dashboard not found" in result.output


def test_dashboard_runs_streamlit(
    runner,
    monkeypatch,
    tmp_path,
):
    dashboard_path = tmp_path / "dashboard.py"
    dashboard_path.touch()

    monkeypatch.setattr(
        cli,
        "get_dashboard_path",
        lambda: dashboard_path,
    )

    completed_process = Mock(returncode=0)

    run_mock = Mock(return_value=completed_process)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        run_mock,
    )

    result = runner.invoke(
        cli.app,
        ["dashboard"],
    )

    assert result.exit_code == 0

    run_mock.assert_called_once()


def test_toggl_workspaces_uses_environment_token(
    runner,
    monkeypatch,
):
    monkeypatch.setenv(
        "TOGGL_API_TOKEN",
        "test-token",
    )

    client = Mock()
    client.fetch_workspaces.return_value = [
        {
            "id": 123,
            "name": "Test workspace",
        }
    ]

    client_class = Mock(return_value=client)

    monkeypatch.setattr(
        cli,
        "TogglClient",
        client_class,
    )

    result = runner.invoke(
        cli.app,
        ["toggl-workspaces"],
    )

    assert result.exit_code == 0
    assert "Test workspace: 123" in result.output

    client_class.assert_called_once_with(
        api_token="test-token",
        workspace_id=None,
    )


def test_config_opens_config_file(
    runner,
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "timezone: Europe/London\n",
        encoding="utf-8",
    )

    run_mock = Mock(
        return_value=SimpleNamespace(
            returncode=0,
        )
    )
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        run_mock,
    )

    result = runner.invoke(
        cli.app,
        [
            "--config",
            str(config_path),
            "config",
        ],
    )

    assert result.exit_code == 0

    run_mock.assert_called_once_with(
        [
            "xdg-open",
            str(config_path),
        ],
        check=False,
    )


def test_config_rejects_missing_config_file(
    runner,
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "missing.yaml"

    run_mock = Mock()
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        run_mock,
    )

    result = runner.invoke(
        cli.app,
        [
            "--config",
            str(config_path),
            "config",
        ],
    )

    assert result.exit_code == 1
    assert "Configuration file not found" in result.output
    assert str(config_path) in result.output

    run_mock.assert_not_called()


def test_config_returns_xdg_open_exit_code(
    runner,
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "timezone: Europe/London\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        Mock(
            return_value=SimpleNamespace(
                returncode=1,
            )
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "--config",
            str(config_path),
            "config",
        ],
    )

    assert result.exit_code == 1
