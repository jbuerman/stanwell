"""Retrieve projects and time entries from the Toggl Track APIs.

Recent time entries are retrieved from the Toggl Track API. Older entries are
retrieved from the Reports API because the standard endpoint only provides a
limited recent period.

The Reports API groups individual time entries into report rows. This module
flattens those rows into entry dictionaries so that recent and historical
entries can use the same normalisation and storage pipeline.

The module retains function-level entry points for existing callers, while
``TogglClient`` contains authentication, HTTP and pagination behaviour.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from stanwell.toggl.constants import (
    API_URL,
    PROJECTS_API_URL,
    RECENT_ENTRY_WINDOW_DAYS,
    REPORTS_API_URL,
    WORKSPACES_API_URL,
)
from stanwell.toggl.exceptions import TogglQuotaExhaustedError

PROJECT_PAGE_SIZE = 200

Config = Mapping[str, Any]
Entry = dict[str, Any]
SleepFunction = Callable[[float], None]
TodayFunction = Callable[[], date]


def _optional_int(value: str | None) -> int | None:
    """Convert an optional string value to an integer."""
    if value is None:
        return None

    return int(value)


class TogglClient:
    """Client for the Toggl Track and Reports APIs.

    Parameters
    ----------
    api_token : str
        Toggl API token used for basic authentication.
    workspace_id : int or None
        Toggl workspace ID. It is required for project and historical-entry
        requests but not for recent-entry requests.
    session : requests.Session, optional
        HTTP session used for requests. Supplying a session allows connection
        reuse and straightforward testing.
    sleep : callable, optional
        Function used to pause between paginated requests.
    today : callable, optional
        Function returning the current local date. It is injectable so range
        selection can be tested deterministically.

    """

    def __init__(
        self,
        api_token: str,
        workspace_id: int | None,
        session: requests.Session | None = None,
        sleep: SleepFunction = time.sleep,
        today: TodayFunction = date.today,
    ) -> None:
        self.api_token = api_token
        self.workspace_id = workspace_id
        self.session = session or requests.Session()
        self.sleep = sleep
        self.today = today

    @classmethod
    def from_config(
        cls,
        config: Config,
        session: requests.Session | None = None,
        sleep: SleepFunction = time.sleep,
        today: TodayFunction = date.today,
    ) -> TogglClient:
        """Create a client from application configuration.

        Parameters
        ----------
        config : Mapping[str, Any]
            Application configuration containing ``api_token`` and optionally
            ``workspace_id``. ``TOGGL_API_TOKEN`` takes precedence over the
            configured token.
        session : requests.Session, optional
            HTTP session used for requests.
        sleep : callable, optional
            Function used between paginated requests.
        today : callable, optional
            Function returning the current local date.

        Returns
        -------
        TogglClient
            Configured client instance.

        Raises
        ------
        RuntimeError
            If no API token is available.

        """
        api_token = os.getenv("TOGGL_API_TOKEN") or config.get("api_token")
        if not api_token:
            raise RuntimeError("Set TOGGL_API_TOKEN or api_token in config.yml")

        workspace_id = config.get("workspace_id")
        return cls(
            api_token=str(api_token),
            workspace_id=int(workspace_id) if workspace_id is not None else None,
            session=session,
            sleep=sleep,
            today=today,
        )

    @property
    def authentication(self) -> tuple[str, str]:
        """Return basic-authentication credentials for Toggl requests."""
        return self.api_token, "api_token"

    @property
    def headers(self) -> dict[str, str]:
        """Return common JSON request headers."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _require_workspace_id(self, purpose: str) -> int:
        if self.workspace_id is None:
            raise RuntimeError(
                f"Add workspace_id to config.yml before downloading {purpose}."
            )
        return self.workspace_id

    @staticmethod
    def _raise_for_quota_exhaustion(
        response: requests.Response,
        partial_entries: list[Entry] | None = None,
    ) -> None:
        if response.status_code in (402, 429):
            raise TogglQuotaExhaustedError(
                status_code=response.status_code,
                remaining=_optional_int(
                    response.headers.get("X-Toggl-Quota-Remaining")
                ),
                resets_in=_optional_int(
                    response.headers.get("X-Toggl-Quota-Resets-In")
                ),
                partial_entries=partial_entries,
            )

    def fetch_workspace_projects(self) -> tuple[list[Entry], int]:
        """Download all projects from the configured workspace.

        Returns
        -------
        tuple[list[dict[str, Any]], int]
            Downloaded projects and the number of API requests made.

        Raises
        ------
        RuntimeError
            If the workspace ID is missing or Toggl returns an HTTP error.
        TogglQuotaExhausted
            If Toggl returns HTTP 402 or 429.
        TypeError
            If the response does not contain a project list.

        """
        workspace_id = self._require_workspace_id("projects")
        url = PROJECTS_API_URL.format(workspace_id=workspace_id)
        projects: list[Entry] = []
        page = 1
        request_count = 0

        while True:
            params: dict[str, str | int] = {
                "active": "both",
                "page": page,
                "per_page": 200,
            }
            response = self.session.get(
                url,
                params=params,
                auth=self.authentication,
                headers=self.headers,
                timeout=60,
            )
            request_count += 1
            self._raise_for_quota_exhaustion(response)

            if not response.ok:
                raise RuntimeError(
                    f"Toggl projects API returned HTTP {response.status_code}.\n"
                    f"Workspace: {workspace_id}\n"
                    f"Response body:\n{response.text[:1_000]}"
                )

            page_projects = _extract_projects(response.json())
            projects.extend(page_projects)

            if len(page_projects) < PROJECT_PAGE_SIZE:
                break

            page += 1
            self.sleep(1.05)

        return projects, request_count

    def fetch_range(
        self,
        config: Config,
        start_date: date,
        end_date: date,
    ) -> list[Entry]:
        """Retrieve entries for a date range using the appropriate APIs.

        Parameters
        ----------
        config : Mapping[str, Any]
            Application configuration containing the local ``timezone``.
        start_date : date
            First local calendar date to retrieve.
        end_date : date
            Last local calendar date to retrieve.

        Returns
        -------
        list[dict[str, Any]]
            Retrieved entries, deduplicated by Toggl entry ID.

        """
        recent_boundary = self.today() - timedelta(days=RECENT_ENTRY_WINDOW_DAYS)

        if end_date < recent_boundary:
            return self.fetch_historical_range(start_date, end_date)

        if start_date >= recent_boundary:
            return self.fetch_recent_range(config, start_date, end_date)

        historical_entries = self.fetch_historical_range(
            start_date,
            recent_boundary - timedelta(days=1),
        )
        recent_entries = self.fetch_recent_range(
            config,
            recent_boundary,
            end_date,
        )

        entries_by_id = {
            _entry_id(entry): entry for entry in historical_entries + recent_entries
        }
        return list(entries_by_id.values())

    def fetch_recent_range(
        self,
        config: Config,
        start_date: date,
        end_date: date,
    ) -> list[Entry]:
        """Retrieve recent entries from the Toggl Track API.

        The requested local dates are converted to a half-open interval from
        local midnight on ``start_date`` to local midnight after ``end_date``.

        Parameters
        ----------
        config : Mapping[str, Any]
            Application configuration containing the local ``timezone``.
        start_date : date
            First local calendar date to retrieve.
        end_date : date
            Last local calendar date to retrieve.

        Returns
        -------
        list[dict[str, Any]]
            Time-entry dictionaries returned by Toggl.

        """
        timezone = ZoneInfo(str(config["timezone"]))
        start_local = datetime.combine(
            start_date,
            dtime.min,
            tzinfo=timezone,
        )
        end_local = datetime.combine(
            end_date + timedelta(days=1),
            dtime.min,
            tzinfo=timezone,
        )

        response = self.session.get(
            API_URL,
            params={
                "start_date": start_local.isoformat(),
                "end_date": end_local.isoformat(),
            },
            auth=self.authentication,
            headers=self.headers,
            timeout=60,
        )
        self._raise_for_quota_exhaustion(response)

        if not response.ok:
            raise RuntimeError(
                f"Toggl API returned HTTP {response.status_code}.\n"
                f"Requested period: {start_date} to {end_date}\n"
                f"Request URL: {response.url}\n"
                f"Response body:\n{response.text[:1_000]}"
            )

        response_data = response.json()
        if not isinstance(response_data, list):
            raise TypeError(
                "Toggl API returned an unexpected response type: "
                f"{type(response_data).__name__}"
            )
        return response_data

    def fetch_historical_range(
        self,
        start_date: date,
        end_date: date,
    ) -> list[Entry]:
        """Retrieve historical entries from the Toggl Reports API.

        Report rows are flattened into individual time-entry dictionaries.
        Entries already received are attached to ``TogglQuotaExhausted`` if
        quota is exhausted during pagination.

        Parameters
        ----------
        start_date : date
            First calendar date to retrieve.
        end_date : date
            Last calendar date to retrieve.

        Returns
        -------
        list[dict[str, Any]]
            Flattened time-entry dictionaries.

        """
        workspace_id = self._require_workspace_id("historical entries")
        url = REPORTS_API_URL.format(workspace_id=workspace_id)
        base_payload: dict[str, Any] = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "page_size": 100,
            "order_by": "date",
            "order_dir": "ASC",
            "grouped": False,
            "enrich_response": True,
        }
        flattened_entries: list[Entry] = []
        first_row_number: int | None = None

        while True:
            payload = dict(base_payload)
            if first_row_number is not None:
                payload["first_row_number"] = first_row_number

            response = self.session.post(
                url,
                json=payload,
                auth=self.authentication,
                headers=self.headers,
                timeout=60,
            )
            self._raise_for_quota_exhaustion(
                response,
                partial_entries=flattened_entries,
            )

            if not response.ok:
                raise RuntimeError(
                    f"Toggl Reports API returned HTTP {response.status_code}.\n"
                    f"Requested period: {start_date} to {end_date}\n"
                    f"Response body:\n{response.text[:1_000]}"
                )

            flattened_entries.extend(
                _flatten_report_rows(response.json(), workspace_id)
            )

            next_row_header = response.headers.get("X-Next-Row-Number")
            if not next_row_header:
                break

            try:
                next_row_number = int(next_row_header)
            except ValueError as error:
                raise ValueError(
                    "Toggl returned an invalid X-Next-Row-Number header: "
                    f"{next_row_header!r}"
                ) from error

            if next_row_number == first_row_number:
                raise RuntimeError(
                    "Toggl pagination did not advance. "
                    f"X-Next-Row-Number remained {next_row_number}."
                )

            first_row_number = next_row_number
            self.sleep(1.05)

        return flattened_entries

    def fetch_workspaces(self) -> list[Entry]:
        """Retrieve workspaces available to the authenticated Toggl user.

        Returns
        -------
        list[dict[str, Any]]
            Workspaces available to the authenticated user.

        Raises
        ------
        TogglQuotaExhausted
            If Toggl returns HTTP 402 or 429.
        RuntimeError
            If Toggl returns another unsuccessful HTTP response.
        TypeError
            If Toggl does not return a list of workspaces.

        """
        response = self.session.get(
            WORKSPACES_API_URL,
            auth=self.authentication,
            headers=self.headers,
            timeout=60,
        )

        self._raise_for_quota_exhaustion(response)

        if not response.ok:
            raise RuntimeError(
                f"Toggl workspaces API returned HTTP "
                f"{response.status_code}.\n"
                f"Response body:\n{response.text[:1_000]}"
            )

        response_data = response.json()

        if not isinstance(response_data, list):
            raise TypeError(
                "Toggl workspaces API returned an unexpected response type: "
                f"{type(response_data).__name__}"
            )

        return response_data


def _extract_projects(response_data: Any) -> list[Entry]:
    """Extract a project list from either supported response shape."""
    if isinstance(response_data, list):
        page_projects = response_data
    elif isinstance(response_data, dict):
        page_projects = response_data.get("items", [])
    else:
        raise TypeError(
            "Toggl projects API returned an unexpected response type: "
            f"{type(response_data).__name__}"
        )

    if not isinstance(page_projects, list):
        raise TypeError("Toggl projects API response does not contain a project list.")
    return page_projects


def _flatten_report_rows(
    report_rows: Any,
    workspace_id: int,
) -> list[Entry]:
    """Flatten Toggl report rows into individual time entries.

    Parameters
    ----------
    report_rows : Any
        Decoded Reports API response. A list of report-row dictionaries is
        expected.
    workspace_id : int
        Workspace ID added to every flattened entry.

    Returns
    -------
    list[dict[str, Any]]
        Individual entries containing their parent row's shared metadata.

    Raises
    ------
    TypeError
        If rows or nested entries have unexpected types.
    ValueError
        If a row has no ``time_entries`` field or an entry has no ID.

    """
    if not isinstance(report_rows, list):
        raise TypeError(
            "Toggl Reports API returned an unexpected response type: "
            f"{type(report_rows).__name__}"
        )

    flattened_entries: list[Entry] = []

    for row_position, report_row in enumerate(report_rows):
        if not isinstance(report_row, dict):
            raise TypeError(
                "Toggl Reports API returned a report row that is not an "
                f"object. Position: {row_position}; "
                f"type: {type(report_row).__name__}"
            )

        nested_entries = report_row.get("time_entries")
        if nested_entries is None:
            raise ValueError(
                "Toggl report row has no time_entries field. "
                f"Available fields: {sorted(report_row.keys())}"
            )
        if not isinstance(nested_entries, list):
            raise TypeError(
                "The time_entries field is not a list. "
                f"Report row position: {row_position}; "
                f"type: {type(nested_entries).__name__}"
            )

        shared_metadata: Entry = {
            "workspace_id": workspace_id,
            "user_id": report_row.get("user_id"),
            "user_account_id": report_row.get("user_account_id"),
            "username": report_row.get("username"),
            "email": report_row.get("email"),
            "project_id": report_row.get("project_id"),
            "project_name": report_row.get("project_name"),
            "project_color": report_row.get("project_color"),
            "project_hex": report_row.get("project_hex"),
            "task_id": report_row.get("task_id"),
            "billable": report_row.get("billable", False),
            "description": report_row.get("description"),
            "tag_ids": report_row.get("tag_ids") or [],
            "tags": report_row.get("tag_names") or [],
            "billable_amount_in_cents": report_row.get("billable_amount_in_cents"),
            "hourly_rate_in_cents": report_row.get("hourly_rate_in_cents"),
            "currency": report_row.get("currency"),
            "report_row_number": report_row.get("row_number"),
        }

        for entry_position, nested_entry in enumerate(nested_entries):
            if not isinstance(nested_entry, dict):
                raise TypeError(
                    "A nested Toggl time entry is not an object. "
                    f"Report row: {row_position}; "
                    f"entry position: {entry_position}; "
                    f"type: {type(nested_entry).__name__}"
                )

            flattened_entry = dict(shared_metadata)
            flattened_entry.update(nested_entry)

            if flattened_entry.get("id") is None:
                raise ValueError(
                    "Nested Toggl time entry has no ID. "
                    f"Report row: {row_position}; "
                    f"entry position: {entry_position}; "
                    f"available fields: {sorted(nested_entry.keys())}"
                )

            flattened_entries.append(flattened_entry)

    return flattened_entries


def _entry_id(entry: Entry) -> int:
    """Return an entry ID from Track or Reports API data."""
    entry_id = entry.get("id")
    if entry_id is None:
        entry_id = entry["time_entry_id"]
    return int(entry_id)


def fetch_workspace_projects(config: Config) -> tuple[list[Entry], int]:
    """Download all projects using application configuration."""
    return TogglClient.from_config(config).fetch_workspace_projects()


def fetch_range(
    config: Config,
    start_date: date,
    end_date: date,
) -> list[Entry]:
    """Retrieve a date range using application configuration."""
    return TogglClient.from_config(config).fetch_range(
        config,
        start_date,
        end_date,
    )


def fetch_recent_range(
    config: Config,
    start_date: date,
    end_date: date,
) -> list[Entry]:
    """Retrieve recent entries using application configuration."""
    return TogglClient.from_config(config).fetch_recent_range(
        config,
        start_date,
        end_date,
    )


def fetch_historical_range(
    config: Config,
    start_date: date,
    end_date: date,
) -> list[Entry]:
    """Retrieve historical entries using application configuration."""
    return TogglClient.from_config(config).fetch_historical_range(
        start_date,
        end_date,
    )
