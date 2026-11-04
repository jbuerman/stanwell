"""Define exceptions raised while communicating with the Toggl API."""

from __future__ import annotations

from typing import Any


class TogglQuotaExhaustedError(Exception):
    """Indicate that the Toggl API request quota has been exhausted.

    Partial entries contain entries already received during the current
    paginated request. They may be retained, but the requested period
    must not be considered completely downloaded.

    Parameters
    ----------
    status_code : int
        HTTP status code returned by Toggl.
    remaining : int, optional
        Number of API requests reported as remaining.
    resets_in : int, optional
        Number of seconds until the quota resets.
    partial_entries : list[dict[str, Any]], optional
        Entries retrieved before the quota was exhausted.

    """

    def __init__(
        self,
        status_code: int,
        remaining: int | None = None,
        resets_in: int | None = None,
        partial_entries: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status_code = status_code
        self.remaining = remaining
        self.resets_in = resets_in

        if partial_entries is None:
            self.partial_entries: list[dict[str, Any]] = []
        else:
            self.partial_entries = partial_entries

        if remaining is None:
            remaining_text = "unknown"
        else:
            remaining_text = str(remaining)

        if resets_in is None:
            resets_in_text = "unknown"
        else:
            resets_in_text = str(resets_in)

        message = (
            f"Toggl API limit returned {status_code}. "
            f"Remaining: {remaining_text}; "
            f"resets in: {resets_in_text} seconds."
        )

        super().__init__(message)
