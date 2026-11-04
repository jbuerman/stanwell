from datetime import date

from stanwell.data_repository.data_util import (
    date_ranges,
)


def test_date_ranges_returns_single_range_when_smaller_than_chunk():
    result = list(
        date_ranges(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 3),
            chunk_size_days=5,
        )
    )

    assert result == [
        (
            date(2026, 9, 1),
            date(2026, 9, 3),
        )
    ]


def test_date_ranges_splits_range_into_chunks():
    result = list(
        date_ranges(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
            chunk_size_days=3,
        )
    )

    assert result == [
        (
            date(2026, 9, 1),
            date(2026, 9, 3),
        ),
        (
            date(2026, 9, 4),
            date(2026, 9, 6),
        ),
        (
            date(2026, 9, 7),
            date(2026, 9, 7),
        ),
    ]


def test_date_ranges_handles_single_day():
    result = list(
        date_ranges(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 1),
            chunk_size_days=30,
        )
    )

    assert result == [
        (
            date(2026, 9, 1),
            date(2026, 9, 1),
        )
    ]


def test_date_ranges_returns_empty_when_start_is_after_end():
    result = list(
        date_ranges(
            start_date=date(2026, 9, 2),
            end_date=date(2026, 9, 1),
            chunk_size_days=30,
        )
    )

    assert result == []
