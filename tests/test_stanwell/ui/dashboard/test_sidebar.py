from datetime import date
from unittest.mock import Mock

import pytest

from stanwell.ui.dashboard.context import (
    DashboardContext,
)
from stanwell.ui.dashboard.sidebar import (
    AnalysisPeriod,
    _custom_period,
    _default_custom_start,
    _normalise_period,
    _preset_period,
    render_sidebar,
)


def make_context(
    *,
    today: date = date(2026, 10, 27),
    earliest_data: date | None = None,
    latest_data: date | None = None,
    workday_hours: float = 7.5,
) -> DashboardContext:
    return DashboardContext(
        config={},
        connection=Mock(),
        workday_hours=workday_hours,
        today=today,
        earliest_data=earliest_data,
        latest_data=latest_data,
    )


@pytest.mark.parametrize(
    (
        "period_option",
        "expected_start",
    ),
    [
        (
            "This week",
            date(2026, 10, 26),
        ),
        (
            "Last 2 weeks",
            date(2026, 10, 19),
        ),
        (
            "Last 4 weeks",
            date(2026, 10, 5),
        ),
        (
            "Last 8 weeks",
            date(2026, 9, 7),
        ),
    ],
)
def test_preset_week_periods(
    period_option,
    expected_start,
):
    today = date(2026, 10, 27)

    result = _preset_period(
        period_option=period_option,
        today=today,
    )

    assert result == AnalysisPeriod(
        start=expected_start,
        end=today,
    )


def test_preset_last_n_weeks():
    today = date(2026, 10, 27)

    result = _preset_period(
        period_option="Last N weeks",
        today=today,
        number_of_weeks=3,
    )

    assert result == AnalysisPeriod(
        start=date(2026, 10, 12),
        end=today,
    )


def test_last_n_weeks_requires_number():
    with pytest.raises(
        ValueError,
        match="number_of_weeks is required",
    ):
        _preset_period(
            period_option="Last N weeks",
            today=date(2026, 10, 27),
        )


def test_unknown_period_option_is_rejected():
    with pytest.raises(
        ValueError,
        match="Unknown period option",
    ):
        _preset_period(
            period_option="Something else",
            today=date(2026, 10, 27),
        )


def test_past_month_period():
    result = _preset_period(
        period_option="Past month",
        today=date(2026, 10, 27),
    )

    assert result == AnalysisPeriod(
        start=date(2026, 9, 27),
        end=date(2026, 10, 27),
    )


def test_past_year_period_handles_calendar_date():
    result = _preset_period(
        period_option="Past year",
        today=date(2026, 10, 27),
    )

    assert result == AnalysisPeriod(
        start=date(2025, 10, 27),
        end=date(2026, 10, 27),
    )


def test_default_custom_start_without_stored_data():
    context = make_context()

    result = _default_custom_start(context)

    assert result == date(
        2026,
        7,
        29,
    )


def test_default_custom_start_uses_later_stored_date():
    context = make_context(
        earliest_data=date(
            2026,
            9,
            1,
        ),
        latest_data=date(
            2026,
            10,
            27,
        ),
    )

    result = _default_custom_start(context)

    assert result == date(
        2026,
        9,
        1,
    )


def test_custom_period_with_two_dates():
    result = _custom_period(
        selected_range=(
            date(2026, 10, 1),
            date(2026, 10, 20),
        ),
        default_start=date(
            2026,
            9,
            1,
        ),
        today=date(
            2026,
            10,
            27,
        ),
    )

    assert result == AnalysisPeriod(
        start=date(2026, 10, 1),
        end=date(2026, 10, 20),
    )


def test_custom_period_with_single_date_sequence():
    result = _custom_period(
        selected_range=(date(2026, 10, 15),),
        default_start=date(
            2026,
            9,
            1,
        ),
        today=date(
            2026,
            10,
            27,
        ),
    )

    assert result == AnalysisPeriod(
        start=date(2026, 10, 15),
        end=date(2026, 10, 15),
    )


def test_custom_period_with_single_date():
    result = _custom_period(
        selected_range=date(
            2026,
            10,
            15,
        ),
        default_start=date(
            2026,
            9,
            1,
        ),
        today=date(
            2026,
            10,
            27,
        ),
    )

    assert result == AnalysisPeriod(
        start=date(2026, 10, 15),
        end=date(2026, 10, 15),
    )


def test_normalise_period_reverses_dates():
    result = _normalise_period(
        period=AnalysisPeriod(
            start=date(2026, 10, 20),
            end=date(2026, 10, 10),
        ),
        today=date(2026, 10, 27),
    )

    assert result == AnalysisPeriod(
        start=date(2026, 10, 10),
        end=date(2026, 10, 20),
    )


def test_normalise_period_excludes_future_end_date():
    result = _normalise_period(
        period=AnalysisPeriod(
            start=date(2026, 10, 20),
            end=date(2026, 11, 10),
        ),
        today=date(2026, 10, 27),
    )

    assert result == AnalysisPeriod(
        start=date(2026, 10, 20),
        end=date(2026, 10, 27),
    )


def test_render_sidebar_returns_selected_period(
    monkeypatch,
):
    context = make_context(
        earliest_data=date(
            2026,
            9,
            1,
        ),
        latest_data=date(
            2026,
            10,
            27,
        ),
    )

    sidebar = Mock()
    sidebar.selectbox.return_value = "Last 2 weeks"

    monkeypatch.setattr(
        "stanwell.ui.dashboard.sidebar.st.sidebar",
        sidebar,
    )

    result = render_sidebar(context)

    assert result == AnalysisPeriod(
        start=date(2026, 10, 19),
        end=date(2026, 10, 27),
    )

    sidebar.header.assert_called_once_with("Period")


def test_render_sidebar_warns_when_period_precedes_data(
    monkeypatch,
):
    context = make_context(
        earliest_data=date(
            2026,
            10,
            25,
        ),
        latest_data=date(
            2026,
            10,
            27,
        ),
    )

    sidebar = Mock()
    sidebar.selectbox.return_value = "Last 2 weeks"

    monkeypatch.setattr(
        "stanwell.ui.dashboard.sidebar.st.sidebar",
        sidebar,
    )

    render_sidebar(context)

    sidebar.warning.assert_any_call(
        "The selected period starts before " "the earliest stored Toggl data."
    )


def test_render_sidebar_warns_when_no_data_are_stored(
    monkeypatch,
):
    context = make_context()

    sidebar = Mock()
    sidebar.selectbox.return_value = "This week"

    monkeypatch.setattr(
        "stanwell.ui.dashboard.sidebar.st.sidebar",
        sidebar,
    )

    render_sidebar(context)

    sidebar.warning.assert_called_once_with(
        "The database currently contains no "
        "synced Toggl entries. The dashboard "
        "is ready, but tracked-time charts "
        "will remain empty until entries have "
        "been imported."
    )


def test_normalise_period_clamps_entirely_future_period():
    result = _normalise_period(
        period=AnalysisPeriod(
            start=date(2026, 11, 10),
            end=date(2026, 11, 15),
        ),
        today=date(2026, 10, 27),
    )

    assert result == AnalysisPeriod(
        start=date(2026, 10, 27),
        end=date(2026, 10, 27),
    )
