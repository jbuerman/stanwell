import math
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from stanwell.ui.dashboard.tabs import (
    overview,
)


def test_calculate_totals():
    daily_summary = pd.DataFrame(
        {
            "actual_hours": [
                7.5,
                8.0,
                0.0,
            ],
            "expected_hours": [
                7.5,
                7.5,
                0.0,
            ],
            "balance_adjustment_hours": [
                0.0,
                0.0,
                -7.5,
            ],
            "balance_hours": [
                0.0,
                0.5,
                -7.5,
            ],
        }
    )

    result = overview._calculate_totals(
        daily_summary=daily_summary,
        workday_hours=7.5,
    )

    assert result.actual_hours == pytest.approx(15.5)
    assert result.expected_hours == pytest.approx(15.0)
    assert result.compensation_hours == pytest.approx(7.5)
    assert result.compensation_equivalent_days == pytest.approx(1.0)
    assert result.balance_hours == pytest.approx(-7.0)
    assert result.equivalent_days == pytest.approx(15.5 / 7.5)
    assert result.balance_equivalent_days == pytest.approx(-7.0 / 7.5)


def test_calculate_totals_with_zero_workday_hours():
    daily_summary = pd.DataFrame(
        {
            "actual_hours": [5.0],
            "expected_hours": [7.5],
            "balance_adjustment_hours": [0.0],
            "balance_hours": [-2.5],
        }
    )

    result = overview._calculate_totals(
        daily_summary=daily_summary,
        workday_hours=0.0,
    )

    assert math.isnan(result.equivalent_days)
    assert math.isnan(result.compensation_equivalent_days)
    assert math.isnan(result.balance_equivalent_days)


def test_prepare_daily_chart_data():
    daily_summary = pd.DataFrame(
        {
            "day": [
                date(2026, 10, 19),
            ],
            "week_start": [
                date(2026, 10, 19),
            ],
            "actual_hours": ["7.5"],
            "expected_hours": ["bad"],
            "balance_adjustment_hours": ["-7.5"],
            "balance_hours": [None],
        }
    )

    result = overview._prepare_daily_chart_data(daily_summary)

    assert pd.api.types.is_datetime64_any_dtype(result["day"])
    assert pd.api.types.is_datetime64_any_dtype(result["week_start"])
    assert result.iloc[0]["actual_hours"] == pytest.approx(7.5)
    assert result.iloc[0]["expected_hours"] == pytest.approx(0.0)
    assert result.iloc[0]["balance_adjustment_hours"] == pytest.approx(-7.5)
    assert result.iloc[0]["compensation_hours"] == pytest.approx(7.5)
    assert result.iloc[0]["balance_hours"] == pytest.approx(0.0)


def test_create_weekly_summary():
    daily_chart_data = pd.DataFrame(
        {
            "week_start": pd.to_datetime(
                [
                    "2026-10-19",
                    "2026-10-19",
                    "2026-10-26",
                ]
            ),
            "actual_hours": [
                7.5,
                8.0,
                6.0,
            ],
            "expected_hours": [
                7.5,
                7.5,
                7.5,
            ],
            "balance_hours": [
                0.0,
                0.5,
                -1.5,
            ],
        }
    )

    result = overview._create_weekly_summary(daily_chart_data)

    assert len(result) == 2

    first_week = result.iloc[0]

    assert first_week["actual_hours"] == pytest.approx(15.5)

    assert first_week["expected_hours"] == pytest.approx(15.0)

    assert first_week["balance_hours"] == pytest.approx(0.5)

    assert first_week["week_label"] == "19 Oct"


def test_create_weekday_summary():
    daily_summary = pd.DataFrame(
        {
            "weekday": [
                "Monday",
                "Monday",
                "Tuesday",
            ],
            "actual_hours": [
                6.0,
                8.0,
                5.0,
            ],
        }
    )

    result = overview._create_weekday_summary(daily_summary)

    monday = result[result["weekday"] == "Monday"].iloc[0]

    tuesday = result[result["weekday"] == "Tuesday"].iloc[0]

    assert monday["average_hours"] == pytest.approx(7.0)

    assert monday["std_dev"] == pytest.approx(2.0**0.5)

    assert monday["days"] == 2

    assert tuesday["average_hours"] == pytest.approx(5.0)

    assert tuesday["std_dev"] == pytest.approx(0.0)

    assert tuesday["days"] == 1


def test_create_weekday_summary_contains_all_weekdays():
    daily_summary = pd.DataFrame(
        {
            "weekday": ["Monday"],
            "actual_hours": [7.5],
        }
    )

    result = overview._create_weekday_summary(daily_summary)

    assert list(result["weekday"]) == overview.WEEKDAY_ORDER


def test_prepare_weekday_table():
    weekday_summary = pd.DataFrame(
        {
            "weekday": ["Monday"],
            "average_hours": [7.456],
            "std_dev": [1.234],
            "days": [3],
        }
    )

    result = overview._prepare_weekday_table(weekday_summary)

    assert list(result.columns) == [
        "Weekday",
        "Average hours",
        "Standard deviation",
        "Days in period",
    ]

    assert result.iloc[0]["Average hours"] == pytest.approx(7.5)

    assert result.iloc[0]["Standard deviation"] == pytest.approx(1.2)


def test_render_overview_returns_period_entries(
    monkeypatch,
):
    period_entries = pd.DataFrame(
        {
            "entry_id": [123],
        }
    )

    daily_summary = pd.DataFrame(
        {
            "day": [
                date(2026, 10, 20),
            ],
            "weekday": ["Tuesday"],
            "actual_hours": [7.5],
            "expected_hours": [7.5],
            "balance_adjustment_hours": [0.0],
            "balance_hours": [0.0],
            "week_start": [pd.Timestamp("2026-10-19")],
        }
    )

    context = SimpleNamespace(
        connection=Mock(),
        config={},
        today=date(2026, 10, 27),
        workday_hours=7.5,
    )

    calls = []

    def fake_calculate_working_time(
        connection,
        config,
        start_day,
        end_day,
    ):
        calls.append(
            (
                start_day,
                end_day,
            )
        )

        return (
            period_entries,
            daily_summary,
        )

    monkeypatch.setattr(
        overview,
        "calculate_working_time",
        fake_calculate_working_time,
    )

    monkeypatch.setattr(
        overview,
        "_render_today_summary",
        Mock(),
    )

    monkeypatch.setattr(
        overview,
        "_render_period_metrics",
        Mock(),
    )

    monkeypatch.setattr(
        overview,
        "_render_daily_and_weekly_charts",
        Mock(),
    )

    monkeypatch.setattr(
        overview,
        "_render_weekday_pattern",
        Mock(),
    )

    render_projection_mock = Mock()

    monkeypatch.setattr(
        overview,
        "_render_week_remaining_projection",
        render_projection_mock,
    )

    result = overview.render_overview(
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
    )

    assert result is period_entries

    assert calls == [
        (
            "2026-10-20",
            "2026-10-27",
        ),
        (
            "2026-10-26",
            "2026-11-01",
        ),
    ]
    render_projection_mock.assert_called_once()
    projection = render_projection_mock.call_args.args[0]

    assert isinstance(
        projection,
        pd.DataFrame,
    )


def test_render_week_remaining_projection_reports_no_remaining_days(
    monkeypatch,
):
    info_mock = Mock()

    monkeypatch.setattr(
        overview.st,
        "markdown",
        Mock(),
    )
    monkeypatch.setattr(
        overview.st,
        "caption",
        Mock(),
    )
    monkeypatch.setattr(
        overview.st,
        "info",
        info_mock,
    )

    overview._render_week_remaining_projection(pd.DataFrame())

    info_mock.assert_called_once_with(
        "There are no remaining required working days " "this week."
    )


def test_render_week_remaining_projection_shows_required_hours(
    monkeypatch,
):
    projection = pd.DataFrame(
        {
            "day": [
                date(2026, 11, 5),
                date(2026, 11, 6),
            ],
            "weekday": [
                "Thursday",
                "Friday",
            ],
            "required_hours": [
                6.5,
                6.5,
            ],
        }
    )

    metric_mock = Mock()

    monkeypatch.setattr(
        overview.st,
        "markdown",
        Mock(),
    )
    monkeypatch.setattr(
        overview.st,
        "caption",
        Mock(),
    )
    monkeypatch.setattr(
        overview.st,
        "metric",
        metric_mock,
    )

    metric_columns = [
        Mock(),
        Mock(),
    ]

    for column in metric_columns:
        column.__enter__ = Mock(return_value=column)
        column.__exit__ = Mock(return_value=False)

    monkeypatch.setattr(
        overview.st,
        "columns",
        Mock(return_value=metric_columns),
    )

    overview._render_week_remaining_projection(projection)

    metric_mock.assert_any_call(
        "Still required",
        "13.0 h",
        border=True,
    )

    metric_mock.assert_any_call(
        "Average per remaining day",
        "6.5 h",
        border=True,
    )


def test_render_today_summary_uses_today(
    monkeypatch,
):
    today_entries = pd.DataFrame()
    today_summary = pd.DataFrame(
        {
            "actual_hours": [0.0],
            "expected_hours": [7.5],
            "balance_adjustment_hours": [0.0],
            "balance_hours": [-7.5],
        }
    )

    context = SimpleNamespace(
        connection=Mock(),
        config={},
        today=date(2026, 10, 27),
        workday_hours=7.5,
    )

    calculate_mock = Mock(
        return_value=(
            today_entries,
            today_summary,
        )
    )

    monkeypatch.setattr(
        overview,
        "calculate_working_time",
        calculate_mock,
    )

    monkeypatch.setattr(
        overview.st,
        "subheader",
        Mock(),
    )
    monkeypatch.setattr(
        overview.st,
        "metric",
        Mock(),
    )
    monkeypatch.setattr(
        overview.st,
        "info",
        Mock(),
    )

    metric_columns = [
        Mock(),
        Mock(),
        Mock(),
    ]

    for metric_column in metric_columns:
        metric_column.__enter__ = Mock(return_value=metric_column)
        metric_column.__exit__ = Mock(return_value=False)

    monkeypatch.setattr(
        overview.st,
        "columns",
        Mock(return_value=metric_columns),
    )

    overview._render_today_summary(context)

    calculate_mock.assert_called_once_with(
        context.connection,
        context.config,
        "2026-10-27",
        "2026-10-27",
    )

    overview.st.info.assert_called_once_with(
        "There are currently no synced time " "entries for today."
    )


def test_render_daily_and_weekly_charts_reports_no_data(
    monkeypatch,
):
    info_mock = Mock()

    monkeypatch.setattr(
        overview.st,
        "info",
        info_mock,
    )

    overview._render_daily_and_weekly_charts(pd.DataFrame())

    info_mock.assert_called_once_with(
        "There is no daily data available " "for the selected period."
    )


def test_render_weekday_pattern_reports_no_data(
    monkeypatch,
):
    info_mock = Mock()

    monkeypatch.setattr(
        overview.st,
        "divider",
        Mock(),
    )
    monkeypatch.setattr(
        overview.st,
        "subheader",
        Mock(),
    )
    monkeypatch.setattr(
        overview.st,
        "caption",
        Mock(),
    )
    monkeypatch.setattr(
        overview.st,
        "info",
        info_mock,
    )

    overview._render_weekday_pattern(pd.DataFrame())

    info_mock.assert_called_once_with(
        "There is no weekday data available " "for the selected period."
    )


def test_render_period_metrics_shows_compensation_days(
    monkeypatch,
):
    totals = overview.WorkingTimeTotals(
        actual_hours=15.0,
        expected_hours=15.0,
        compensation_hours=7.5,
        compensation_equivalent_days=1.0,
        balance_hours=-7.5,
        equivalent_days=2.0,
        balance_equivalent_days=-1.0,
    )

    metric_mock = Mock()
    monkeypatch.setattr(overview.st, "divider", Mock())
    monkeypatch.setattr(overview.st, "subheader", Mock())
    monkeypatch.setattr(overview.st, "caption", Mock())
    monkeypatch.setattr(overview.st, "metric", metric_mock)

    metric_columns = [Mock() for _ in range(6)]
    for column in metric_columns:
        column.__enter__ = Mock(return_value=column)
        column.__exit__ = Mock(return_value=False)

    monkeypatch.setattr(
        overview.st,
        "columns",
        Mock(return_value=metric_columns),
    )

    overview._render_period_metrics(
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
        totals=totals,
    )

    metric_mock.assert_any_call(
        "Compensation days",
        "1.0",
        border=True,
    )
