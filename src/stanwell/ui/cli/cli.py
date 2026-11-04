"""Define the command-line interface for Stanwell.

The CLI provides commands for initial setup, Toggl synchronisation,
database status and launching the Streamlit dashboard. Commands primarily
coordinate configuration, database and Toggl services; application logic
remains in the corresponding lower-level modules.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from stanwell.data_repository.data_coverage import (
    get_pending_refresh_days,
)
from stanwell.data_repository.database_schema import (
    initialise_database,
)
from stanwell.data_repository.db import connect_db, sync_exceptions
from stanwell.toggl.client import TogglClient
from stanwell.toggl.sync import (
    refresh_pending,
    refresh_period,
    refresh_recent,
    sync_missing,
)
from stanwell.ui.cli.cli_util import (
    get_dashboard_path,
    load_config_and_open_database_from_context,
)

app = typer.Typer(
    name="stanwell",
    help=(
        "Track working time, maintain local Toggl data "
        "and monitor healthy working patterns."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
)

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "stanwell" / "config.yaml"


@app.callback()
def main_callback(
    context: typer.Context,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to the configuration file.",
        ),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Store CLI-wide configuration in the Typer context.

    Parameters
    ----------
    context : typer.Context
        Typer context shared with subcommands.
    config : Path
        Path to the application configuration file.

    """
    context.ensure_object(dict)
    context.obj["config_path"] = config


@app.command(
    "init",
    help="Initialise Stanwell.",
)
def cmd_init(
    context: typer.Context,
) -> None:
    """Create the application configuration and local database.

    The command interactively collects the required Toggl and working-time
    settings before writing the configuration and initialising the SQLite
    database.

    Parameters
    ----------
    context : typer.Context
        Typer context containing the configuration path.

    """
    config_path: Path = context.obj["config_path"]

    setup_cancelled = False

    if config_path.exists():
        overwrite = typer.confirm(f"{config_path} already exists. Overwrite it?")

        if overwrite is False:
            setup_cancelled = True

    if setup_cancelled:
        typer.echo("Setup cancelled.")
    else:
        typer.echo("Stanwell setup")
        typer.echo()

        toggl_token = typer.prompt(
            "Toggl API token",
            hide_input=True,
        )

        workspace_id = typer.prompt(
            "Toggl workspace ID",
            type=int,
        )

        workday_hours = typer.prompt(
            "Hours in a standard working day",
            default=7,
            type=float,
        )

        core_start = typer.prompt(
            "Core hours start",
            default="09:00",
        )

        core_end = typer.prompt(
            "Core hours end",
            default="17:00",
        )

        tracking_start_date = typer.prompt(
            "Start tracking from",
            default=str(date.today()),
        )

        database_path = config_path.parent / "time_tracking.db"

        config = {
            "toggl_api_token": toggl_token,
            "workspace_id": workspace_id,
            "database_path": str(database_path),
            "workday_hours": workday_hours,
            "core_start": core_start,
            "core_end": core_end,
            "tracking_start_date": (tracking_start_date),
        }

        config_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with config_path.open(
            "w",
            encoding="utf-8",
        ) as config_file:
            yaml.safe_dump(
                config,
                config_file,
                sort_keys=False,
            )

        connection = connect_db(database_path)
        initialise_database(connection)
        connection.close()

        typer.echo()
        typer.echo(f"Configuration written to " f"{config_path}")
        typer.echo(f"Database initialised at " f"{database_path}")

    if setup_cancelled:
        raise typer.Exit()


@app.command(
    "sync-missing",
    help=("Download Toggl data for dates " "not yet stored locally."),
)
def cmd_sync_missing(
    context: typer.Context,
) -> None:
    """Download periods not yet covered by the local database.

    Parameters
    ----------
    context : typer.Context
        Typer context containing the configuration path.

    """
    config, connection = load_config_and_open_database_from_context(context)

    try:
        typer.echo("Checking for missing Toggl data...")

        result = sync_missing(
            connection,
            config,
        )

        if result["status"] == "quota_exhausted":
            typer.secho(
                "Toggl quota exhausted.",
                fg=typer.colors.YELLOW,
                bold=True,
            )
            typer.echo(
                result.get(
                    "message",
                    ("All data retrieved before " "the limit was stored."),
                )
            )
        else:
            typer.secho(
                "Missing-data sync complete.",
                fg=typer.colors.GREEN,
            )

    except Exception as error:
        typer.secho(
            f"Sync failed: {error}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from None
    finally:
        connection.close()


@app.command(
    "refresh-recent",
    help="Refresh recently tracked Toggl data.",
)
def cmd_refresh_recent(
    context: typer.Context,
) -> None:
    """Refresh the configured recent Toggl period.

    This refresh captures entries subsequently added, edited or deleted
    within the configured recent-refresh period.

    Parameters
    ----------
    context : typer.Context
        Typer context containing the configuration path.

    """
    config, connection = load_config_and_open_database_from_context(context)
    sync_exceptions(connection, config.get("exceptions", []))

    try:
        recent_days = int(
            config.get(
                "recent_refresh_days",
                7,
            )
        )

        typer.echo(f"Refreshing the last " f"{recent_days} days...")

        result = refresh_recent(
            connection,
            config,
        )

        if result["status"] == "quota_exhausted":
            typer.secho(
                "Toggl quota exhausted.",
                fg=typer.colors.YELLOW,
                bold=True,
            )
            typer.echo(
                result.get(
                    "message",
                    ("All data retrieved before " "the limit was stored."),
                )
            )
        else:
            typer.secho(
                "Recent-data refresh complete.",
                fg=typer.colors.GREEN,
            )

    except Exception as error:
        typer.secho(
            f"Refresh failed: {error}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from None
    finally:
        connection.close()


@app.command(
    "refresh",
    help="Refresh Toggl data for a specific period.",
)
def cmd_refresh(
    context: typer.Context,
    start_day: str = typer.Argument(
        ...,
        help="Start date in YYYY-MM-DD format.",
    ),
    end_day: str = typer.Argument(
        ...,
        help="End date in YYYY-MM-DD format.",
    ),
) -> None:
    """Refresh Toggl data for a specified date range.

    Parameters
    ----------
    context : typer.Context
        Typer context containing the configuration path.
    start_day : str
        First date to refresh, in ISO format.
    end_day : str
        Last date to refresh, in ISO format.

    """
    config, connection = load_config_and_open_database_from_context(context)

    exit_code = 0

    try:
        typer.echo(f"Refreshing {start_day} " f"to {end_day}...")

        result = refresh_period(
            connection,
            config,
            start_day,
            end_day,
        )

        if result["status"] == "quota_exhausted":
            typer.secho(
                ("Refresh incomplete: Toggl API " "quota exhausted."),
                fg=typer.colors.YELLOW,
                bold=True,
            )

            pending_days = get_pending_refresh_days(connection)

            typer.echo(f"{len(pending_days)} date(s) " "remain pending.")

            if len(pending_days) > 0:
                typer.echo(
                    "Pending range: " f"{pending_days[0]} to " f"{pending_days[-1]}"
                )

            quota_resets_in_seconds = result.get("quota_resets_in_seconds")

            if quota_resets_in_seconds is not None:
                reset_minutes = (
                    round(
                        int(quota_resets_in_seconds) / 60,
                        0,
                    )
                    + 1
                )

                typer.echo("Quota resets in approximately " f"{reset_minutes} minutes.")

            typer.echo()
            typer.echo("Run refresh-pending to continue.")

            exit_code = 2
        else:
            typer.secho(
                "Refresh complete.",
                fg=typer.colors.GREEN,
            )

    except Exception as error:
        typer.echo(
            f"Refresh failed: {error}",
            err=True,
        )
        exit_code = 1
    finally:
        connection.close()

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


@app.command(
    "status",
    help=("Show the status and date range " "of the local database."),
)
def cmd_status(
    context: typer.Context,
) -> None:
    """Display local time-entry database status.

    Parameters
    ----------
    context : typer.Context
        Typer context containing the configuration path.

    """
    config, connection = load_config_and_open_database_from_context(context)

    try:
        status = connection.execute("""
            SELECT
                COUNT(*) AS entry_count,
                MIN(DATE(start_utc)) AS first_date,
                MAX(DATE(start_utc)) AS last_date
            FROM time_entries
            """).fetchone()

        first_date = status["first_date"]
        latest_date = status["last_date"]

        if first_date is None:
            first_date = "none"

        if latest_date is None:
            latest_date = "none"

        typer.echo(f"Entries: {status['entry_count']}")
        typer.echo(f"First entry: {first_date}")
        typer.echo(f"Latest entry: {latest_date}")
        typer.echo(f"Database: " f"{config['database_path']}")

    finally:
        connection.close()


@app.command(
    "dashboard",
    help=("Open the interactive working-time " "dashboard."),
)
def cmd_dashboard(
    context: typer.Context,
) -> None:
    """Launch the Streamlit working-time dashboard.

    Parameters
    ----------
    context : typer.Context
        Typer context containing the configuration path.

    """
    config_path: Path = context.obj["config_path"]

    dashboard_path = get_dashboard_path()

    exit_code = 0

    if dashboard_path.exists() is False:
        typer.echo(
            f"Dashboard not found: " f"{dashboard_path}",
            err=True,
        )
        exit_code = 1
    else:
        completed_process = subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(dashboard_path),
                "--",
                "--config",
                str(config_path),
            ],
            check=False,
        )

        exit_code = completed_process.returncode

    raise typer.Exit(code=exit_code)


@app.command(
    "refresh-pending",
    help=("Retry dates left pending by an " "incomplete refresh."),
)
def cmd_refresh_pending(
    context: typer.Context,
) -> None:
    """Retry dates awaiting completion after an interrupted refresh.

    Parameters
    ----------
    context : typer.Context
        Typer context containing the configuration path.

    """
    config, connection = load_config_and_open_database_from_context(context)

    exit_code = 0

    try:
        pending_days = get_pending_refresh_days(connection)

        if len(pending_days) == 0:
            typer.echo("There are no pending refreshes.")
        else:
            typer.echo(
                f"Refreshing {len(pending_days)} "
                "pending date(s) "
                f"from {pending_days[0]} "
                f"to {pending_days[-1]}..."
            )

            result = refresh_pending(
                connection,
                config,
            )

            if result["status"] == "quota_exhausted":
                typer.secho(
                    ("Refresh incomplete: Toggl " "API quota exhausted."),
                    fg=typer.colors.YELLOW,
                    bold=True,
                )

                typer.echo(f"{result['pending_count']} " "date(s) remain pending.")

                first_pending = result.get("first_pending")
                last_pending = result.get("last_pending")

                if first_pending is not None and last_pending is not None:
                    typer.echo(
                        "Pending range: " f"{first_pending} to " f"{last_pending}"
                    )

                quota_resets_in_seconds = result.get("quota_resets_in_seconds")

                if quota_resets_in_seconds is not None:
                    reset_minutes = (
                        round(
                            int(quota_resets_in_seconds) / 60,
                            0,
                        )
                        + 1
                    )

                    typer.echo(
                        "Quota resets in approximately " f"{reset_minutes} minutes."
                    )

                typer.echo()
                typer.echo("Run refresh-pending again " "to continue.")

                exit_code = 2
            else:
                typer.secho(
                    "Pending refresh complete.",
                    fg=typer.colors.GREEN,
                )
                typer.echo(f"{result['entries_saved']} " "entries processed.")

    finally:
        connection.close()

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


@app.command(
    "toggl-workspaces",
    help="List Toggl workspaces and their IDs.",
)
def cmd_toggl_workspaces(
    config_path: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Path to the configuration file.",
        ),
    ] = Path("config.yml"),
) -> None:
    """List workspaces available to the Toggl account.

    The API token is read from the environment first, then from the
    configuration file. If neither provides a token, the user is prompted.

    Parameters
    ----------
    config_path : Path
        Path to a configuration file which may contain the Toggl API
        token.

    """
    config: dict[str, Any] = {}

    if config_path.exists():
        with config_path.open(encoding="utf-8") as config_file:
            loaded_config = yaml.safe_load(config_file)

        if loaded_config is not None:
            config = loaded_config

    api_token = os.getenv("TOGGL_API_TOKEN")

    if api_token is None:
        api_token = config.get("api_token")

    if api_token is None:
        api_token = typer.prompt(
            "Toggl API token",
            hide_input=True,
        )

    client = TogglClient(
        api_token=api_token,
        workspace_id=None,
    )

    try:
        workspaces = client.fetch_workspaces()
    except Exception as error:
        typer.secho(
            ("Could not retrieve Toggl " f"workspaces: {error}"),
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from None

    if len(workspaces) == 0:
        typer.echo("No Toggl workspaces found.")
    else:
        for workspace in workspaces:
            workspace_name = workspace.get(
                "name",
                "Unnamed workspace",
            )

            typer.echo(f"{workspace_name}: " f"{workspace['id']}")


@app.command(
    "config",
    help="Open the configuration file in the default application.",
)
def cmd_config(
    ctx: typer.Context,
) -> None:
    """Open the configuration file in the default application."""
    config_path: Path = ctx.obj["config_path"]

    if not config_path.exists():
        typer.echo(
            f"Configuration file not found: {config_path}",
            err=True,
        )
        raise typer.Exit(code=1)

    result = subprocess.run(
        [
            "xdg-open",
            str(config_path),
        ],
        check=False,
    )

    raise typer.Exit(code=result.returncode)


def main() -> None:
    """Run the command-line application."""
    app()


if __name__ == "__main__":
    main()
