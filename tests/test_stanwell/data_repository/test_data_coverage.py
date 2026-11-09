from datetime import date

import pytest

from stanwell.data_repository.data_coverage import (
    count_pending_refresh_dates,
    find_missing_ranges,
    get_pending_refresh_days,
    mark_refresh_complete,
    mark_refresh_pending,
    pending_refresh_ranges,
    pending_sync_ranges,
)


def test_pending_refresh_ranges_groups_consecutive_days(conn):
    conn.executemany(
        """
        INSERT INTO data_coverage (day,
                                   refresh_pending)
        VALUES (?, 1)
        """,
        [
            ("2026-09-01",),
            ("2026-09-02",),
            ("2026-09-05",),
            ("2026-09-06",),
            ("2026-09-07",),
        ],
    )
    conn.commit()

    result = pending_refresh_ranges(conn)

    assert result == [
        (
            date(2026, 9, 1),
            date(2026, 9, 2),
        ),
        (
            date(2026, 9, 5),
            date(2026, 9, 7),
        ),
    ]


def test_mark_refresh_pending_updates_existing_row(conn):
    conn.execute(
        """
        INSERT INTO data_coverage (
            day,
            refresh_pending
        )
        VALUES (?, 0)
        """,
        ("2026-09-01",),
    )
    conn.commit()

    mark_refresh_pending(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 1),
    )

    row = conn.execute(
        """
        SELECT refresh_pending
        FROM data_coverage
        WHERE day = ?
        """,
        ("2026-09-01",),
    ).fetchone()

    assert row["refresh_pending"] == 1


def test_mark_refresh_complete_clears_pending_state(conn):
    mark_refresh_pending(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 2),
    )

    mark_refresh_complete(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 2),
    )

    rows = conn.execute("""
        SELECT refresh_pending, refreshed_at
        FROM data_coverage
        ORDER BY day
        """).fetchall()

    assert all(row["refresh_pending"] == 0 for row in rows)
    assert all(row["refreshed_at"] is not None for row in rows)


def test_mark_refresh_complete_does_not_affect_other_days(conn):
    mark_refresh_pending(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 3),
    )

    mark_refresh_complete(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 2),
    )

    row = conn.execute(
        """
        SELECT refresh_pending
        FROM data_coverage
        WHERE day = ?
        """,
        ("2026-09-03",),
    ).fetchone()

    assert row["refresh_pending"] == 1


def test_get_pending_refresh_days_returns_sorted_dates(conn):
    mark_refresh_pending(
        conn,
        date(2026, 9, 3),
        date(2026, 9, 3),
    )
    mark_refresh_pending(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 1),
    )

    result = get_pending_refresh_days(conn)

    assert result == [
        date(2026, 9, 1),
        date(2026, 9, 3),
    ]


def test_get_pending_refresh_days_returns_empty_list(conn):
    assert get_pending_refresh_days(conn) == []


def test_pending_refresh_ranges_returns_empty_list(conn):
    assert pending_refresh_ranges(conn) == []


def test_count_pending_refresh_dates(conn):
    mark_refresh_pending(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 3),
    )

    assert count_pending_refresh_dates(conn) == 3


def test_count_pending_refresh_dates_ignores_completed_dates(conn):
    mark_refresh_pending(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 3),
    )

    mark_refresh_complete(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 1),
    )

    assert count_pending_refresh_dates(conn) == 2


class TestFindMissingRanges:
    def test_find_missing_ranges_when_all_days_are_missing(self, conn):
        result = find_missing_ranges(
            conn,
            date(2026, 9, 1),
            date(2026, 9, 3),
        )

        assert result == [
            (
                date(2026, 9, 1),
                date(2026, 9, 3),
            ),
        ]

    def test_find_missing_ranges_when_no_days_are_missing(self, conn):
        conn.executemany(
            """
            INSERT INTO covered_days (
                day,
                fetched_at,
                fetch_mode
            )
            VALUES (?, ?, ?)
            """,
            [
                ("2026-09-01", "2026-09-10T12:00:00+00:00", "test"),
                ("2026-09-02", "2026-09-10T12:00:00+00:00", "test"),
                ("2026-09-03", "2026-09-10T12:00:00+00:00", "test"),
            ],
        )
        conn.commit()

        result = find_missing_ranges(
            conn,
            date(2026, 9, 1),
            date(2026, 9, 3),
        )

        assert result == []

    def test_find_missing_ranges_groups_consecutive_missing_days(self, conn):
        conn.executemany(
            """
            INSERT INTO covered_days (
                day,
                fetched_at,
                fetch_mode
            )
            VALUES (?, ?, ?)
            """,
            [
                ("2026-09-03", "2026-09-10T12:00:00+00:00", "test"),
                ("2026-09-06", "2026-09-10T12:00:00+00:00", "test"),
            ],
        )
        conn.commit()

        result = find_missing_ranges(
            conn,
            date(2026, 9, 1),
            date(2026, 9, 7),
        )

        assert result == [
            (
                date(2026, 9, 1),
                date(2026, 9, 2),
            ),
            (
                date(2026, 9, 4),
                date(2026, 9, 5),
            ),
            (
                date(2026, 9, 7),
                date(2026, 9, 7),
            ),
        ]

    def test_find_missing_ranges_accepts_iso_date_strings(self, conn):
        result = find_missing_ranges(
            conn,
            "2026-09-01",
            "2026-09-02",
        )

        assert result == [
            (
                date(2026, 9, 1),
                date(2026, 9, 2),
            ),
        ]


class TestPendingSyncRanges:

    def test_pending_sync_ranges_returns_missing_dates(
        self,
        conn,
    ):
        """Return dates that have never been successfully covered."""
        conn.execute(
            """
            INSERT INTO covered_days (
                day,
                fetched_at,
                fetch_mode
            )
            VALUES (?, ?, ?)
            """,
            (
                "2026-11-01",
                "2026-11-09T12:00:00+00:00",
                "missing",
            ),
        )

        conn.commit()

        result = pending_sync_ranges(
            conn,
            date(2026, 11, 1),
            date(2026, 11, 4),
        )

        assert result == [
            (
                date(2026, 11, 2),
                date(2026, 11, 4),
            ),
        ]

    def test_pending_sync_ranges_returns_refresh_pending_dates(
        self,
        conn,
    ):
        """Return covered dates that have been marked for refresh."""
        for day in range(1, 5):
            day_string = f"2026-11-{day:02d}"

            conn.execute(
                """
                INSERT INTO covered_days (
                    day,
                    fetched_at,
                    fetch_mode
                )
                VALUES (?, ?, ?)
                """,
                (
                    day_string,
                    "2026-11-09T12:00:00+00:00",
                    "force",
                ),
            )

            conn.execute(
                """
                INSERT INTO data_coverage (
                    day,
                    refresh_pending
                )
                VALUES (?, ?)
                """,
                (
                    day_string,
                    1 if day in {2, 3} else 0,
                ),
            )

        conn.commit()

        result = pending_sync_ranges(
            conn,
            date(2026, 11, 1),
            date(2026, 11, 4),
        )

        assert result == [
            (
                date(2026, 11, 2),
                date(2026, 11, 3),
            ),
        ]

    def test_pending_sync_ranges_combines_missing_and_refresh_pending(
        self,
        conn,
    ):
        """Combine missing and refresh-pending dates."""
        conn.executemany(
            """
            INSERT INTO covered_days (
                day,
                fetched_at,
                fetch_mode
            )
            VALUES (?, ?, ?)
            """,
            [
                (
                    "2026-11-01",
                    "2026-11-09T12:00:00+00:00",
                    "force",
                ),
                (
                    "2026-11-03",
                    "2026-11-09T12:00:00+00:00",
                    "force",
                ),
                (
                    "2026-11-04",
                    "2026-11-09T12:00:00+00:00",
                    "force",
                ),
            ],
        )

        conn.execute(
            """
            INSERT INTO data_coverage (
                day,
                refresh_pending
            )
            VALUES (?, 1)
            """,
            ("2026-11-03",),
        )

        conn.commit()

        result = pending_sync_ranges(
            conn,
            date(2026, 11, 1),
            date(2026, 11, 4),
        )

        assert result == [
            (
                date(2026, 11, 2),
                date(2026, 11, 3),
            ),
        ]

    def test_pending_sync_ranges_does_not_duplicate_overlapping_states(
        self,
        conn,
        monkeypatch,
    ):
        """Include a date only once when missing and pending sets overlap."""
        monkeypatch.setattr(
            "stanwell.data_repository.data_coverage.find_missing_ranges",
            lambda connection, start_day, end_day: [
                (
                    date(2026, 11, 2),
                    date(2026, 11, 4),
                ),
            ],
        )

        monkeypatch.setattr(
            "stanwell.data_repository.data_coverage.pending_refresh_ranges",
            lambda connection: [
                (
                    date(2026, 11, 3),
                    date(2026, 11, 5),
                ),
            ],
        )

        result = pending_sync_ranges(
            conn,
            date(2026, 11, 1),
            date(2026, 11, 6),
        )

        assert result == [
            (
                date(2026, 11, 2),
                date(2026, 11, 5),
            ),
        ]

    def test_pending_sync_ranges_merges_adjacent_missing_and_pending_ranges(
        self,
        conn,
        monkeypatch,
    ):
        """Merge adjacent missing and refresh-pending dates into one range."""
        monkeypatch.setattr(
            "stanwell.data_repository.data_coverage.find_missing_ranges",
            lambda connection, start_day, end_day: [
                (
                    date(2026, 11, 1),
                    date(2026, 11, 3),
                ),
            ],
        )

        monkeypatch.setattr(
            "stanwell.data_repository.data_coverage.pending_refresh_ranges",
            lambda connection: [
                (
                    date(2026, 11, 4),
                    date(2026, 11, 6),
                ),
            ],
        )

        result = pending_sync_ranges(
            conn,
            date(2026, 11, 1),
            date(2026, 11, 6),
        )

        assert result == [
            (
                date(2026, 11, 1),
                date(2026, 11, 6),
            ),
        ]

    def test_pending_sync_ranges_returns_empty_when_nothing_requires_sync(
        self,
        conn,
    ):
        """Return no ranges when every requested date is current."""
        for day in range(1, 5):
            day_string = f"2026-11-{day:02d}"

            conn.execute(
                """
                INSERT INTO covered_days (
                    day,
                    fetched_at,
                    fetch_mode
                )
                VALUES (?, ?, ?)
                """,
                (
                    day_string,
                    "2026-11-09T12:00:00+00:00",
                    "force",
                ),
            )

            conn.execute(
                """
                INSERT INTO data_coverage (
                    day,
                    refresh_pending
                )
                VALUES (?, 0)
                """,
                (day_string,),
            )

        conn.commit()

        result = pending_sync_ranges(
            conn,
            date(2026, 11, 1),
            date(2026, 11, 4),
        )

        assert result == []

    def test_pending_sync_ranges_ignores_pending_dates_before_window(
        self,
        conn,
        monkeypatch,
    ):
        """Ignore refresh-pending dates before the requested window."""
        monkeypatch.setattr(
            "stanwell.data_repository.data_coverage.find_missing_ranges",
            lambda connection, start_day, end_day: [],
        )

        monkeypatch.setattr(
            "stanwell.data_repository.data_coverage.pending_refresh_ranges",
            lambda connection: [
                (
                    date(2026, 10, 20),
                    date(2026, 10, 25),
                ),
                (
                    date(2026, 11, 2),
                    date(2026, 11, 3),
                ),
            ],
        )

        result = pending_sync_ranges(
            conn,
            date(2026, 11, 1),
            date(2026, 11, 5),
        )

        assert result == [
            (
                date(2026, 11, 2),
                date(2026, 11, 3),
            ),
        ]

    def test_pending_sync_ranges_clips_pending_range_to_window(
        self,
        conn,
        monkeypatch,
    ):
        """Clip refresh-pending ranges to the requested synchronization window."""
        monkeypatch.setattr(
            "stanwell.data_repository.data_coverage.find_missing_ranges",
            lambda connection, start_day, end_day: [],
        )

        monkeypatch.setattr(
            "stanwell.data_repository.data_coverage.pending_refresh_ranges",
            lambda connection: [
                (
                    date(2026, 10, 30),
                    date(2026, 11, 10),
                ),
            ],
        )

        result = pending_sync_ranges(
            conn,
            date(2026, 11, 2),
            date(2026, 11, 5),
        )

        assert result == [
            (
                date(2026, 11, 2),
                date(2026, 11, 5),
            ),
        ]

    def test_pending_sync_ranges_rejects_reversed_window(
        self,
        conn,
    ):
        """Reject a synchronization window whose end precedes its start."""
        with pytest.raises(
            ValueError,
            match="end_day must not be before start_day",
        ):
            pending_sync_ranges(
                conn,
                date(2026, 11, 5),
                date(2026, 11, 1),
            )
