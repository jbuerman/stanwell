from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

import pandas as pd
import pytest

from stanwell.analysis.working_time import (
    SEGMENT_COLUMNS,
    calculate_working_time,
    load_time_segments,
)


@pytest.fixture
def working_time_config() -> dict[str, Any]:
    return {
        "timezone": "Europe/London",
        "core_start": "10:00",
        "core_end": "16:00",
        "workday_hours": 7.5,
        "working_days": [0, 1, 2, 3, 4],
    }


def insert_time_entry(
    connection: sqlite3.Connection,
    *,
    entry_id: int,
    start_utc: str,
    stop_utc: str | None,
    duration_seconds: int,
    description: str = "Test entry",
) -> None:
    """Insert a complete test time entry.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the test database.
    entry_id : int
        Identifier for the time entry.
    start_utc : str
        Entry start timestamp.
    stop_utc : str or None
        Entry stop timestamp.
    duration_seconds : int
        Recorded entry duration.
    description : str, default="Test entry"
        Entry description.
    """
    raw_entry = {
        "id": entry_id,
        "start": start_utc,
        "stop": stop_utc,
        "duration": duration_seconds,
        "description": description,
    }

    connection.execute(
        """
        INSERT INTO time_entries (
            id,
            description,
            start_utc,
            stop_utc,
            duration_seconds,
            raw_json,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry_id,
            description,
            start_utc,
            stop_utc,
            duration_seconds,
            json.dumps(raw_entry),
            "2026-10-24T12:00:00+00:00",
        ),
    )
    connection.commit()


def insert_day_exception(
    connection: sqlite3.Connection,
    day: str,
    kind: str,
    note: str,
) -> None:
    """Insert a day exception into the test database.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the test database.
    day : str
        Exception date in ISO format.
    kind : str
        Exception kind.
    note : str
        Human-readable description of the exception.
    """
    connection.execute(
        """
        INSERT INTO day_exceptions (
            day,
            kind,
            note
        )
        VALUES (?, ?, ?)
        """,
        (day, kind, note),
    )
    connection.commit()


def get_daily_row(
    daily_summary: pd.DataFrame,
    day: str,
) -> pd.Series:
    """Return one daily-summary row.

    Parameters
    ----------
    daily_summary : pandas.DataFrame
        Daily working-time summary.
    day : str
        Date to retrieve, in ISO format.

    Returns
    -------
    pandas.Series
        Matching daily-summary row.
    """
    matching_rows = daily_summary[daily_summary["day"].astype(str) == day]

    assert len(matching_rows) == 1

    return matching_rows.iloc[0]


class TestLoadTimeSegments:
    def test_empty_database_returns_expected_columns(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        segments = load_time_segments(
            conn,
            working_time_config,
        )

        assert segments.empty
        assert list(segments.columns) == SEGMENT_COLUMNS

    def test_entry_partly_outside_core_hours(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=1,
            start_utc="2026-01-05T09:00:00+00:00",
            stop_utc="2026-01-05T12:00:00+00:00",
            duration_seconds=3 * 3600,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        assert len(segments) == 1

        segment = segments.iloc[0]

        assert segment["entry_id"] == 1
        assert segment["day"] == "2026-01-05"
        assert segment["weekday"] == "Monday"
        assert segment["seconds"] == pytest.approx(3 * 3600)
        assert segment["outside_core_seconds"] == pytest.approx(3600)
        assert segment["weekend_seconds"] == pytest.approx(0)

    def test_entry_completely_inside_core_hours(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=2,
            start_utc="2026-01-05T11:00:00+00:00",
            stop_utc="2026-01-05T12:00:00+00:00",
            duration_seconds=3600,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        segment = segments.iloc[0]

        assert segment["seconds"] == pytest.approx(3600)
        assert segment["outside_core_seconds"] == pytest.approx(0)

    def test_entry_completely_outside_core_hours(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=3,
            start_utc="2026-01-05T07:00:00+00:00",
            stop_utc="2026-01-05T09:00:00+00:00",
            duration_seconds=2 * 3600,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        segment = segments.iloc[0]

        assert segment["seconds"] == pytest.approx(2 * 3600)
        assert segment["outside_core_seconds"] == pytest.approx(2 * 3600)

    def test_entry_crossing_midnight_is_split(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=4,
            start_utc="2026-01-05T23:00:00+00:00",
            stop_utc="2026-01-06T01:00:00+00:00",
            duration_seconds=2 * 3600,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        assert len(segments) == 2
        assert list(segments["day"]) == [
            "2026-01-05",
            "2026-01-06",
        ]
        assert list(segments["seconds"]) == pytest.approx(
            [
                3600,
                3600,
            ]
        )
        assert list(segments["outside_core_seconds"]) == pytest.approx(
            [
                3600,
                3600,
            ]
        )

    def test_weekend_segment_counts_all_time_as_weekend(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=5,
            start_utc="2026-01-10T11:00:00+00:00",
            stop_utc="2026-01-10T12:00:00+00:00",
            duration_seconds=3600,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        segment = segments.iloc[0]

        assert segment["weekday"] == "Saturday"
        assert segment["seconds"] == pytest.approx(3600)
        assert segment["weekend_seconds"] == pytest.approx(3600)

    def test_utc_timestamp_is_converted_to_local_date(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=6,
            start_utc="2026-06-01T23:30:00+00:00",
            stop_utc="2026-06-02T00:30:00+00:00",
            duration_seconds=3600,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        assert len(segments) == 1

        segment = segments.iloc[0]

        assert segment["day"] == "2026-06-02"
        assert segment["weekday"] == "Tuesday"
        assert segment["start_local"].hour == 0
        assert segment["start_local"].minute == 30
        assert segment["stop_local"].hour == 1
        assert segment["stop_local"].minute == 30

    def test_entry_crossing_start_of_daylight_saving_time(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=13,
            start_utc="2026-03-29T00:30:00+00:00",
            stop_utc="2026-03-29T01:30:00+00:00",
            duration_seconds=3600,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        assert len(segments) == 1

        segment = segments.iloc[0]

        assert segment["day"] == "2026-03-29"
        assert segment["start_local"].hour == 0
        assert segment["start_local"].minute == 30
        assert segment["stop_local"].hour == 2
        assert segment["stop_local"].minute == 30
        assert segment["seconds"] == pytest.approx(3600)

    def test_entry_crossing_end_of_daylight_saving_time(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=14,
            start_utc="2026-10-25T00:30:00+00:00",
            stop_utc="2026-10-25T01:30:00+00:00",
            duration_seconds=3600,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        assert len(segments) == 1

        segment = segments.iloc[0]

        assert segment["day"] == "2026-10-25"
        assert segment["start_local"].hour == 1
        assert segment["start_local"].minute == 30
        assert segment["stop_local"].hour == 1
        assert segment["stop_local"].minute == 30
        assert segment["seconds"] == pytest.approx(3600)

    def test_running_entry_without_stop_time_is_excluded(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=7,
            start_utc="2026-01-05T09:00:00+00:00",
            stop_utc=None,
            duration_seconds=0,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        assert segments.empty

    def test_negative_duration_entry_is_excluded(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=8,
            start_utc="2026-01-05T09:00:00+00:00",
            stop_utc="2026-01-05T10:00:00+00:00",
            duration_seconds=-1,
        )

        segments = load_time_segments(
            conn,
            working_time_config,
        )

        assert segments.empty


class TestCalculateWorkingTime:
    def test_creates_row_for_every_requested_day(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        segments, daily_summary = calculate_working_time(
            connection=conn,
            config=working_time_config,
            start_day="2026-01-05",
            end_day="2026-01-11",
        )

        assert segments.empty
        assert list(daily_summary["day"].astype(str)) == [
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
            "2026-01-09",
            "2026-01-10",
            "2026-01-11",
        ]

    def test_working_days_have_expected_hours(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        _, daily_summary = calculate_working_time(
            connection=conn,
            config=working_time_config,
            start_day="2026-01-05",
            end_day="2026-01-11",
        )

        expected_hours = list(daily_summary["expected_hours"])

        assert expected_hours == [
            7.5,
            7.5,
            7.5,
            7.5,
            7.5,
            0.0,
            0.0,
        ]

    @pytest.mark.parametrize(
        (
            "kind",
            "expected_hours",
            "balance_adjustment_hours",
            "balance_hours",
        ),
        [
            ("sick", 0.0, 0.0, 0.0),
            ("annual_leave", 0.0, 0.0, 0.0),
            ("public_holiday", 0.0, 0.0, 0.0),
            ("closure_day", 0.0, 0.0, 0.0),
            ("overtime_compensation", 0.0, -7.5, -7.5),
        ],
    )
    def test_working_day_exception_affects_balance_correctly(
        self,
        conn,
        working_time_config: Mapping[str, Any],
        kind: str,
        expected_hours: float,
        balance_adjustment_hours: float,
        balance_hours: float,
    ):
        insert_day_exception(
            conn,
            day="2026-01-08",
            kind=kind,
            note="Test exception",
        )

        _, daily_summary = calculate_working_time(
            connection=conn,
            config=working_time_config,
            start_day="2026-01-08",
            end_day="2026-01-08",
        )

        day = get_daily_row(
            daily_summary,
            "2026-01-08",
        )

        assert day["expected_hours"] == pytest.approx(expected_hours)
        assert day["actual_hours"] == pytest.approx(0.0)
        assert day["balance_adjustment_hours"] == pytest.approx(
            balance_adjustment_hours
        )
        assert day["balance_hours"] == pytest.approx(balance_hours)

    def test_work_on_overtime_compensation_day_offsets_balance_adjustment(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_day_exception(
            conn,
            day="2026-01-09",
            kind="overtime_compensation",
            note="Overtime compensation",
        )

        insert_time_entry(
            conn,
            entry_id=15,
            start_utc="2026-01-09T10:00:00+00:00",
            stop_utc="2026-01-09T12:00:00+00:00",
            duration_seconds=2 * 3600,
        )

        _, daily_summary = calculate_working_time(
            connection=conn,
            config=working_time_config,
            start_day="2026-01-09",
            end_day="2026-01-09",
        )

        day = get_daily_row(
            daily_summary,
            "2026-01-09",
        )

        assert day["expected_hours"] == pytest.approx(0.0)
        assert day["actual_hours"] == pytest.approx(2.0)
        assert day["balance_adjustment_hours"] == pytest.approx(-7.5)
        assert day["balance_hours"] == pytest.approx(-5.5)

    def test_overtime_compensation_on_non_working_day_has_no_balance_adjustment(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_day_exception(
            conn,
            day="2026-01-10",
            kind="overtime_compensation",
            note="Overtime compensation",
        )

        _, daily_summary = calculate_working_time(
            connection=conn,
            config=working_time_config,
            start_day="2026-01-10",
            end_day="2026-01-10",
        )

        day = get_daily_row(
            daily_summary,
            "2026-01-10",
        )

        assert day["expected_hours"] == pytest.approx(0.0)
        assert day["actual_hours"] == pytest.approx(0.0)
        assert day["balance_adjustment_hours"] == pytest.approx(0.0)
        assert day["balance_hours"] == pytest.approx(0.0)

    def test_actual_and_balance_hours_are_calculated(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=9,
            start_utc="2026-01-05T10:00:00+00:00",
            stop_utc="2026-01-05T14:00:00+00:00",
            duration_seconds=4 * 3600,
        )

        _, daily_summary = calculate_working_time(
            connection=conn,
            config=working_time_config,
            start_day="2026-01-05",
            end_day="2026-01-05",
        )

        day = get_daily_row(
            daily_summary,
            "2026-01-05",
        )

        assert day["seconds"] == pytest.approx(4 * 3600)
        assert day["actual_hours"] == pytest.approx(4.0)
        assert day["expected_hours"] == pytest.approx(7.5)
        assert day["balance_hours"] == pytest.approx(-3.5)

    def test_day_without_entries_has_zero_actual_hours(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        _, daily_summary = calculate_working_time(
            connection=conn,
            config=working_time_config,
            start_day="2026-01-05",
            end_day="2026-01-05",
        )

        day = get_daily_row(
            daily_summary,
            "2026-01-05",
        )

        assert day["seconds"] == pytest.approx(0)
        assert day["actual_hours"] == pytest.approx(0)
        assert day["balance_hours"] == pytest.approx(-7.5)

    def test_segments_are_restricted_to_requested_range(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        insert_time_entry(
            conn,
            entry_id=10,
            start_utc="2026-01-04T11:00:00+00:00",
            stop_utc="2026-01-04T12:00:00+00:00",
            duration_seconds=3600,
        )
        insert_time_entry(
            conn,
            entry_id=11,
            start_utc="2026-01-05T11:00:00+00:00",
            stop_utc="2026-01-05T12:00:00+00:00",
            duration_seconds=3600,
        )
        insert_time_entry(
            conn,
            entry_id=12,
            start_utc="2026-01-06T11:00:00+00:00",
            stop_utc="2026-01-06T12:00:00+00:00",
            duration_seconds=3600,
        )

        segments, _ = calculate_working_time(
            connection=conn,
            config=working_time_config,
            start_day="2026-01-05",
            end_day="2026-01-05",
        )

        assert list(segments["entry_id"]) == [11]

    def test_week_start_is_monday(
        self,
        conn,
        working_time_config: Mapping[str, Any],
    ):
        _, daily_summary = calculate_working_time(
            connection=conn,
            config=working_time_config,
            start_day="2026-01-07",
            end_day="2026-01-11",
        )

        assert set(daily_summary["week_start"].dt.strftime("%Y-%m-%d")) == {
            "2026-01-05"
        }
