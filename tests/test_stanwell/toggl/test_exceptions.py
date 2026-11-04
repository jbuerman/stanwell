from stanwell.toggl.exceptions import (
    TogglQuotaExhaustedError,
)


def test_quota_exhausted_stores_status_code():
    error = TogglQuotaExhaustedError(
        status_code=429,
    )

    assert error.status_code == 429


def test_quota_exhausted_stores_quota_information():
    error = TogglQuotaExhaustedError(
        status_code=429,
        remaining=5,
        resets_in=60,
    )

    assert error.remaining == 5
    assert error.resets_in == 60


def test_quota_exhausted_defaults_to_empty_partial_entries():
    error = TogglQuotaExhaustedError(
        status_code=429,
    )

    assert error.partial_entries == []


def test_quota_exhausted_stores_partial_entries():
    partial_entries = [
        {
            "id": 123,
        },
        {
            "id": 456,
        },
    ]

    error = TogglQuotaExhaustedError(
        status_code=429,
        partial_entries=partial_entries,
    )

    assert error.partial_entries == partial_entries


def test_quota_exhausted_message_contains_quota_information():
    error = TogglQuotaExhaustedError(
        status_code=429,
        remaining=5,
        resets_in=60,
    )

    assert str(error) == (
        "Toggl API limit returned 429. " "Remaining: 5; " "resets in: 60 seconds."
    )


def test_quota_exhausted_message_handles_missing_quota_information():
    error = TogglQuotaExhaustedError(
        status_code=429,
    )

    assert str(error) == (
        "Toggl API limit returned 429. "
        "Remaining: unknown; "
        "resets in: unknown seconds."
    )


def test_quota_exhausted_preserves_zero_remaining():
    error = TogglQuotaExhaustedError(
        status_code=429,
        remaining=0,
        resets_in=0,
    )

    assert str(error) == (
        "Toggl API limit returned 429. " "Remaining: 0; " "resets in: 0 seconds."
    )
