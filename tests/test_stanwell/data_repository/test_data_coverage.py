from datetime import date

from stanwell.data_repository.data_coverage import (
    count_pending_refresh_dates,
    find_missing_ranges,
    get_pending_refresh_days,
    mark_refresh_complete,
    mark_refresh_pending,
    pending_refresh_ranges,
)
from stanwell.toggl import sync


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


def test_refresh_pending_does_nothing_when_empty(
    conn,
    cfg,
):
    result = sync.refresh_pending(
        conn,
        cfg,
    )

    assert result["status"] == "ok"
    assert result["ranges_attempted"] == 0
    assert result["pending_count"] == 0


def test_mark_refresh_pending_creates_coverage_rows(conn):
    mark_refresh_pending(
        conn,
        date(2026, 9, 1),
        date(2026, 9, 3),
    )

    rows = conn.execute("""
        SELECT day, refresh_pending
        FROM data_coverage
        ORDER BY day
        """).fetchall()

    assert [(row["day"], row["refresh_pending"]) for row in rows] == [
        ("2026-09-01", 1),
        ("2026-09-02", 1),
        ("2026-09-03", 1),
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


def test_find_missing_ranges_when_all_days_are_missing(conn):
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


def test_find_missing_ranges_when_no_days_are_missing(conn):
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


def test_find_missing_ranges_groups_consecutive_missing_days(conn):
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


def test_find_missing_ranges_accepts_iso_date_strings(conn):
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
