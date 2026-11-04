from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from stanwell.ui.dashboard.tabs import (
    work_patterns,
)
from stanwell.ui.dashboard.tabs.work_patterns import SCORE_LABELS


def make_pattern(
    *,
    total_hours: float = 10.0,
    normal_hours: float = 7.0,
    outside_core_hours: float = 1.0,
    weekend_hours: float = 1.0,
    non_working_day_hours: float = 1.0,
):
    return {
        "total_hours": total_hours,
        "normal_hours": normal_hours,
        "outside_core_hours": outside_core_hours,
        "weekend_hours": weekend_hours,
        "non_working_day_hours": (non_working_day_hours),
    }


def test_prepare_pattern_data():
    pattern = make_pattern()

    result = work_patterns._prepare_pattern_data(pattern)

    assert list(result["category"]) == [
        "Normal working hours",
        "Outside core hours",
        "Weekend",
        "Day off / holiday",
    ]

    assert list(result["hours"]) == pytest.approx(
        [
            7.0,
            1.0,
            1.0,
            1.0,
        ]
    )

    assert list(result["percent"]) == pytest.approx(
        [
            70.0,
            10.0,
            10.0,
            10.0,
        ]
    )


def test_prepare_pattern_data_removes_zero_categories():
    pattern = make_pattern(
        normal_hours=8.0,
        outside_core_hours=2.0,
        weekend_hours=0.0,
        non_working_day_hours=0.0,
    )

    result = work_patterns._prepare_pattern_data(pattern)

    assert list(result["category"]) == [
        "Normal working hours",
        "Outside core hours",
    ]


def test_prepare_pattern_data_handles_no_hours():
    pattern = make_pattern(
        total_hours=0.0,
        normal_hours=0.0,
        outside_core_hours=0.0,
        weekend_hours=0.0,
        non_working_day_hours=0.0,
    )

    result = work_patterns._prepare_pattern_data(pattern)

    assert result.empty


def test_prepare_score_trend():
    scores = pd.DataFrame(
        {
            "week_start": [
                pd.Timestamp("2026-10-19"),
            ],
            "weekend_score": [90.0],
            "core_hours_score": [80.0],
            "day_off_score": [100.0],
            "overall_score": [75.0],
        }
    )

    result = work_patterns._prepare_score_trend(scores)

    assert len(result) == len(SCORE_LABELS)

    assert set(result["measure"]) == {
        "Weekend",
        "Core hours",
        "Day off / holiday",
        "Overall",
    }

    overall = result[result["measure"] == "Overall"].iloc[0]

    assert overall["score"] == pytest.approx(75.0)


def test_prepare_undesirable_time_trend():
    weekly_scores = pd.DataFrame(
        {
            "week_start": [
                pd.Timestamp("2026-10-19"),
            ],
            "weekend_share": [0.10],
            "outside_core_share": [0.20],
            "non_working_day_share": [0.05],
        }
    )

    result = work_patterns._prepare_undesirable_time_trend(weekly_scores)

    assert set(result["measure"]) == {
        "Weekend",
        "Outside core hours",
        "Day off / holiday",
    }

    weekend = result[result["measure"] == "Weekend"].iloc[0]

    assert weekend["percent"] == pytest.approx(10.0)


def test_load_long_term_scores(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        config={},
        today=date(2026, 10, 27),
    )

    score_entries = pd.DataFrame(
        {
            "entry_id": [1],
        }
    )

    weekly_patterns = pd.DataFrame(
        {
            "week_start": [
                pd.Timestamp("2026-10-19"),
            ],
            "total_hours": [10.0],
        }
    )

    scored_patterns = pd.DataFrame(
        {
            "overall_score": [80.0],
        }
    )

    calculate_mock = Mock(
        return_value=(
            score_entries,
            pd.DataFrame(),
        )
    )

    weekly_mock = Mock(return_value=weekly_patterns)

    scoring_mock = Mock(return_value=scored_patterns)

    monkeypatch.setattr(
        work_patterns,
        "calculate_working_time",
        calculate_mock,
    )
    monkeypatch.setattr(
        work_patterns,
        "get_weekly_working_patterns",
        weekly_mock,
    )
    monkeypatch.setattr(
        work_patterns,
        "add_smoothed_working_scores",
        scoring_mock,
    )

    result = work_patterns._load_long_term_scores(context)

    assert result is scored_patterns

    calculate_mock.assert_called_once_with(
        context.connection,
        context.config,
        "2025-10-27",
        "2026-10-27",
    )

    weekly_mock.assert_called_once_with(
        entries=score_entries,
        start_date=date(2025, 10, 27),
        end_date=date(2026, 10, 27),
        connection=context.connection,
    )

    scoring_mock.assert_called_once_with(
        weekly_patterns,
        half_life_weeks=6.0,
        minimum_week_hours=1.0,
    )


def test_render_work_patterns_uses_selected_period(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        config={
            "core_start": "10:00",
            "core_end": "16:00",
        },
        today=date(2026, 10, 27),
    )

    period_entries = pd.DataFrame(
        {
            "entry_id": [1],
        }
    )

    pattern = make_pattern()

    get_pattern_mock = Mock(return_value=pattern)

    weekly_score_data = pd.DataFrame()

    monkeypatch.setattr(
        work_patterns,
        "get_working_pattern",
        get_pattern_mock,
    )

    monkeypatch.setattr(
        work_patterns,
        "_load_long_term_scores",
        Mock(return_value=weekly_score_data),
    )

    render_metrics_mock = Mock()
    render_breakdown_mock = Mock()
    render_scores_mock = Mock()
    render_trend_mock = Mock()
    render_balance_mock = Mock()

    monkeypatch.setattr(
        work_patterns,
        "_render_pattern_metrics",
        render_metrics_mock,
    )
    monkeypatch.setattr(
        work_patterns,
        "_render_pattern_breakdown",
        render_breakdown_mock,
    )
    monkeypatch.setattr(
        work_patterns,
        "_render_long_term_scores",
        render_scores_mock,
    )
    monkeypatch.setattr(
        work_patterns,
        "_render_undesirable_time_trend",
        render_trend_mock,
    )

    monkeypatch.setattr(
        work_patterns,
        "_render_long_term_balance",
        render_balance_mock,
    )

    monkeypatch.setattr(
        work_patterns.st,
        "header",
        Mock(),
    )
    monkeypatch.setattr(
        work_patterns.st,
        "caption",
        Mock(),
    )

    work_patterns.render_work_patterns(
        context=context,
        period_start=date(
            2026,
            10,
            20,
        ),
        period_end=date(
            2026,
            10,
            27,
        ),
        period_entries=period_entries,
    )

    get_pattern_mock.assert_called_once_with(
        entries=period_entries,
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 27),
        connection=context.connection,
    )

    render_metrics_mock.assert_called_once_with(pattern)
    render_breakdown_mock.assert_called_once_with(pattern)
    render_scores_mock.assert_called_once_with(weekly_score_data)
    render_trend_mock.assert_called_once_with(weekly_score_data)
    render_balance_mock.assert_called_once_with(context)


def test_render_work_patterns_reports_no_selected_data(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        config={
            "core_start": "10:00",
            "core_end": "16:00",
        },
        today=date(2026, 10, 27),
    )

    pattern = make_pattern(
        total_hours=0.0,
        normal_hours=0.0,
        outside_core_hours=0.0,
        weekend_hours=0.0,
        non_working_day_hours=0.0,
    )

    monkeypatch.setattr(
        work_patterns,
        "get_working_pattern",
        Mock(return_value=pattern),
    )

    monkeypatch.setattr(
        work_patterns,
        "_load_long_term_scores",
        Mock(return_value=pd.DataFrame()),
    )

    render_metrics_mock = Mock()
    render_breakdown_mock = Mock()

    monkeypatch.setattr(
        work_patterns,
        "_render_pattern_metrics",
        render_metrics_mock,
    )
    monkeypatch.setattr(
        work_patterns,
        "_render_pattern_breakdown",
        render_breakdown_mock,
    )

    monkeypatch.setattr(
        work_patterns,
        "_render_long_term_scores",
        Mock(),
    )
    monkeypatch.setattr(
        work_patterns,
        "_render_undesirable_time_trend",
        Mock(),
    )

    monkeypatch.setattr(
        work_patterns,
        "_render_long_term_balance",
        Mock(),
    )

    monkeypatch.setattr(
        work_patterns.st,
        "header",
        Mock(),
    )
    monkeypatch.setattr(
        work_patterns.st,
        "caption",
        Mock(),
    )

    info_mock = Mock()

    monkeypatch.setattr(
        work_patterns.st,
        "info",
        info_mock,
    )

    work_patterns.render_work_patterns(
        context=context,
        period_start=date(
            2026,
            10,
            20,
        ),
        period_end=date(
            2026,
            10,
            27,
        ),
        period_entries=pd.DataFrame(),
    )

    info_mock.assert_any_call(
        "There is no synced working-time " "data for the selected period."
    )

    render_metrics_mock.assert_not_called()
    render_breakdown_mock.assert_not_called()


def test_render_long_term_scores_reports_no_scores(
    monkeypatch,
):
    score_data = pd.DataFrame(
        columns=[
            "weekend_score",
            "core_hours_score",
            "day_off_score",
            "overall_score",
        ]
    )

    monkeypatch.setattr(
        work_patterns.st,
        "markdown",
        Mock(),
    )
    monkeypatch.setattr(
        work_patterns.st,
        "caption",
        Mock(),
    )

    info_mock = Mock()

    monkeypatch.setattr(
        work_patterns.st,
        "info",
        info_mock,
    )

    work_patterns._render_long_term_scores(score_data)

    info_mock.assert_called_once_with(
        "There is not yet enough synced data " "to calculate a working-pattern score."
    )


def test_render_undesirable_time_trend_handles_empty_data(
    monkeypatch,
):
    info_mock = Mock()

    monkeypatch.setattr(
        work_patterns.st,
        "markdown",
        Mock(),
    )
    monkeypatch.setattr(
        work_patterns.st,
        "info",
        info_mock,
    )

    work_patterns._render_undesirable_time_trend(pd.DataFrame())

    info_mock.assert_called_once_with(
        "There is not yet enough synced data " "to show weekly working-time trends."
    )


def test_prepare_weekly_balance_history():
    daily_summary = pd.DataFrame(
        {
            "week_start": pd.to_datetime(
                [
                    "2026-10-19",
                    "2026-10-19",
                    "2026-10-19",
                    "2026-10-26",
                ]
            ),
            "actual_hours": [
                9.0,
                6.0,
                0.0,
                8.0,
            ],
            "expected_hours": [
                7.5,
                7.5,
                0.0,
                7.5,
            ],
            "balance_adjustment_hours": [
                0.0,
                0.0,
                -7.5,
                0.0,
            ],
        }
    )

    result = work_patterns._prepare_weekly_balance_history(daily_summary)

    assert len(result) == 2

    first_week = result.iloc[0]
    assert first_week["overtime_hours"] == pytest.approx(1.5)
    assert first_week["shortfall_hours"] == pytest.approx(-1.5)
    assert first_week["compensation_hours"] == pytest.approx(-7.5)
    assert first_week["weekly_balance_hours"] == pytest.approx(-7.5)
    assert first_week["cumulative_balance_hours"] == pytest.approx(-7.5)

    second_week = result.iloc[1]
    assert second_week["overtime_hours"] == pytest.approx(0.5)
    assert second_week["shortfall_hours"] == pytest.approx(0.0)
    assert second_week["compensation_hours"] == pytest.approx(0.0)
    assert second_week["weekly_balance_hours"] == pytest.approx(0.5)
    assert second_week["cumulative_balance_hours"] == pytest.approx(-7.0)


def test_load_long_term_balance(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        config={},
        today=date(2026, 10, 27),
    )

    daily_summary = pd.DataFrame(
        {
            "week_start": [
                pd.Timestamp("2026-10-19"),
            ],
            "actual_hours": [7.5],
            "expected_hours": [7.5],
            "balance_adjustment_hours": [0.0],
        }
    )

    calculate_mock = Mock(
        return_value=(
            pd.DataFrame(),
            daily_summary,
        )
    )

    monkeypatch.setattr(
        work_patterns,
        "calculate_working_time",
        calculate_mock,
    )

    result = work_patterns._load_long_term_balance(context)

    assert result is daily_summary

    calculate_mock.assert_called_once_with(
        context.connection,
        context.config,
        "2025-10-27",
        "2026-10-27",
    )
