"""Provide date-range utilities for data retrieval and synchronisation."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

DateRange = tuple[date, date]


def date_ranges(
    start_date: date,
    end_date: date,
    chunk_size_days: int,
) -> Iterator[DateRange]:
    """Split an inclusive date range into fixed-size chunks.

    The final range may contain fewer days than ``chunk_size_days``.

    Parameters
    ----------
    start_date : date
        First date to include.
    end_date : date
        Last date to include.
    chunk_size_days : int
        Maximum number of days in each generated range.

    Yields
    ------
    DateRange
        Inclusive start and end dates for each chunk.

    """
    current_start = start_date

    while current_start <= end_date:
        current_end = min(
            end_date,
            current_start + timedelta(days=chunk_size_days - 1),
        )

        yield current_start, current_end

        current_start = current_end + timedelta(days=1)
