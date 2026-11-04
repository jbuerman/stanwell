"""Optional integration tests for access to the real Toggl APIs.

These tests make real network requests and consume Toggl API quota. They are
disabled by default and require local Toggl credentials and configuration.

Run explicitly with:

    uv run pytest -m integration

The tests are intended to verify API access and the response structure relied
upon by the application. They must not contain personal Toggl data.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import pytest
import requests

from stanwell.toggl.client import TogglClient
from stanwell.toggl.constants import RECENT_ENTRY_WINDOW_DAYS
from stanwell.toggl.exceptions import TogglQuotaExhaustedError

pytestmark = pytest.mark.integration


@pytest.fixture
def real_client() -> TogglClient:
    """Create a client using credentials supplied by the environment."""
    api_token = os.getenv("TOGGL_API_TOKEN")
    workspace_id = os.getenv("TOGGL_WORKSPACE_ID")

    if api_token is None or workspace_id is None:
        pytest.skip("Real Toggl credentials are not available.")

    return TogglClient(
        api_token=api_token,
        workspace_id=int(workspace_id),
    )


def _assert_entry_structure(entry: dict[str, Any]) -> None:
    """Check fields required by the application's Toggl processing."""
    assert entry.get("id") is not None
    assert entry.get("start") is not None

    assert isinstance(entry["id"], int)
    assert isinstance(entry["start"], str)


def test_recent_api_access(real_client: TogglClient) -> None:
    """Check access to recent Toggl entries and their basic structure."""
    end_date = date.today()
    start_date = end_date - timedelta(days=1)

    try:
        entries = real_client.fetch_recent_range(
            {"timezone": "Europe/London"},
            start_date,
            end_date,
        )
    except TogglQuotaExhaustedError:
        pytest.skip("Toggl API quota is currently exhausted.")
    except requests.RequestException as error:
        pytest.skip(f"Toggl API could not be reached: {error}")

    assert isinstance(entries, list)

    for entry in entries:
        assert isinstance(entry, dict)
        _assert_entry_structure(entry)


def test_historical_api_access(real_client: TogglClient) -> None:
    """Check access to historical Toggl entries and their basic structure."""
    end_date = (
        date.today() - timedelta(days=RECENT_ENTRY_WINDOW_DAYS) - timedelta(days=1)
    )
    start_date = end_date - timedelta(days=1)

    try:
        entries = real_client.fetch_historical_range(
            start_date,
            end_date,
        )
    except TogglQuotaExhaustedError:
        pytest.skip("Toggl API quota is currently exhausted.")
    except requests.RequestException as error:
        pytest.skip(f"Toggl Reports API could not be reached: {error}")

    assert isinstance(entries, list)

    for entry in entries:
        assert isinstance(entry, dict)
        _assert_entry_structure(entry)
        assert entry.get("workspace_id") == real_client.workspace_id


def test_workspace_api_access() -> None:
    """Check access to Toggl workspaces and their basic structure."""
    api_token = os.getenv("TOGGL_API_TOKEN")

    if api_token is None:
        pytest.skip("Real Toggl credentials are not available.")

    client = TogglClient(
        api_token=api_token,
        workspace_id=None,
    )

    try:
        workspaces = client.fetch_workspaces()
    except TogglQuotaExhaustedError:
        pytest.skip("Toggl API quota is currently exhausted.")
    except requests.RequestException as error:
        pytest.skip(f"Toggl API could not be reached: {error}")

    assert isinstance(workspaces, list)

    for workspace in workspaces:
        assert isinstance(workspace, dict)
        assert workspace.get("id") is not None
        assert workspace.get("name") is not None

        assert isinstance(workspace["id"], int)
        assert isinstance(workspace["name"], str)
