from datetime import date
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from stanwell.toggl import exceptions, sync


@pytest.fixture
def mock_refresh_dependencies(monkeypatch):
    monkeypatch.setattr(
        sync,
        "synchronise_projects",
        lambda connection, cfg: 1,
    )

    monkeypatch.setattr(
        sync,
        "load_project_names",
        lambda connection: {
            123: "Test project",
        },
    )

    monkeypatch.setattr(
        sync,
        "normalise",
        lambda raw_entry, project_names: (raw_entry["id"],),
    )

    def fake_upsert(connection, rows):
        for row in rows:
            connection.execute(
                """
                INSERT INTO time_entries (
                    id,
                    start_utc,
                    duration_seconds,
                    raw_json,
                    fetched_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    start_utc = excluded.start_utc,
                    duration_seconds = excluded.duration_seconds
                """,
                (
                    row[0],
                    "2026-09-01T09:00:00+01:00",
                    3600,
                    "{}",
                    "2026-09-01T10:00:00+01:00",
                ),
            )

    monkeypatch.setattr(
        sync,
        "upsert_normalised_rows",
        fake_upsert,
    )


class TestRefresh:
    """Test Toggl refresh and synchronisation orchestration.

    These tests focus on the behaviour of the synchronisation layer rather
    than the individual API, normalisation or repository components.

    A real in-memory SQLite database is used to verify changes to coverage
    and stored entries. External or lower-level dependencies are mocked so
    that the tests can exercise refresh behaviour deterministically.

    The tests cover marking periods as pending, completing successful
    refreshes, handling quota exhaustion, preserving existing data after
    incomplete downloads and retrying pending periods.
    """

    def test_refresh_marks_whole_range_pending_before_fetch(
        self,
        conn,
        cfg,
        mock_refresh_dependencies,
        monkeypatch,
    ):
        calls = 0

        def fake_fetch_range(
            fetch_cfg,
            chunk_start,
            chunk_end,
        ):
            nonlocal calls
            calls += 1

            rows = conn.execute("""
                SELECT day
                FROM data_coverage
                WHERE refresh_pending = 1
                ORDER BY day
                """).fetchall()

            pending = [row["day"] for row in rows]

            if calls == 1:
                assert pending == [
                    "2026-09-01",
                    "2026-09-02",
                    "2026-09-03",
                    "2026-09-04",
                ]

            return []

        monkeypatch.setattr(
            sync,
            "fetch_range",
            fake_fetch_range,
        )

        sync.refresh_period(
            conn,
            cfg,
            date(2026, 9, 1),
            date(2026, 9, 4),
        )

        assert calls == 2

    def test_successful_refresh_clears_pending_dates(
        self,
        conn,
        cfg,
        mock_refresh_dependencies,
        monkeypatch,
    ):
        monkeypatch.setattr(
            sync,
            "fetch_range",
            lambda cfg, start, end: [],
        )

        result = sync.refresh_period(
            conn,
            cfg,
            date(2026, 9, 1),
            date(2026, 9, 4),
        )

        assert result["status"] == "ok"

        rows = conn.execute("""
            SELECT
                day,
                refresh_pending,
                refreshed_at
            FROM data_coverage
            ORDER BY day
            """).fetchall()

        assert len(rows) == 4

        for row in rows:
            assert row["refresh_pending"] == 0
            assert row["refreshed_at"] is not None

    def test_quota_exhaustion_leaves_remaining_dates_pending(
        self,
        conn,
        cfg,
        mock_refresh_dependencies,
        monkeypatch,
    ):
        calls = 0

        def fake_fetch_range(
            fetch_cfg,
            chunk_start,
            chunk_end,
        ):
            nonlocal calls

            calls += 1

            if calls == 1:
                return []

            raise exceptions.TogglQuotaExhaustedError(
                status_code=402,
                remaining=0,
                resets_in=1200,
                partial_entries=[],
            )

        monkeypatch.setattr(
            sync,
            "fetch_range",
            fake_fetch_range,
        )

        result = sync.refresh_period(
            conn,
            cfg,
            date(2026, 9, 1),
            date(2026, 9, 4),
        )

        assert result["status"] == "quota_exhausted"

        rows = conn.execute("""
            SELECT day,
                   refresh_pending
            FROM data_coverage
            ORDER BY day
            """).fetchall()

        states = {row["day"]: row["refresh_pending"] for row in rows}

        assert states == {
            "2026-09-01": 0,
            "2026-09-02": 0,
            "2026-09-03": 1,
            "2026-09-04": 1,
        }

    def test_incomplete_chunk_preserves_existing_entries(
        self,
        conn,
        cfg,
        mock_refresh_dependencies,
        monkeypatch,
    ):
        conn.execute(
            """
            INSERT INTO time_entries (id,
                                      start_utc,
                                      duration_seconds,
                                      raw_json,
                                      fetched_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                999,
                "2026-09-01T09:00:00+01:00",
                3600,
                "{}",
                "2026-09-01T10:00:00+01:00",
            ),
        )
        conn.commit()

        def fake_fetch_range(
            fetch_cfg,
            chunk_start,
            chunk_end,
        ):
            raise exceptions.TogglQuotaExhaustedError(
                status_code=402,
                remaining=0,
                resets_in=1200,
                partial_entries=[],
            )

        monkeypatch.setattr(
            sync,
            "fetch_range",
            fake_fetch_range,
        )

        result = sync.refresh_period(
            conn,
            cfg,
            date(2026, 9, 1),
            date(2026, 9, 2),
        )

        assert result["status"] == "quota_exhausted"

        existing = conn.execute("""
            SELECT id
            FROM time_entries
            WHERE id = 999
            """).fetchone()

        assert existing is not None

        pending = conn.execute("""
            SELECT refresh_pending
            FROM data_coverage
            WHERE day = '2026-09-01'
            """).fetchone()

        assert pending["refresh_pending"] == 1

    def test_successful_retry_clears_previous_pending_state(
        self,
        conn,
        cfg,
        mock_refresh_dependencies,
        monkeypatch,
    ):
        conn.executemany(
            """
            INSERT INTO data_coverage (day,
                                       refresh_pending)
            VALUES (?, 1)
            """,
            [
                ("2026-09-01",),
                ("2026-09-02",),
            ],
        )

        conn.commit()

        monkeypatch.setattr(
            sync,
            "fetch_range",
            lambda cfg, start, end: [],
        )

        result = sync.refresh_period(
            conn,
            cfg,
            date(2026, 9, 1),
            date(2026, 9, 2),
        )

        assert result["status"] == "ok"

        rows = conn.execute("""
            SELECT refresh_pending,
                   refreshed_at
            FROM data_coverage
            ORDER BY day
            """).fetchall()

        assert all(row["refresh_pending"] == 0 for row in rows)

        assert all(row["refreshed_at"] is not None for row in rows)

    def test_refresh_pending_clears_pending_dates(
        self,
        conn,
        cfg,
        mock_refresh_dependencies,
        monkeypatch,
    ):
        conn.executemany(
            """
            INSERT INTO data_coverage (day,
                                       refresh_pending)
            VALUES (?, 1)
            """,
            [
                ("2026-09-01",),
                ("2026-09-02",),
            ],
        )

        conn.commit()

        monkeypatch.setattr(
            sync,
            "fetch_range",
            lambda cfg, start, end: [],
        )

        result = sync.refresh_pending(
            conn,
            cfg,
        )

        assert result["status"] == "ok"
        assert result["pending_count"] == 0

        rows = conn.execute("""
            SELECT refresh_pending
            FROM data_coverage
            ORDER BY day
            """).fetchall()

        assert all(row["refresh_pending"] == 0 for row in rows)


class TestPrepareProjectNames:
    def test_returns_project_names_and_request_count(
        self,
        conn,
        cfg,
        monkeypatch,
    ):
        monkeypatch.setattr(
            sync,
            "synchronise_projects",
            lambda connection, config: 2,
        )
        monkeypatch.setattr(
            sync,
            "load_project_names",
            lambda connection: {
                123: "Project one",
                456: "Project two",
            },
        )

        project_names, request_count = sync._prepare_project_names(
            conn,
            cfg,
        )

        assert project_names == {
            123: "Project one",
            456: "Project two",
        }
        assert request_count == 2

    def test_uses_local_projects_when_quota_is_exhausted(
        self,
        conn,
        cfg,
        monkeypatch,
    ):
        def raise_quota_error(connection, config):
            raise exceptions.TogglQuotaExhaustedError(
                status_code=429,
                remaining=0,
                resets_in=1200,
                partial_entries=[],
            )

        monkeypatch.setattr(
            sync,
            "synchronise_projects",
            raise_quota_error,
        )
        monkeypatch.setattr(
            sync,
            "load_project_names",
            lambda connection: {
                123: "Existing project",
            },
        )

        project_names, request_count = sync._prepare_project_names(
            conn,
            cfg,
        )

        assert project_names == {
            123: "Existing project",
        }
        assert request_count == 0

    def test_raises_when_quota_is_exhausted_without_local_projects(
        self,
        conn,
        cfg,
        monkeypatch,
    ):
        def raise_quota_error(connection, config):
            raise exceptions.TogglQuotaExhaustedError(
                status_code=429,
                remaining=0,
                resets_in=1200,
                partial_entries=[],
            )

        monkeypatch.setattr(
            sync,
            "synchronise_projects",
            raise_quota_error,
        )
        monkeypatch.setattr(
            sync,
            "load_project_names",
            lambda connection: {},
        )

        with pytest.raises(
            RuntimeError,
            match="no local project catalogue is available",
        ):
            sync._prepare_project_names(
                conn,
                cfg,
            )


class TestRefreshChunk:
    def test_complete_chunk_reconciles_and_marks_chunk_complete(
        self,
        conn,
        cfg,
        monkeypatch,
    ):
        raw_entries = [
            {
                "id": 123,
            },
        ]
        normalised_entries = [
            (123,),
        ]

        monkeypatch.setattr(
            sync,
            "fetch_range",
            lambda config, chunk_start, chunk_end: raw_entries,
        )

        normalise_mock = Mock(return_value=normalised_entries)
        delete_mock = Mock()
        upsert_mock = Mock()
        complete_mock = Mock()

        monkeypatch.setattr(
            sync,
            "_normalise_entries",
            normalise_mock,
        )
        monkeypatch.setattr(
            sync,
            "_delete_stale_entries",
            delete_mock,
        )
        monkeypatch.setattr(
            sync,
            "upsert_normalised_rows",
            upsert_mock,
        )
        monkeypatch.setattr(
            sync,
            "_mark_chunk_complete",
            complete_mock,
        )

        timezone = ZoneInfo("Europe/London")
        chunk_start = date(2026, 9, 1)
        chunk_end = date(2026, 9, 2)

        result = sync._refresh_chunk(
            conn,
            cfg,
            {123: "Test project"},
            timezone,
            chunk_start,
            chunk_end,
            "force",
        )

        assert result.entry_count == 1
        assert result.is_complete is True
        assert result.quota_error is None

        normalise_mock.assert_called_once_with(
            raw_entries,
            {123: "Test project"},
            chunk_start,
            chunk_end,
        )

        delete_mock.assert_called_once_with(
            conn,
            normalised_entries,
            timezone,
            chunk_start,
            chunk_end,
        )

        upsert_mock.assert_called_once_with(
            conn,
            normalised_entries,
        )

        complete_mock.assert_called_once_with(
            conn,
            chunk_start,
            chunk_end,
            "force",
        )

    def test_incomplete_chunk_saves_partial_entries_without_reconciliation(
        self,
        conn,
        cfg,
        monkeypatch,
    ):
        partial_entries = [
            {
                "id": 123,
            },
        ]
        normalised_entries = [
            (123,),
        ]

        quota_error = exceptions.TogglQuotaExhaustedError(
            status_code=429,
            remaining=0,
            resets_in=1200,
            partial_entries=partial_entries,
        )

        def raise_quota_error(
            config,
            chunk_start,
            chunk_end,
        ):
            raise quota_error

        monkeypatch.setattr(
            sync,
            "fetch_range",
            raise_quota_error,
        )
        monkeypatch.setattr(
            sync,
            "_normalise_entries",
            Mock(return_value=normalised_entries),
        )

        delete_mock = Mock()
        upsert_mock = Mock()
        complete_mock = Mock()

        monkeypatch.setattr(
            sync,
            "_delete_stale_entries",
            delete_mock,
        )
        monkeypatch.setattr(
            sync,
            "upsert_normalised_rows",
            upsert_mock,
        )
        monkeypatch.setattr(
            sync,
            "_mark_chunk_complete",
            complete_mock,
        )

        result = sync._refresh_chunk(
            conn,
            cfg,
            {123: "Test project"},
            ZoneInfo("Europe/London"),
            date(2026, 9, 1),
            date(2026, 9, 2),
            "force",
        )

        assert result.entry_count == 1
        assert result.is_complete is False
        assert result.quota_error is quota_error

        upsert_mock.assert_called_once_with(
            conn,
            normalised_entries,
        )
        delete_mock.assert_not_called()
        complete_mock.assert_not_called()

    def test_rejects_non_list_response(
        self,
        conn,
        cfg,
        monkeypatch,
    ):
        monkeypatch.setattr(
            sync,
            "fetch_range",
            lambda config, chunk_start, chunk_end: {"unexpected": "response"},
        )

        with pytest.raises(
            TypeError,
            match="unexpected response type",
        ):
            sync._refresh_chunk(
                conn,
                cfg,
                {},
                ZoneInfo("Europe/London"),
                date(2026, 9, 1),
                date(2026, 9, 2),
                "force",
            )


class TestCreateQuotaExhaustedResult:
    def test_creates_result_and_finishes_sync_log(
        self,
        conn,
        monkeypatch,
    ):
        finish_log_mock = Mock()

        monkeypatch.setattr(
            sync,
            "_finish_sync_log",
            finish_log_mock,
        )

        quota_error = exceptions.TogglQuotaExhaustedError(
            status_code=429,
            remaining=0,
            resets_in=1200,
            partial_entries=[],
        )

        result = sync._create_quota_exhausted_result(
            conn,
            log_id=12,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 6),
            mode="force",
            chunk_start=date(2026, 9, 3),
            chunk_end=date(2026, 9, 4),
            completed_through=date(2026, 9, 2),
            request_count=3,
            entry_count=15,
            quota_error=quota_error,
            partial_entry_count=5,
        )

        assert result["status"] == "quota_exhausted"
        assert result["start"] == "2026-09-01"
        assert result["end"] == "2026-09-06"
        assert result["mode"] == "force"
        assert result["requests"] == 3
        assert result["entries_saved"] == 15
        assert result["partial_chunk_start"] == "2026-09-03"
        assert result["partial_chunk_end"] == "2026-09-04"
        assert result["completed_through"] == "2026-09-02"
        assert result["quota_remaining"] == 0
        assert result["quota_resets_in_seconds"] == 1200

        assert "Saved 5 entries" in result["message"]

        finish_log_mock.assert_called_once_with(
            conn,
            12,
            3,
            15,
            "quota_exhausted",
            result["message"],
        )
