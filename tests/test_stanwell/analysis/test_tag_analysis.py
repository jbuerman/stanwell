from datetime import date

import pytest

from stanwell.analysis.tag_analysis import (
    get_available_tags,
    get_tag_analysis,
    get_weekly_tag_scores,
    has_tag,
)


def insert_entry(
    connection,
    entry_id,
    start_utc,
    duration_seconds,
    tags,
):
    stop_utc = "2026-10-20T11:00:00+00:00"

    connection.execute(
        """
        INSERT INTO time_entries (
            id,
            start_utc,
            stop_utc,
            duration_seconds,
            tags_json,
            raw_json,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry_id,
            start_utc,
            stop_utc,
            duration_seconds,
            "[]",
            "{}",
            "2026-10-20T12:00:00+00:00",
        ),
    )

    connection.executemany(
        """
        INSERT INTO time_entry_tags (
            time_entry_id,
            tag
        )
        VALUES (?, ?)
        """,
        [
            (
                entry_id,
                tag,
            )
            for tag in tags
        ],
    )

    connection.commit()


def test_get_available_tags(conn):
    insert_entry(
        conn,
        1,
        "2026-10-20T10:00:00+00:00",
        3600,
        [
            "development",
            "research",
        ],
    )

    assert get_available_tags(conn) == [
        "development",
        "research",
    ]


def test_get_weekly_tag_scores_good_entry(conn):
    insert_entry(
        conn,
        1,
        "2026-10-20T10:00:00+00:00",
        3600,
        ["good"],
    )

    result = get_weekly_tag_scores(
        connection=conn,
        config={"timezone": "Europe/London"},
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 20),
        good_tags=["good"],
        bad_tags=[],
    )

    row = result.iloc[0]

    assert row["total_hours"] == pytest.approx(1.0)
    assert row["good_hours"] == pytest.approx(1.0)
    assert row["weekly_quality"] == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("policy", "expected_quality"),
    [
        ("neutral", 50.0),
        ("bad_wins", 0.0),
        ("good_wins", 100.0),
    ],
)
def test_conflict_policy(
    conn,
    policy,
    expected_quality,
):
    insert_entry(
        conn,
        1,
        "2026-10-20T10:00:00+00:00",
        3600,
        [
            "good",
            "bad",
        ],
    )

    result = get_weekly_tag_scores(
        connection=conn,
        config={"timezone": "Europe/London"},
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 20),
        good_tags=["good"],
        bad_tags=["bad"],
        conflict_policy=policy,
    )

    assert result.iloc[0]["weekly_quality"] == pytest.approx(expected_quality)


def test_tag_analysis_retains_only_selected_tags(conn):
    insert_entry(
        conn,
        1,
        "2026-10-20T10:00:00+00:00",
        3600,
        [
            "research",
            "development",
        ],
    )

    result = get_tag_analysis(
        connection=conn,
        config={"timezone": "Europe/London"},
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 20),
        selected_tags=["research"],
    )

    assert len(result) == 1
    assert result.iloc[0]["selected_tags"] == {"research"}


def test_has_tag():
    assert has_tag(
        {"research", "development"},
        "research",
    )


def test_has_tag_returns_false_when_missing():
    assert (
        has_tag(
            {"research"},
            "development",
        )
        is False
    )
