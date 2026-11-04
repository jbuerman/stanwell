from importlib.machinery import ModuleSpec
from pathlib import Path
from unittest.mock import Mock

import pytest
import typer

from stanwell.ui.cli import cli_util


def test_get_dashboard_path(monkeypatch, tmp_path):
    dashboard_path = tmp_path / "stanwell" / "ui" / "dashboard" / "dashboard.py"

    module_spec = ModuleSpec(
        name="stanwell.ui.dashboard.dashboard",
        loader=None,
        origin=str(dashboard_path),
    )

    monkeypatch.setattr(
        cli_util,
        "find_spec",
        lambda name: module_spec,
    )

    result = cli_util.get_dashboard_path()

    assert result == dashboard_path.resolve()


def test_get_dashboard_path_raises_when_module_not_found(
    monkeypatch,
):
    monkeypatch.setattr(
        cli_util,
        "find_spec",
        lambda name: None,
    )

    with pytest.raises(
        RuntimeError,
        match="Could not locate the dashboard module",
    ):
        cli_util.get_dashboard_path()


def test_get_dashboard_path_raises_when_module_has_no_origin(
    monkeypatch,
):
    module_spec = ModuleSpec(
        name="stanwell.ui.dashboard.dashboard",
        loader=None,
    )

    monkeypatch.setattr(
        cli_util,
        "find_spec",
        lambda name: module_spec,
    )

    with pytest.raises(
        RuntimeError,
        match="Could not locate the dashboard module",
    ):
        cli_util.get_dashboard_path()


def test_load_config_and_open_database_from_context(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.yml"

    expected_config = {
        "database_path": "test.db",
    }
    expected_connection = Mock()

    context = Mock(spec=typer.Context)
    context.obj = {
        "config_path": config_path,
    }

    def fake_load_config_and_open_database(path):
        assert path == config_path

        return (
            expected_config,
            expected_connection,
        )

    monkeypatch.setattr(
        cli_util,
        "load_config_and_open_database",
        fake_load_config_and_open_database,
    )

    config, connection = cli_util.load_config_and_open_database_from_context(context)

    assert config == expected_config
    assert connection is expected_connection


def test_load_config_and_open_database_from_context_converts_path(
    monkeypatch,
):
    expected_connection = Mock()

    context = Mock(spec=typer.Context)
    context.obj = {
        "config_path": "somewhere/config.yml",
    }

    received_path = None

    def fake_load_config_and_open_database(path):
        nonlocal received_path

        received_path = path

        return (
            {},
            expected_connection,
        )

    monkeypatch.setattr(
        cli_util,
        "load_config_and_open_database",
        fake_load_config_and_open_database,
    )

    cli_util.load_config_and_open_database_from_context(context)

    assert received_path == Path("somewhere/config.yml")
