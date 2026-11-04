"""Tests for the Toggl API client and response transformations."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import Mock

import pytest

from stanwell.toggl.client import (
    TogglClient,
    _extract_projects,
    _flatten_report_rows,
)
from stanwell.toggl.constants import (
    API_URL,
    PROJECTS_API_URL,
    RECENT_ENTRY_WINDOW_DAYS,
    REPORTS_API_URL,
)
from stanwell.toggl.exceptions import TogglQuotaExhaustedError


class FakeResponse:
    """Small requests.Response substitute used by client tests."""

    def __init__(
        self,
        json_data: Any,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        text: str = "",
        url: str = "https://example.test/request",
    ) -> None:
        self._json_data = json_data
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.url = url

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    def json(self) -> Any:
        return self._json_data


@pytest.fixture
def config() -> dict[str, Any]:
    return {
        "api_token": "configured-token",
        "workspace_id": 123,
        "timezone": "Europe/London",
    }


@pytest.fixture
def session() -> Mock:
    return Mock()


@pytest.fixture
def client(session: Mock) -> TogglClient:
    return TogglClient(
        api_token="token",
        workspace_id=123,
        session=session,
        sleep=lambda _: None,
        today=lambda: date(2026, 10, 25),
    )


class TestTogglClientConfiguration:
    def test_environment_token_takes_precedence(
        self,
        monkeypatch: pytest.MonkeyPatch,
        config: dict[str, Any],
    ) -> None:
        monkeypatch.setenv("TOGGL_API_TOKEN", "environment-token")

        client = TogglClient.from_config(config)

        assert client.api_token == "environment-token"
        assert client.workspace_id == 123

    def test_configured_token_used_without_environment_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
        config: dict[str, Any],
    ) -> None:
        monkeypatch.delenv("TOGGL_API_TOKEN", raising=False)

        client = TogglClient.from_config(config)

        assert client.api_token == "configured-token"

    def test_missing_token_raises_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TOGGL_API_TOKEN", raising=False)

        with pytest.raises(RuntimeError, match="TOGGL_API_TOKEN"):
            TogglClient.from_config({})

    def test_workspace_required_for_projects(self) -> None:
        client = TogglClient("token", None, session=Mock())

        with pytest.raises(RuntimeError, match="workspace_id"):
            client.fetch_workspace_projects()


class TestExtractProjects:
    def test_accepts_direct_list(self) -> None:
        projects = [{"id": 1}]

        assert _extract_projects(projects) == projects

    def test_accepts_items_object(self) -> None:
        projects = [{"id": 1}]

        assert _extract_projects({"items": projects}) == projects

    def test_rejects_unexpected_response_type(self) -> None:
        with pytest.raises(TypeError, match="unexpected response type"):
            _extract_projects("not projects")

    def test_rejects_non_list_items(self) -> None:
        with pytest.raises(TypeError, match="project list"):
            _extract_projects({"items": {"id": 1}})


class TestFetchWorkspaceProjects:
    def test_fetches_single_page(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.get.return_value = FakeResponse([{"id": 1}])

        projects, request_count = client.fetch_workspace_projects()

        assert projects == [{"id": 1}]
        assert request_count == 1
        session.get.assert_called_once_with(
            PROJECTS_API_URL.format(workspace_id=123),
            params={"active": "both", "page": 1, "per_page": 200},
            auth=("token", "api_token"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=60,
        )

    def test_fetches_second_page_after_full_page(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        first_page = [{"id": entry_id} for entry_id in range(200)]
        session.get.side_effect = [
            FakeResponse(first_page),
            FakeResponse([{"id": 200}]),
        ]

        projects, request_count = client.fetch_workspace_projects()

        assert len(projects) == 201
        assert request_count == 2
        assert session.get.call_args_list[1].kwargs["params"]["page"] == 2

    @pytest.mark.parametrize("status_code", [402, 429])
    def test_quota_response_raises_specific_exception(
        self,
        client: TogglClient,
        session: Mock,
        status_code: int,
    ) -> None:
        session.get.return_value = FakeResponse(
            [],
            status_code=status_code,
            headers={
                "X-Toggl-Quota-Remaining": "0",
                "X-Toggl-Quota-Resets-In": "10",
            },
        )

        with pytest.raises(TogglQuotaExhaustedError) as exc_info:
            client.fetch_workspace_projects()

        assert exc_info.value.status_code == status_code
        assert exc_info.value.remaining == 0
        assert exc_info.value.resets_in == 10

    def test_other_http_error_contains_response_details(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.get.return_value = FakeResponse(
            {},
            status_code=500,
            text="server error",
        )

        with pytest.raises(RuntimeError, match="server error"):
            client.fetch_workspace_projects()


class TestFetchRange:
    def test_uses_historical_api_for_old_range(self, client: TogglClient) -> None:
        boundary = date(2026, 10, 25) - timedelta(days=RECENT_ENTRY_WINDOW_DAYS)
        client.fetch_historical_range = Mock(return_value=[{"id": 1}])
        client.fetch_recent_range = Mock()

        result = client.fetch_range(
            {"timezone": "Europe/London"},
            date(2020, 1, 1),
            boundary - timedelta(days=1),
        )

        assert result == [{"id": 1}]
        client.fetch_recent_range.assert_not_called()

    def test_uses_recent_api_for_recent_range(self, client: TogglClient) -> None:
        client.fetch_recent_range = Mock(return_value=[{"id": 1}])
        client.fetch_historical_range = Mock()

        result = client.fetch_range(
            {"timezone": "Europe/London"},
            date(2026, 10, 25),
            date(2026, 10, 25),
        )

        assert result == [{"id": 1}]
        client.fetch_historical_range.assert_not_called()

    def test_split_range_deduplicates_and_prefers_recent_entry(
        self,
        client: TogglClient,
    ) -> None:
        client.fetch_historical_range = Mock(
            return_value=[
                {"id": 1, "description": "historical"},
                {"id": 2},
            ]
        )
        client.fetch_recent_range = Mock(
            return_value=[{"id": 1, "description": "recent"}]
        )

        result = client.fetch_range(
            {"timezone": "Europe/London"},
            date(2020, 1, 1),
            date(2026, 10, 25),
        )

        assert result == [
            {"id": 1, "description": "recent"},
            {"id": 2},
        ]


class TestFetchRecentRange:
    def test_sends_local_half_open_date_range(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.get.return_value = FakeResponse([{"id": 1}])

        result = client.fetch_recent_range(
            {"timezone": "Europe/London"},
            date(2026, 3, 28),
            date(2026, 3, 29),
        )

        assert result == [{"id": 1}]
        assert session.get.call_args.args[0] == API_URL
        assert session.get.call_args.kwargs["params"] == {
            "start_date": "2026-03-28T00:00:00+00:00",
            "end_date": "2026-03-30T00:00:00+01:00",
        }

    @pytest.mark.parametrize("status_code", [402, 429])
    def test_quota_response_raises_specific_exception(
        self,
        client: TogglClient,
        session: Mock,
        status_code: int,
    ) -> None:
        session.get.return_value = FakeResponse([], status_code=status_code)

        with pytest.raises(TogglQuotaExhaustedError):
            client.fetch_recent_range(
                {"timezone": "Europe/London"},
                date(2026, 1, 1),
                date(2026, 1, 1),
            )

    def test_rejects_non_list_response(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.get.return_value = FakeResponse({"items": []})

        with pytest.raises(TypeError, match="unexpected response type"):
            client.fetch_recent_range(
                {"timezone": "Europe/London"},
                date(2026, 1, 1),
                date(2026, 1, 1),
            )

    def test_http_error_contains_period_and_body(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.get.return_value = FakeResponse(
            {},
            status_code=500,
            text="server error",
        )

        with pytest.raises(RuntimeError, match="server error"):
            client.fetch_recent_range(
                {"timezone": "Europe/London"},
                date(2026, 1, 1),
                date(2026, 1, 2),
            )


class TestFlattenReportRows:
    def test_adds_shared_metadata_to_each_nested_entry(self) -> None:
        rows = [
            {
                "user_id": 10,
                "project_id": 20,
                "description": "Shared description",
                "tag_ids": [30],
                "tag_names": ["Tag"],
                "time_entries": [
                    {"id": 1, "start": "first"},
                    {"id": 2, "start": "second"},
                ],
            }
        ]

        result = _flatten_report_rows(rows, workspace_id=123)

        assert [entry["id"] for entry in result] == [1, 2]
        assert all(entry["workspace_id"] == 123 for entry in result)
        assert all(entry["project_id"] == 20 for entry in result)
        assert all(entry["tags"] == ["Tag"] for entry in result)

    def test_nested_entry_overrides_shared_metadata(self) -> None:
        rows = [
            {
                "description": "Shared",
                "time_entries": [
                    {"id": 1, "description": "Specific"},
                ],
            }
        ]

        result = _flatten_report_rows(rows, workspace_id=123)

        assert result[0]["description"] == "Specific"

    def test_missing_tags_become_empty_lists(self) -> None:
        result = _flatten_report_rows(
            [{"time_entries": [{"id": 1}]}],
            workspace_id=123,
        )

        assert result[0]["tag_ids"] == []
        assert result[0]["tags"] == []

    def test_rejects_non_list_response(self) -> None:
        with pytest.raises(TypeError, match="unexpected response type"):
            _flatten_report_rows({}, workspace_id=123)

    def test_rejects_row_without_time_entries(self) -> None:
        with pytest.raises(ValueError, match="no time_entries"):
            _flatten_report_rows([{}], workspace_id=123)

    def test_rejects_non_list_time_entries(self) -> None:
        with pytest.raises(TypeError, match="not a list"):
            _flatten_report_rows(
                [{"time_entries": {"id": 1}}],
                workspace_id=123,
            )

    def test_rejects_non_dictionary_nested_entry(self) -> None:
        with pytest.raises(TypeError, match="not an object"):
            _flatten_report_rows(
                [{"time_entries": ["entry"]}],
                workspace_id=123,
            )

    def test_rejects_entry_without_id(self) -> None:
        with pytest.raises(ValueError, match="no ID"):
            _flatten_report_rows(
                [{"time_entries": [{"start": "value"}]}],
                workspace_id=123,
            )


class TestFetchHistoricalRange:
    def test_fetches_and_flattens_single_page(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.post.return_value = FakeResponse(
            [
                {
                    "project_id": 20,
                    "time_entries": [{"id": 1}],
                }
            ]
        )

        result = client.fetch_historical_range(
            date(2020, 1, 1),
            date(2020, 1, 2),
        )

        assert result[0]["id"] == 1
        assert result[0]["workspace_id"] == 123
        assert result[0]["project_id"] == 20
        session.post.assert_called_once_with(
            REPORTS_API_URL.format(workspace_id=123),
            json={
                "start_date": "2020-01-01",
                "end_date": "2020-01-02",
                "page_size": 100,
                "order_by": "date",
                "order_dir": "ASC",
                "grouped": False,
                "enrich_response": True,
            },
            auth=("token", "api_token"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=60,
        )

    def test_uses_next_row_number_for_second_page(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.post.side_effect = [
            FakeResponse(
                [{"time_entries": [{"id": 1}]}],
                headers={"X-Next-Row-Number": "101"},
            ),
            FakeResponse([{"time_entries": [{"id": 2}]}]),
        ]

        result = client.fetch_historical_range(
            date(2020, 1, 1),
            date(2020, 1, 2),
        )

        assert [entry["id"] for entry in result] == [1, 2]
        assert session.post.call_args_list[1].kwargs["json"]["first_row_number"] == 101

    def test_rejects_invalid_next_row_number(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.post.return_value = FakeResponse(
            [],
            headers={"X-Next-Row-Number": "invalid"},
        )

        with pytest.raises(ValueError, match="invalid X-Next-Row-Number"):
            client.fetch_historical_range(
                date(2020, 1, 1),
                date(2020, 1, 2),
            )

    def test_rejects_repeated_next_row_number(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.post.side_effect = [
            FakeResponse([], headers={"X-Next-Row-Number": "101"}),
            FakeResponse([], headers={"X-Next-Row-Number": "101"}),
        ]

        with pytest.raises(RuntimeError, match="did not advance"):
            client.fetch_historical_range(
                date(2020, 1, 1),
                date(2020, 1, 2),
            )

    def test_quota_exception_contains_partial_entries(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.post.side_effect = [
            FakeResponse(
                [{"time_entries": [{"id": 1}]}],
                headers={"X-Next-Row-Number": "101"},
            ),
            FakeResponse([], status_code=429),
        ]

        with pytest.raises(TogglQuotaExhaustedError) as exc_info:
            client.fetch_historical_range(
                date(2020, 1, 1),
                date(2020, 1, 2),
            )

        assert [entry["id"] for entry in exc_info.value.partial_entries] == [1]


class TestFetchWorkspaces:
    def test_returns_workspaces(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        workspaces = [
            {"id": 123, "name": "Workspace"},
        ]
        session.get.return_value = FakeResponse(workspaces)

        result = client.fetch_workspaces()

        assert result == workspaces

    def test_rejects_unexpected_response_type(
        self,
        client: TogglClient,
        session: Mock,
    ) -> None:
        session.get.return_value = FakeResponse(
            {"id": 123},
        )

        with pytest.raises(
            TypeError,
            match="unexpected response type",
        ):
            client.fetch_workspaces()
