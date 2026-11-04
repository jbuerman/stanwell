"""Load application configuration and open the configured database.

Configuration values are read from a YAML file and supplemented with
application defaults where values are not provided. Database paths relative
to the configuration file are resolved from the configuration file's
directory.
"""

import sqlite3
from pathlib import Path
from typing import Any

import yaml

from stanwell.data_repository.db import connect_db

DATABASE_PATH = "toggl_time.db"
TIMEZONE = "Europe/London"
WORKDAY_HOURS = 7.5
WORKING_DAYS = [0, 1, 2, 3, 4]
CORE_START = "10:00"
CORE_END = "16:00"
RECENT_REFRESH_DAYS = 7
API_CHUNK_DAYS = 30


def load_config(
    path: str | Path = "config.yml",
) -> dict[str, Any]:
    """Load application configuration from a YAML file.

    Values not specified in the configuration file are populated with
    application defaults.

    Parameters
    ----------
    path : str or Path, default="config.yml"
        Path to the YAML configuration file.

    Returns
    -------
    dict[str, Any]
        Configuration values loaded from the file and supplemented with
        defaults.

    """
    with open(path, encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}

    defaults = {
        "database_path": DATABASE_PATH,
        "timezone": TIMEZONE,
        "workday_hours": WORKDAY_HOURS,
        "working_days": WORKING_DAYS,
        "core_start": CORE_START,
        "core_end": CORE_END,
        "recent_refresh_days": RECENT_REFRESH_DAYS,
        "api_chunk_days": API_CHUNK_DAYS,
    }

    for key, default_value in defaults.items():
        config.setdefault(
            key,
            default_value,
        )

    return config


def load_config_and_open_database(
    config_path: Path,
) -> tuple[dict[str, Any], sqlite3.Connection]:
    """Load configuration and open its configured SQLite database.

    Relative database paths are interpreted relative to the directory
    containing the configuration file.

    Parameters
    ----------
    config_path : Path
        Path to the YAML configuration file.

    Returns
    -------
    tuple[dict[str, Any], sqlite3.Connection]
        Loaded configuration and an open connection to the configured
        database.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist.

    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file '{config_path}' not found.")

    config = load_config(config_path)

    database_path = Path(config["database_path"]).expanduser()

    if not database_path.is_absolute():
        database_path = config_path.parent / database_path

    connection = connect_db(database_path)

    return config, connection
