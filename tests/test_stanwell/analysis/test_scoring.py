import pandas as pd
import pytest

from stanwell.analysis.scoring import (
    add_smoothed_tag_score,
    add_smoothed_working_scores,
)


def test_working_scores_perfect_week():
    weekly = pd.DataFrame(
        [
            {
                "week_start": "2026-10-19",
                "total_hours": 37.5,
                "normal_hours": 37.5,
                "outside_core_hours": 0.0,
                "weekend_hours": 0.0,
                "non_working_day_hours": 0.0,
            }
        ]
    )

    result = add_smoothed_working_scores(weekly)

    row = result.iloc[0]

    assert row["weekend_quality"] == pytest.approx(100.0)
    assert row["core_hours_quality"] == pytest.approx(100.0)
    assert row["day_off_quality"] == pytest.approx(100.0)
    assert row["overall_quality"] == pytest.approx(100.0)
    assert row["overall_score"] == pytest.approx(100.0)


def test_working_score_categories_use_hour_shares():
    weekly = pd.DataFrame(
        [
            {
                "week_start": "2026-10-19",
                "total_hours": 10.0,
                "normal_hours": 7.0,
                "outside_core_hours": 1.0,
                "weekend_hours": 2.0,
                "non_working_day_hours": 0.0,
            }
        ]
    )

    result = add_smoothed_working_scores(weekly)

    row = result.iloc[0]

    assert row["weekend_quality"] == pytest.approx(80.0)
    assert row["core_hours_quality"] == pytest.approx(90.0)
    assert row["overall_quality"] == pytest.approx(70.0)


def test_sparse_week_does_not_update_tag_score():
    weekly = pd.DataFrame(
        [
            {
                "week_start": "2026-10-12",
                "total_hours": 10.0,
                "weekly_quality": 80.0,
            },
            {
                "week_start": "2026-10-19",
                "total_hours": 0.5,
                "weekly_quality": 0.0,
            },
        ]
    )

    result = add_smoothed_tag_score(
        weekly,
        minimum_week_hours=1.0,
    )

    assert result.iloc[0]["smoothed_score"] == pytest.approx(80.0)
    assert result.iloc[1]["smoothed_score"] == pytest.approx(80.0)


def test_zero_half_life_is_rejected():
    weekly = pd.DataFrame(
        [
            {
                "week_start": "2026-10-19",
                "total_hours": 10.0,
                "weekly_quality": 80.0,
            }
        ]
    )

    with pytest.raises(
        ValueError,
        match="half_life_weeks",
    ):
        add_smoothed_tag_score(
            weekly,
            half_life_weeks=0,
        )
