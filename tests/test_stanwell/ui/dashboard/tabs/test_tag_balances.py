from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from stanwell.ui.dashboard.tabs import (
    tag_balances,
)


def make_tag_entries() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entry_id": [
                1,
                2,
                3,
            ],
            "week_start": pd.to_datetime(
                [
                    "2026-10-19",
                    "2026-10-19",
                    "2026-10-26",
                ]
            ),
            "hours": [
                2.0,
                3.0,
                5.0,
            ],
            "selected_tags": [
                {"research"},
                {
                    "research",
                    "development",
                },
                {"development"},
            ],
        }
    )


def test_calculate_tag_totals():
    tag_entries = make_tag_entries()

    result = tag_balances._calculate_tag_totals(
        tag_entries=tag_entries,
        selected_tags=[
            "research",
            "development",
        ],
        workday_hours=7.5,
    )

    research = result[result["tag"] == "research"].iloc[0]

    development = result[result["tag"] == "development"].iloc[0]

    assert research["hours"] == pytest.approx(5.0)

    assert research["percent"] == pytest.approx(50.0)

    assert research["days"] == pytest.approx(5.0 / 7.5)

    assert development["hours"] == pytest.approx(8.0)

    assert development["percent"] == pytest.approx(80.0)


def test_calculate_tag_totals_with_zero_workday_hours():
    result = tag_balances._calculate_tag_totals(
        tag_entries=make_tag_entries(),
        selected_tags=["research"],
        workday_hours=0.0,
    )

    assert result.iloc[0]["days"] == pytest.approx(0.0)


def test_create_tag_trend():
    result = tag_balances._create_tag_trend(
        tag_entries=make_tag_entries(),
        selected_tags=[
            "research",
            "development",
        ],
    )

    first_week_research = result[
        (result["week_start"] == pd.Timestamp("2026-10-19"))
        & (result["tag"] == "research")
    ].iloc[0]

    assert first_week_research["hours"] == pytest.approx(5.0)

    assert first_week_research["share"] == pytest.approx(100.0)

    second_week_research = result[
        (result["week_start"] == pd.Timestamp("2026-10-26"))
        & (result["tag"] == "research")
    ].iloc[0]

    assert second_week_research["hours"] == pytest.approx(0.0)

    assert second_week_research["share"] == pytest.approx(0.0)


def test_create_tag_combinations():
    result = tag_balances._create_tag_combinations(
        tag_entries=make_tag_entries(),
        selected_tags=[
            "research",
            "development",
        ],
    )

    combinations = {row["combination"]: row["hours"] for _, row in result.iterrows()}

    assert combinations == {
        ("development",): 5.0,
        (
            "research",
            "development",
        ): 3.0,
        ("research",): 2.0,
    }


def test_create_tag_combinations_ignores_entries_without_selected_tags():
    tag_entries = make_tag_entries()

    additional_entry = pd.DataFrame(
        {
            "entry_id": [4],
            "week_start": pd.to_datetime(["2026-10-26"]),
            "hours": [10.0],
            "selected_tags": [set()],
        }
    )

    tag_entries = pd.concat(
        [
            tag_entries,
            additional_entry,
        ],
        ignore_index=True,
    )

    result = tag_balances._create_tag_combinations(
        tag_entries=tag_entries,
        selected_tags=[
            "research",
            "development",
        ],
    )

    assert float(result["hours"].sum()) == pytest.approx(10.0)


def test_create_tag_combinations_preserves_selected_tag_order():
    tag_entries = pd.DataFrame(
        {
            "hours": [2.0],
            "selected_tags": [
                {
                    "development",
                    "research",
                }
            ],
        }
    )

    result = tag_balances._create_tag_combinations(
        tag_entries=tag_entries,
        selected_tags=[
            "research",
            "development",
        ],
    )

    assert result.iloc[0]["combination"] == (
        "research",
        "development",
    )


def test_render_tag_balances_reports_no_available_tags(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        config={},
        workday_hours=7.5,
    )

    monkeypatch.setattr(
        tag_balances,
        "get_available_tags",
        Mock(return_value=[]),
    )

    monkeypatch.setattr(
        tag_balances.st,
        "header",
        Mock(),
    )
    monkeypatch.setattr(
        tag_balances.st,
        "caption",
        Mock(),
    )

    info_mock = Mock()

    monkeypatch.setattr(
        tag_balances.st,
        "info",
        info_mock,
    )

    tag_balances.render_tag_balances(
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

    info_mock.assert_called_once_with(
        "No tags are currently stored " "in the database."
    )


def test_render_tag_balances_requests_selected_period(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        config={
            "timezone": "Europe/London",
        },
        workday_hours=7.5,
    )

    tag_entries = make_tag_entries()

    monkeypatch.setattr(
        tag_balances,
        "get_available_tags",
        Mock(
            return_value=[
                "research",
                "development",
            ]
        ),
    )

    monkeypatch.setattr(
        tag_balances.st,
        "header",
        Mock(),
    )
    monkeypatch.setattr(
        tag_balances.st,
        "caption",
        Mock(),
    )
    monkeypatch.setattr(
        tag_balances.st,
        "multiselect",
        Mock(
            return_value=[
                "research",
                "development",
            ]
        ),
    )

    get_analysis_mock = Mock(return_value=tag_entries)

    monkeypatch.setattr(
        tag_balances,
        "get_tag_analysis",
        get_analysis_mock,
    )

    render_cards_mock = Mock()
    render_trend_mock = Mock()
    render_overlaps_mock = Mock()

    monkeypatch.setattr(
        tag_balances,
        "_render_tag_cards",
        render_cards_mock,
    )
    monkeypatch.setattr(
        tag_balances,
        "_render_tag_trend",
        render_trend_mock,
    )
    monkeypatch.setattr(
        tag_balances,
        "_render_tag_overlaps",
        render_overlaps_mock,
    )

    tag_balances.render_tag_balances(
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

    get_analysis_mock.assert_called_once_with(
        connection=context.connection,
        config=context.config,
        start_date=date(
            2026,
            10,
            20,
        ),
        end_date=date(
            2026,
            10,
            27,
        ),
        selected_tags=[
            "research",
            "development",
        ],
    )

    render_cards_mock.assert_called_once()
    render_trend_mock.assert_called_once()
    render_overlaps_mock.assert_called_once()


def test_render_tag_balances_reports_no_selected_tags(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        config={},
        workday_hours=7.5,
    )

    monkeypatch.setattr(
        tag_balances,
        "get_available_tags",
        Mock(return_value=["research"]),
    )

    monkeypatch.setattr(
        tag_balances.st,
        "header",
        Mock(),
    )
    monkeypatch.setattr(
        tag_balances.st,
        "caption",
        Mock(),
    )
    monkeypatch.setattr(
        tag_balances.st,
        "multiselect",
        Mock(return_value=[]),
    )

    info_mock = Mock()

    monkeypatch.setattr(
        tag_balances.st,
        "info",
        info_mock,
    )

    tag_balances.render_tag_balances(
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

    info_mock.assert_called_once_with("Select one or more tags " "to analyse.")


def test_render_tag_balances_reports_no_entries(
    monkeypatch,
):
    context = SimpleNamespace(
        connection=Mock(),
        config={},
        workday_hours=7.5,
    )

    monkeypatch.setattr(
        tag_balances,
        "get_available_tags",
        Mock(return_value=["research"]),
    )

    monkeypatch.setattr(
        tag_balances.st,
        "header",
        Mock(),
    )
    monkeypatch.setattr(
        tag_balances.st,
        "caption",
        Mock(),
    )
    monkeypatch.setattr(
        tag_balances.st,
        "multiselect",
        Mock(return_value=["research"]),
    )

    monkeypatch.setattr(
        tag_balances,
        "get_tag_analysis",
        Mock(return_value=pd.DataFrame()),
    )

    info_mock = Mock()

    monkeypatch.setattr(
        tag_balances.st,
        "info",
        info_mock,
    )

    tag_balances.render_tag_balances(
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

    info_mock.assert_called_once_with(
        "No time entries are available " "for the selected period."
    )


def test_render_tag_overlaps_reports_no_combinations(
    monkeypatch,
):
    monkeypatch.setattr(
        tag_balances.st,
        "markdown",
        Mock(),
    )
    monkeypatch.setattr(
        tag_balances.st,
        "caption",
        Mock(),
    )

    info_mock = Mock()

    monkeypatch.setattr(
        tag_balances.st,
        "info",
        info_mock,
    )

    tag_balances._render_tag_overlaps(
        combinations=pd.DataFrame(
            columns=[
                "combination",
                "hours",
            ]
        ),
        selected_tags=[
            "research",
        ],
        total_combination_count=0,
    )

    info_mock.assert_called_once_with(
        "None of the selected tags occur " "during this period."
    )
