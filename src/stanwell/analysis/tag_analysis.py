"""Analyse recorded time using user-selected entry tags.

Entries are classified according to selected desirable and undesirable
tags. Each entry contributes once to aggregate quality calculations,
regardless of how many tags it contains.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

ConflictPolicy = Literal[
    "neutral",
    "bad_wins",
    "good_wins",
]

TAG_SCORE_COLUMNS = [
    "week_start",
    "total_hours",
    "matched_hours",
    "good_hours",
    "bad_hours",
    "conflicted_hours",
    "neutral_hours",
    "good_share",
    "bad_share",
    "matched_share",
    "weekly_quality",
]

TAG_ANALYSIS_COLUMNS = [
    "entry_id",
    "day",
    "week_start",
    "hours",
    "selected_tags",
]

MIN_TREND_DATA_POINTS = 2


def get_available_tags(
    connection: sqlite3.Connection,
) -> list[str]:
    """Return all non-empty tags stored locally.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.

    Returns
    -------
    list[str]
        Distinct tags in alphabetical order.

    """
    rows = connection.execute("""
        SELECT DISTINCT tag
        FROM time_entry_tags
        WHERE tag IS NOT NULL
          AND TRIM(tag) <> ''
        ORDER BY tag
        """).fetchall()

    tags = [str(row["tag"]) for row in rows]

    return tags


def _classify_tags(
    entry_tags: set[str],
    good_tags: set[str],
    bad_tags: set[str],
    conflict_policy: ConflictPolicy,
) -> tuple[str, float]:
    """Classify one entry from its selected tags."""
    has_good_tag = len(entry_tags & good_tags) > 0
    has_bad_tag = len(entry_tags & bad_tags) > 0

    if has_good_tag and has_bad_tag:
        classification = "conflicted"

        if conflict_policy == "bad_wins":
            value = -1.0
        elif conflict_policy == "good_wins":
            value = 1.0
        else:
            value = 0.0
    elif has_good_tag:
        classification = "good"
        value = 1.0
    elif has_bad_tag:
        classification = "bad"
        value = -1.0
    else:
        classification = "neutral"
        value = 0.0

    result = (
        classification,
        value,
    )

    return result


def get_weekly_tag_scores(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
    start_date: date,
    end_date: date,
    good_tags: Sequence[str],
    bad_tags: Sequence[str],
    conflict_policy: ConflictPolicy = "neutral",
) -> pd.DataFrame:
    """Calculate weekly quality measures from selected tags.

    Each entry contributes once. Good entries have value +1, neutral
    entries value 0 and bad entries value -1. Conflicted entries are
    handled according to ``conflict_policy``.

    ``weekly_quality`` maps the duration-weighted mean classification
    from -1..1 onto 0..100.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Configuration containing ``timezone``.
    start_date : date
        First date to include.
    end_date : date
        Last date to include.
    good_tags : Sequence[str]
        Tags considered desirable.
    bad_tags : Sequence[str]
        Tags considered undesirable.
    conflict_policy : {"neutral", "bad_wins", "good_wins"}, default="neutral"
        Classification applied when an entry contains both good and bad
        tags.

    Returns
    -------
    pandas.DataFrame
        Weekly tag-based working-time measures.

    """
    good_tag_set = set(good_tags)
    bad_tag_set = set(bad_tags)

    weekly = pd.DataFrame(columns=TAG_SCORE_COLUMNS)

    if len(good_tag_set) > 0 or len(bad_tag_set) > 0:
        entries = pd.read_sql_query(
            """
            SELECT
                id,
                start_utc,
                duration_seconds
            FROM time_entries
            WHERE DATE(start_utc)
                BETWEEN ? AND ?
              AND stop_utc IS NOT NULL
              AND duration_seconds >= 0
            """,
            connection,
            params=[
                start_date.isoformat(),
                end_date.isoformat(),
            ],
        )

        if entries.empty is False:
            tag_rows = pd.read_sql_query(
                """
                SELECT
                    time_entry_id,
                    tag
                FROM time_entry_tags
                WHERE time_entry_id IN (
                    SELECT id
                    FROM time_entries
                    WHERE DATE(start_utc)
                        BETWEEN ? AND ?
                )
                """,
                connection,
                params=[
                    start_date.isoformat(),
                    end_date.isoformat(),
                ],
            )

            entries["start_utc"] = pd.to_datetime(
                entries["start_utc"],
                errors="coerce",
                utc=True,
            )
            entries = entries.dropna(subset=["start_utc"])

            entries["duration_seconds"] = (
                pd.to_numeric(
                    entries["duration_seconds"],
                    errors="coerce",
                )
                .fillna(0.0)
                .clip(lower=0.0)
            )

            entries["day"] = (
                entries["start_utc"].dt.tz_convert(config["timezone"]).dt.date
            )

            entry_dates = pd.to_datetime(entries["day"])
            entries["week_start"] = entry_dates - pd.to_timedelta(
                entry_dates.dt.weekday,
                unit="D",
            )

            tags_by_entry: dict[int, set[str]] = {}

            if tag_rows.empty is False:
                for entry_id, tags in tag_rows.groupby("time_entry_id")["tag"]:
                    typed_entry_id = cast(int, entry_id)

                    tags_by_entry[typed_entry_id] = {str(tag) for tag in tags}

            classifications: list[dict[str, Any]] = []

            for entry in entries.itertuples():
                entry_id = cast(int, entry.id)
                entry_tags = tags_by_entry.get(
                    entry_id,
                    set(),
                )

                classification, entry_value = _classify_tags(
                    entry_tags=entry_tags,
                    good_tags=good_tag_set,
                    bad_tags=bad_tag_set,
                    conflict_policy=conflict_policy,
                )

                classifications.append(
                    {
                        "id": entry.id,
                        "classification": (classification),
                        "entry_value": entry_value,
                    }
                )

            classification_data = pd.DataFrame(classifications)

            entries = entries.merge(
                classification_data,
                on="id",
                how="left",
            )

            entries["weighted_value"] = (
                entries["duration_seconds"] * entries["entry_value"]
            )

            for classification in (
                "good",
                "bad",
                "conflicted",
                "neutral",
            ):
                entries[f"{classification}_seconds"] = entries[
                    "duration_seconds"
                ].where(
                    entries["classification"] == classification,
                    0.0,
                )

            entries["matched_seconds"] = entries["duration_seconds"].where(
                entries["classification"] != "neutral",
                0.0,
            )

            weekly = entries.groupby(
                "week_start",
                as_index=False,
            ).agg(
                total_seconds=(
                    "duration_seconds",
                    "sum",
                ),
                matched_seconds=(
                    "matched_seconds",
                    "sum",
                ),
                good_seconds=(
                    "good_seconds",
                    "sum",
                ),
                bad_seconds=(
                    "bad_seconds",
                    "sum",
                ),
                conflicted_seconds=(
                    "conflicted_seconds",
                    "sum",
                ),
                neutral_seconds=(
                    "neutral_seconds",
                    "sum",
                ),
                weighted_value=(
                    "weighted_value",
                    "sum",
                ),
            )

            for category in (
                "total",
                "matched",
                "good",
                "bad",
                "conflicted",
                "neutral",
            ):
                weekly[f"{category}_hours"] = weekly[f"{category}_seconds"] / 3600.0

            total_seconds = weekly["total_seconds"].replace(
                0,
                pd.NA,
            )

            weekly["good_share"] = (weekly["good_seconds"] / total_seconds).fillna(0.0)

            weekly["bad_share"] = (weekly["bad_seconds"] / total_seconds).fillna(0.0)

            weekly["matched_share"] = (
                weekly["matched_seconds"] / total_seconds
            ).fillna(0.0)

            weighted_mean = (weekly["weighted_value"] / total_seconds).fillna(0.0)

            weekly["weekly_quality"] = (50.0 + 50.0 * weighted_mean).clip(
                lower=0.0,
                upper=100.0,
            )

            weekly = weekly[TAG_SCORE_COLUMNS]

    return weekly


def get_tag_analysis(
    connection: sqlite3.Connection,
    config: Mapping[str, Any],
    start_date: date,
    end_date: date,
    selected_tags: Sequence[str],
) -> pd.DataFrame:
    """Return per-entry data for selected-tag analysis.

    Each time entry appears once with its duration and the subset of
    selected tags attached to that entry.

    Parameters
    ----------
    connection : sqlite3.Connection
        Connection to the application's SQLite database.
    config : collections.abc.Mapping
        Configuration containing ``timezone``.
    start_date : date
        First local date to include.
    end_date : date
        Last local date to include.
    selected_tags : Sequence[str]
        Tags to retain for analysis.

    Returns
    -------
    pandas.DataFrame
        Per-entry tag-analysis data.

    """
    result = pd.DataFrame(columns=TAG_ANALYSIS_COLUMNS)

    if len(selected_tags) > 0:
        entries = pd.read_sql_query(
            """
            SELECT
                id AS entry_id,
                start_utc,
                duration_seconds
            FROM time_entries
            WHERE duration_seconds > 0
            """,
            connection,
        )

        if entries.empty is False:
            entries["start_utc"] = pd.to_datetime(
                entries["start_utc"],
                format="ISO8601",
                errors="coerce",
                utc=True,
            )
            entries = entries.dropna(subset=["start_utc"])

            entries["start_local"] = entries["start_utc"].dt.tz_convert(
                config["timezone"]
            )
            entries["day"] = entries["start_local"].dt.date

            entries = entries[
                (entries["day"] >= start_date) & (entries["day"] <= end_date)
            ].copy()

            if entries.empty is False:
                entries["hours"] = (
                    pd.to_numeric(
                        entries["duration_seconds"],
                        errors="coerce",
                    ).fillna(0.0)
                    / 3600.0
                )

                entry_dates = pd.to_datetime(entries["day"])
                entries["week_start"] = entry_dates - pd.to_timedelta(
                    entry_dates.dt.weekday,
                    unit="D",
                )

                entry_ids = entries["entry_id"].astype(int).tolist()

                placeholders = ",".join("?" for _ in entry_ids)

                tag_rows = pd.read_sql_query(
                    f"""
                    SELECT
                        time_entry_id,
                        tag
                    FROM time_entry_tags
                    WHERE time_entry_id IN (
                        {placeholders}
                    )
                    """,
                    connection,
                    params=entry_ids,
                )

                tags_by_entry: dict[int, set[str]] = {}

                if not tag_rows.empty:
                    for entry_id, tags in tag_rows.groupby("time_entry_id")["tag"]:
                        typed_entry_id = cast(int, entry_id)

                        tags_by_entry[typed_entry_id] = {str(tag) for tag in tags}

                selected_tag_set = set(selected_tags)

                entries["selected_tags"] = entries["entry_id"].map(
                    lambda entry_id: (
                        tags_by_entry.get(
                            int(entry_id),
                            set(),
                        )
                        & selected_tag_set
                    )
                )

                result = entries[TAG_ANALYSIS_COLUMNS].reset_index(drop=True)

    return result


def tag_trend_delta(
    tag_entries: pd.DataFrame,
    tag: str,
    span: int = 4,
) -> float | None:
    """Estimate the trend in a tag's weekly share.

    Weekly tag shares are exponentially smoothed before a linear slope is
    fitted. Positive values indicate an increasing share and negative values
    indicate a decreasing share.

    Parameters
    ----------
    tag_entries : pandas.DataFrame
        Per-entry tag-analysis data.
    tag : str
        Tag whose trend should be measured.
    span : int, default=4
        Maximum span used for exponential smoothing.

    Returns
    -------
    float or None
        Linear slope of the smoothed weekly percentage share, or ``None``
        when fewer than two usable weekly values are available.

    """
    weekly_total_hours = tag_entries.groupby("week_start")["hours"].sum()

    tagged_entries = tag_entries[
        tag_entries["selected_tags"].apply(lambda tags: tag in tags)
    ]

    weekly_tag_hours = tagged_entries.groupby("week_start")["hours"].sum()

    shares: list[float] = []

    for (
        week_start,
        total_hours,
    ) in weekly_total_hours.items():
        if total_hours > 0:
            tag_hours = weekly_tag_hours.get(
                week_start,
                0.0,
            )
            shares.append(float(tag_hours) / float(total_hours) * 100.0)

    slope: float | None = None

    if len(shares) >= MIN_TREND_DATA_POINTS:
        values = pd.Series(
            shares,
            dtype=float,
        )
        smoothed_values = values.ewm(
            span=min(span, len(values)),
            adjust=False,
        ).mean()

        positions = np.arange(
            len(smoothed_values),
            dtype=float,
        )

        slope = float(
            np.polyfit(
                positions,
                smoothed_values.to_numpy(),
                1,
            )[0]
        )

    return slope


def has_tag(
    tags: set[str],
    tag: str,
) -> bool:
    """Return whether a set contains a tag.

    Parameters
    ----------
    tags : set[str]
        Tags to inspect.
    tag : str
        Tag to find.

    Returns
    -------
    bool
        ``True`` when ``tag`` is present.

    """
    result = tag in tags

    return result
