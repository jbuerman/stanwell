from datetime import date

import pytest

from stanwell.ui.date_periods import (
    monday_of_week,
    n_week_period,
)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (
            date(2026, 10, 19),
            date(2026, 10, 19),
        ),
        (
            date(2026, 10, 21),
            date(2026, 10, 19),
        ),
        (
            date(2026, 10, 25),
            date(2026, 10, 19),
        ),
    ],
)
def test_monday_of_week(
    day,
    expected,
):
    assert monday_of_week(day) == expected


def test_n_week_period_for_one_week():
    result = n_week_period(
        date(2026, 10, 21),
        1,
    )

    assert result == (
        date(2026, 10, 19),
        date(2026, 10, 21),
    )


def test_n_week_period_for_multiple_weeks():
    result = n_week_period(
        date(2026, 10, 21),
        4,
    )

    assert result == (
        date(2026, 9, 28),
        date(2026, 10, 21),
    )


def test_n_week_period_rejects_zero_weeks():
    with pytest.raises(
        ValueError,
        match="number_of_weeks must be at least 1",
    ):
        n_week_period(
            date(2026, 10, 21),
            0,
        )
