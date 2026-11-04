from datetime import date

import pandas as pd
import pytest

from stanwell.analysis.working_patterns import (
    get_weekly_working_patterns,
    get_working_pattern,
)


def make_entries(
    rows: list[dict],
) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_get_working_pattern_empty_entries(conn):
    result = get_working_pattern(
        entries=pd.DataFrame(),
        start_date=date(2026, 10, 19),
        end_date=date(2026, 10, 25),
        connection=conn,
    )

    assert result == {
        "total_hours": 0.0,
        "outside_core_hours": 0.0,
        "weekend_hours": 0.0,
        "non_working_day_hours": 0.0,
        "normal_hours": 0.0,
    }


def test_get_working_pattern_normal_weekday(conn):
    entries = make_entries(
        [
            {
                "day": "2026-10-20",
                "seconds": 7200,
                "outside_core_seconds": 0,
                "weekend_seconds": 0,
            }
        ]
    )

    result = get_working_pattern(
        entries=entries,
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 20),
        connection=conn,
    )

    assert result["total_hours"] == pytest.approx(2.0)
    assert result["normal_hours"] == pytest.approx(2.0)
    assert result["outside_core_hours"] == pytest.approx(0.0)


def test_get_working_pattern_outside_core(conn):
    entries = make_entries(
        [
            {
                "day": "2026-10-20",
                "seconds": 7200,
                "outside_core_seconds": 3600,
                "weekend_seconds": 0,
            }
        ]
    )

    result = get_working_pattern(
        entries=entries,
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 20),
        connection=conn,
    )

    assert result["outside_core_hours"] == pytest.approx(1.0)
    assert result["normal_hours"] == pytest.approx(1.0)


def test_get_working_pattern_weekend_is_exclusive(conn):
    entries = make_entries(
        [
            {
                "day": "2026-10-24",
                "seconds": 7200,
                "outside_core_seconds": 7200,
                "weekend_seconds": 7200,
            }
        ]
    )

    result = get_working_pattern(
        entries=entries,
        start_date=date(2026, 10, 24),
        end_date=date(2026, 10, 24),
        connection=conn,
    )

    assert result["weekend_hours"] == pytest.approx(2.0)
    assert result["outside_core_hours"] == pytest.approx(0.0)
    assert result["normal_hours"] == pytest.approx(0.0)


def test_non_working_day_has_priority_over_weekend(conn):
    conn.execute(
        """
        INSERT INTO day_exceptions (
            day,
            kind,
            note
        )
        VALUES (?, ?, ?)
        """,
        (
            "2026-10-24",
            "annual_leave",
            None,
        ),
    )
    conn.commit()

    entries = make_entries(
        [
            {
                "day": "2026-10-24",
                "seconds": 7200,
                "outside_core_seconds": 7200,
                "weekend_seconds": 7200,
            }
        ]
    )

    result = get_working_pattern(
        entries=entries,
        start_date=date(2026, 10, 24),
        end_date=date(2026, 10, 24),
        connection=conn,
    )

    assert result["non_working_day_hours"] == pytest.approx(2.0)
    assert result["weekend_hours"] == pytest.approx(0.0)
    assert result["outside_core_hours"] == pytest.approx(0.0)


def test_sick_day_is_not_classified_as_non_working(conn):
    conn.execute(
        """
        INSERT INTO day_exceptions (
            day,
            kind,
            note
        )
        VALUES (?, ?, ?)
        """,
        (
            "2026-10-20",
            "sick",
            None,
        ),
    )
    conn.commit()

    entries = make_entries(
        [
            {
                "day": "2026-10-20",
                "seconds": 3600,
                "outside_core_seconds": 0,
                "weekend_seconds": 0,
            }
        ]
    )

    result = get_working_pattern(
        entries=entries,
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 20),
        connection=conn,
    )

    assert result["non_working_day_hours"] == pytest.approx(0.0)
    assert result["normal_hours"] == pytest.approx(1.0)


def test_get_weekly_working_patterns_groups_by_monday(
    conn,
):
    entries = make_entries(
        [
            {
                "day": "2026-10-19",
                "seconds": 3600,
                "outside_core_seconds": 0,
                "weekend_seconds": 0,
            },
            {
                "day": "2026-10-20",
                "seconds": 7200,
                "outside_core_seconds": 3600,
                "weekend_seconds": 0,
            },
        ]
    )

    weekly = get_weekly_working_patterns(
        entries=entries,
        start_date=date(2026, 10, 19),
        end_date=date(2026, 10, 20),
        connection=conn,
    )

    assert len(weekly) == 1
    assert weekly.iloc[0]["week_start"].date() == date(2026, 10, 19)
    assert weekly.iloc[0]["total_hours"] == pytest.approx(3.0)
    assert weekly.iloc[0]["normal_hours"] == pytest.approx(2.0)
    assert weekly.iloc[0]["outside_core_hours"] == pytest.approx(1.0)
