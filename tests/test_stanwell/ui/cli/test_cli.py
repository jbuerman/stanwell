import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
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
    """Report quota exhaustion and direct the user to sync pending data."""
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

    result = runner.invoke(
        cli.app,
        [
            "refresh",
            "2026-10-03",
            "2026-10-04",
        ],
    )

    assert result.exit_code == 2

    assert "Refresh incomplete: Toggl API quota exhausted." in result.output

    assert "All successfully retrieved data has been saved." in result.output

    assert "Quota resets in approximately 2 minute(s)." in result.output

    assert "Run 'stanwell sync-pending' after the quota has reset." in result.output

    connection.close.assert_called_once()


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


class TestConfig:
    def test_config_opens_config_file(
        self,
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
        self,
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
        self,
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


class TestCmdSyncPending:
    def test_sync_pending_reports_when_data_is_current(
        self,
        runner,
        monkeypatch,
    ):
        """Report when there is no outstanding data to synchronise."""
        connection = Mock()

        monkeypatch.setattr(
            cli,
            "load_config_and_open_database_from_context",
            Mock(
                return_value=(
                    {},
                    connection,
                )
            ),
        )

        monkeypatch.setattr(
            cli,
            "sync_pending",
            Mock(
                return_value={
                    "status": "ok",
                    "periods_processed": 0,
                    "pending_count": 0,
                    "first_pending": None,
                    "last_pending": None,
                    "quota_resets_in_seconds": None,
                }
            ),
        )

        result = runner.invoke(
            cli.app,
            [
                "sync-pending",
            ],
        )

        assert result.exit_code == 0

        assert "All data is already synchronised." in result.output

        connection.close.assert_called_once()

    def test_sync_pending_reports_success(
        self,
        runner,
        monkeypatch,
    ):
        """Report successful processing of outstanding ranges."""
        connection = Mock()

        monkeypatch.setattr(
            cli,
            "load_config_and_open_database_from_context",
            Mock(
                return_value=(
                    {},
                    connection,
                )
            ),
        )

        monkeypatch.setattr(
            cli,
            "sync_pending",
            Mock(
                return_value={
                    "status": "ok",
                    "periods_processed": 3,
                    "pending_count": 0,
                    "first_pending": None,
                    "last_pending": None,
                    "quota_resets_in_seconds": None,
                }
            ),
        )

        result = runner.invoke(
            cli.app,
            [
                "sync-pending",
            ],
        )

        assert result.exit_code == 0

        assert "Synchronisation complete." in result.output

        assert "3 pending range(s) processed." in result.output

        connection.close.assert_called_once()

    def test_sync_pending_reports_quota_exhaustion(
        self,
        runner,
        monkeypatch,
    ):
        """Report remaining work and quota reset after exhaustion."""
        connection = Mock()

        monkeypatch.setattr(
            cli,
            "load_config_and_open_database_from_context",
            Mock(
                return_value=(
                    {},
                    connection,
                )
            ),
        )

        monkeypatch.setattr(
            cli,
            "sync_pending",
            Mock(
                return_value={
                    "status": "quota_exhausted",
                    "periods_processed": 2,
                    "pending_count": 17,
                    "first_pending": "2026-10-20",
                    "last_pending": "2026-11-05",
                    "quota_remaining": 0,
                    "quota_resets_in_seconds": 420,
                }
            ),
        )

        result = runner.invoke(
            cli.app,
            [
                "sync-pending",
            ],
        )

        assert result.exit_code == 2

        assert "Toggl quota exhausted." in result.output

        assert "All successfully retrieved data has been saved." in result.output

        assert "17 date(s) remain pending." in result.output

        assert "Pending range: " "2026-10-20 to 2026-11-05" in result.output

        assert "Quota resets in approximately " "7 minute(s)." in result.output

        assert (
            "Run 'stanwell sync-pending' again "
            "after the quota has reset." in result.output
        )

        connection.close.assert_called_once()

    def test_sync_pending_reports_failure(
        self,
        runner,
        monkeypatch,
    ):
        """Report an unexpected synchronisation error."""
        connection = Mock()

        monkeypatch.setattr(
            cli,
            "load_config_and_open_database_from_context",
            Mock(
                return_value=(
                    {},
                    connection,
                )
            ),
        )

        monkeypatch.setattr(
            cli,
            "sync_pending",
            Mock(side_effect=RuntimeError("Something went wrong.")),
        )

        result = runner.invoke(
            cli.app,
            [
                "sync-pending",
            ],
        )

        assert result.exit_code == 1

        assert "Synchronisation failed: " "Something went wrong." in result.output

        connection.close.assert_called_once()


class TestCmdInit:

    def test_init_creates_config_and_database_in_default_location(
        self,
        runner,
        monkeypatch,
        tmp_path,
    ):
        """Create config and database beneath a temporary home directory."""
        monkeypatch.setenv(
            "HOME",
            str(tmp_path),
        )

        result = runner.invoke(
            cli.app,
            ["init"],
            input="test-token\n" "123456\n" "7\n" "\n" "\n" "2025-10-01\n",
        )

        assert result.exit_code == 0

        application_directory = tmp_path / ".config" / "stanwell"

        config_path = application_directory / "config.yaml"

        database_path = application_directory / "time_tracking.db"

        assert application_directory.is_dir()
        assert config_path.is_file()
        assert database_path.is_file()

        with config_path.open(
            encoding="utf-8",
        ) as config_file:
            config = yaml.safe_load(config_file)

        assert config["toggl_api_token"] == "test-token"
        assert config["workspace_id"] == 123456
        assert config["database_path"] == "time_tracking.db"
        assert config["workday_hours"] == 7
        assert config["core_start"] == "09:00"
        assert config["core_end"] == "17:00"
        assert config["tracking_start_date"] == "2025-10-01"

        connection = sqlite3.connect(database_path)

        try:
            table_rows = connection.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """).fetchall()

            tables = {row[0] for row in table_rows}

            assert {
                "covered_days",
                "data_coverage",
                "day_exceptions",
                "exception_types",
                "projects",
                "sync_log",
                "time_entries",
                "time_entry_tags",
            } <= tables

        finally:
            connection.close()

        assert f"Configuration written to {config_path}" in result.output

        assert f"Database initialised at {database_path}" in result.output
