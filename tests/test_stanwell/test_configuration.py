from pathlib import Path

import pytest
import yaml

from stanwell.configuration import (
    API_CHUNK_DAYS,
    CORE_END,
    CORE_START,
    DATABASE_PATH,
    RECENT_REFRESH_DAYS,
    TIMEZONE,
    WORKDAY_HOURS,
    WORKING_DAYS,
    load_config,
    load_config_and_open_database,
)


@pytest.fixture
def default_config():
    return {
        "database_path": DATABASE_PATH,
        "timezone": TIMEZONE,
        "workday_hours": WORKDAY_HOURS,
        "working_days": WORKING_DAYS,
        "core_start": CORE_START,
        "core_end": CORE_END,
        "recent_refresh_days": RECENT_REFRESH_DAYS,
        "api_chunk_days": API_CHUNK_DAYS,
    }


def test_load_config_uses_defaults(tmp_path, default_config):
    config_path = tmp_path / "config.yml"
    config_path.write_text("", encoding="utf-8")

    config = load_config(config_path)

    assert config == default_config


def test_load_config_overrides_defaults(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "timezone": "Europe/Berlin",
                "workday_hours": 8.0,
                "working_days": [0, 1, 2, 3],
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["timezone"] == "Europe/Berlin"
    assert config["workday_hours"] == 8.0
    assert config["working_days"] == [0, 1, 2, 3]


def test_load_config_keeps_defaults_for_unspecified_values(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "timezone: Europe/Berlin\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["timezone"] == "Europe/Berlin"
    assert config["database_path"] == DATABASE_PATH
    assert config["workday_hours"] == WORKDAY_HOURS
    assert config["working_days"] == WORKING_DAYS
    assert config["core_start"] == CORE_START
    assert config["core_end"] == CORE_END
    assert config["recent_refresh_days"] == RECENT_REFRESH_DAYS
    assert config["api_chunk_days"] == API_CHUNK_DAYS


def test_load_config_preserves_additional_values(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "some_other_setting: hello\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["some_other_setting"] == "hello"


def test_load_config_raises_if_file_does_not_exist(tmp_path):
    config_path = tmp_path / "missing.yml"

    with pytest.raises(FileNotFoundError):
        load_config(config_path)


def test_load_config_and_open_database_raises_if_config_missing(tmp_path):
    config_path = tmp_path / "missing.yml"

    with pytest.raises(
        FileNotFoundError,
        match="Config file .* not found",
    ):
        load_config_and_open_database(config_path)


def test_load_config_and_open_database_resolves_relative_database_path(
    tmp_path,
):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "database_path: data.db\n",
        encoding="utf-8",
    )

    config, connection = load_config_and_open_database(config_path)

    try:
        database_path = connection.execute("PRAGMA database_list").fetchone()["file"]

        assert Path(database_path) == tmp_path / "data.db"
        assert config["database_path"] == "data.db"
    finally:
        connection.close()


def test_load_config_and_open_database_uses_absolute_database_path(
    tmp_path,
):
    database_path = tmp_path / "absolute.db"
    config_path = tmp_path / "config.yml"

    config_path.write_text(
        yaml.safe_dump(
            {
                "database_path": str(database_path),
            }
        ),
        encoding="utf-8",
    )

    _, connection = load_config_and_open_database(config_path)

    try:
        actual_path = connection.execute("PRAGMA database_list").fetchone()["file"]

        assert Path(actual_path) == database_path
    finally:
        connection.close()
