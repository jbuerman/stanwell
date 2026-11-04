from datetime import date

import pandas as pd
import pytest

from stanwell.analysis.projections import (
    prepare_week_remaining_projection,
)


def test_week_remaining_projection_distributes_hours_equally():
    daily = pd.DataFrame(
        {
            "day": pd.date_range(
                "2026-11-02",
                "2026-11-06",
            ),
            "weekday": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
            ],
            "expected_hours": [
                7.0,
                7.0,
                7.0,
                7.0,
                7.0,
            ],
            "actual_hours": [
                7.0,
                7.0,
                8.0,
                0.0,
                0.0,
            ],
            "balance_adjustment_hours": [
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ],
        }
    )

    result = prepare_week_remaining_projection(
        daily=daily,
        today=date(2026, 11, 4),
    )

    assert list(result["weekday"]) == [
        "Thursday",
        "Friday",
    ]

    assert list(result["required_hours"]) == pytest.approx(
        [
            6.5,
            6.5,
        ]
    )


def test_week_remaining_projection_excludes_non_working_days():
    daily = pd.DataFrame(
        {
            "day": pd.date_range(
                "2026-11-02",
                "2026-11-06",
            ),
            "weekday": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
            ],
            "expected_hours": [
                7.0,
                7.0,
                7.0,
                7.0,
                0.0,
            ],
            "actual_hours": [
                7.0,
                7.0,
                6.0,
                0.0,
                0.0,
            ],
            "balance_adjustment_hours": [
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ],
        }
    )

    result = prepare_week_remaining_projection(
        daily=daily,
        today=date(2026, 11, 4),
    )

    assert list(result["weekday"]) == [
        "Thursday",
    ]

    assert result.iloc[0]["required_hours"] == pytest.approx(8.0)


def test_week_remaining_projection_never_requires_negative_hours():
    daily = pd.DataFrame(
        {
            "day": pd.date_range(
                "2026-11-02",
                "2026-11-06",
            ),
            "weekday": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
            ],
            "expected_hours": [
                7.0,
                7.0,
                7.0,
                7.0,
                7.0,
            ],
            "actual_hours": [
                12.0,
                12.0,
                12.0,
                0.0,
                0.0,
            ],
        }
    )

    result = prepare_week_remaining_projection(
        daily=daily,
        today=date(2026, 11, 4),
    )

    assert list(result["required_hours"]) == pytest.approx(
        [
            0.0,
            0.0,
        ]
    )


def test_week_remaining_projection_is_empty_when_week_is_finished():
    daily = pd.DataFrame(
        {
            "day": [
                date(2026, 11, 6),
            ],
            "weekday": [
                "Friday",
            ],
            "expected_hours": [
                7.0,
            ],
            "actual_hours": [
                7.0,
            ],
        }
    )

    result = prepare_week_remaining_projection(
        daily=daily,
        today=date(2026, 11, 6),
    )

    assert result.empty


def test_week_remaining_projection_returns_zero_when_requirement_met():
    daily = pd.DataFrame(
        {
            "day": pd.date_range(
                "2026-11-02",
                "2026-11-06",
            ),
            "weekday": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
            ],
            "expected_hours": [
                7.0,
                7.0,
                7.0,
                7.0,
                7.0,
            ],
            "actual_hours": [
                12.0,
                12.0,
                11.0,
                0.0,
                0.0,
            ],
        }
    )

    result = prepare_week_remaining_projection(
        daily=daily,
        today=date(2026, 11, 4),
    )

    assert list(result["weekday"]) == [
        "Thursday",
        "Friday",
    ]

    assert list(result["required_hours"]) == pytest.approx(
        [
            0.0,
            0.0,
        ]
    )
