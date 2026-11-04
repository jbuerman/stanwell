import json
from datetime import datetime

import pytest
from dateutil.parser import isoparse

from stanwell.toggl.normalisation import (
    NormalisedTimeEntry,
    normalise,
)


def test_normalise_recent_api_entry():
    raw_entry = {
        "id": 123,
        "workspace_id": 10,
        "project_id": 20,
        "task_id": 30,
        "description": "Development",
        "start": "2026-10-24T09:00:00+00:00",
        "stop": "2026-10-24T10:00:00+00:00",
        "duration": 3600,
        "tags": [
            "software",
            "project",
        ],
        "billable": True,
        "at": "2026-10-24T10:00:00+00:00",
    }

    result = normalise(
        raw_entry,
        project_names={
            20: "Time tracking",
        },
    )

    assert isinstance(result, NormalisedTimeEntry)
    assert result.id == 123
    assert result.workspace_id == 10
    assert result.project_id == 20
    assert result.project_name == "Time tracking"
    assert result.task_id == 30
    assert result.description == "Development"
    assert result.start_utc == "2026-10-24T09:00:00+00:00"
    assert result.stop_utc == "2026-10-24T10:00:00+00:00"
    assert result.duration_seconds == 3600
    assert json.loads(result.tags_json) == [
        "software",
        "project",
    ]
    assert result.billable == 1
    assert result.updated_at == "2026-10-24T10:00:00+00:00"
    assert json.loads(result.raw_json) == raw_entry
    assert isoparse(result.fetched_at) <= datetime.now().astimezone()


def test_normalise_reports_api_entry():
    raw_entry = {
        "id": 456,
        "wid": 11,
        "pid": 21,
        "tid": 31,
        "description": "Research",
        "start": "2026-10-24T11:00:00+00:00",
        "stop": "2026-10-24T12:30:00+00:00",
        "seconds": 5400,
        "tag_names": ["research"],
        "updated_at": "2026-10-24T12:30:00+00:00",
    }

    result = normalise(
        raw_entry,
        project_names={
            21: "Research project",
        },
    )

    assert result.workspace_id == 11
    assert result.project_id == 21
    assert result.project_name == "Research project"
    assert result.task_id == 31
    assert result.duration_seconds == 5400
    assert json.loads(result.tags_json) == ["research"]
    assert result.updated_at == "2026-10-24T12:30:00+00:00"


def test_normalise_prefers_explicit_project_name():
    result = normalise(
        {
            "id": 123,
            "project_id": 20,
            "project_name": "API project name",
            "start": "2026-10-24T09:00:00+00:00",
            "duration": 3600,
        },
        project_names={
            20: "Local project name",
        },
    )

    assert result.project_name == "API project name"


def test_normalise_calculates_missing_duration():
    result = normalise(
        {
            "id": 123,
            "start": "2026-10-24T09:00:00+00:00",
            "stop": "2026-10-24T10:30:00+00:00",
        }
    )

    assert result.duration_seconds == 5400


def test_normalise_uses_zero_duration_for_running_entry():
    result = normalise(
        {
            "id": 123,
            "start": "2026-10-24T09:00:00+00:00",
            "stop": None,
        }
    )

    assert result.duration_seconds == 0


def test_normalise_preserves_zero_identifiers():
    result = normalise(
        {
            "id": 123,
            "workspace_id": 0,
            "wid": 999,
            "project_id": 0,
            "pid": 999,
            "task_id": 0,
            "tid": 999,
            "start": "2026-10-24T09:00:00+00:00",
        }
    )

    assert result.workspace_id == 0
    assert result.project_id == 0
    assert result.task_id == 0


def test_normalise_defaults_to_empty_tags():
    result = normalise(
        {
            "id": 123,
            "start": "2026-10-24T09:00:00+00:00",
        }
    )

    assert json.loads(result.tags_json) == []


def test_normalise_defaults_to_not_billable():
    result = normalise(
        {
            "id": 123,
            "start": "2026-10-24T09:00:00+00:00",
        }
    )

    assert result.billable == 0


def test_normalise_raises_when_id_is_missing():
    with pytest.raises(
        ValueError,
        match="Toggl entry has no ID",
    ):
        normalise(
            {
                "start": "2026-10-24T09:00:00+00:00",
            }
        )


def test_normalise_raises_when_start_is_missing():
    with pytest.raises(
        ValueError,
        match="Toggl entry has no start time",
    ):
        normalise(
            {
                "id": 123,
            }
        )


def test_normalised_entry_is_compatible_with_database_tuple():
    result = normalise(
        {
            "id": 123,
            "start": "2026-10-24T09:00:00+00:00",
        }
    )

    assert isinstance(result, tuple)
    assert len(result) == 14
