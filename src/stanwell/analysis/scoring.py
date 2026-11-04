"""Calculate smoothed working-pattern and tag-based quality scores."""

from __future__ import annotations

import pandas as pd

WORKING_SCORE_COLUMNS = [
    "weekend_quality",
    "core_hours_quality",
    "day_off_quality",
    "overall_quality",
    "weekend_score",
    "core_hours_score",
    "day_off_score",
    "overall_score",
]


def _calculate_retention(
    half_life_weeks: float,
) -> float:
    """Calculate exponential retention from a half-life.

    Parameters
    ----------
    half_life_weeks : float
        Number of weeks over which historical influence halves.

    Returns
    -------
    float
        Retention applied to the previous score.

    Raises
    ------
    ValueError
        If ``half_life_weeks`` is not greater than zero.

    """
    if half_life_weeks <= 0:
        raise ValueError("half_life_weeks must be greater than 0")

    retention = 0.5 ** (1.0 / half_life_weeks)

    return retention


def _smooth_values(
    weekly: pd.DataFrame,
    quality_column: str,
    half_life_weeks: float,
    minimum_week_hours: float,
) -> list[float | None]:
    """Smooth weekly quality values using exponential retention."""
    retention = _calculate_retention(half_life_weeks)
    current_weight = 1.0 - retention

    scores: list[float | None] = []
    previous_score: float | None = None

    for weekly_hours, current_quality in zip(
        weekly["total_hours"].astype(float),
        weekly[quality_column].astype(float),
        strict=True,
    ):
        if weekly_hours >= minimum_week_hours:
            if previous_score is None:
                new_score = current_quality
            else:
                new_score = (
                    previous_score * retention + current_quality * current_weight
                )

            new_score = max(
                0.0,
                min(100.0, new_score),
            )

            previous_score = new_score
            scores.append(new_score)
        else:
            scores.append(previous_score)

    return scores


def add_smoothed_working_scores(
    weekly: pd.DataFrame,
    half_life_weeks: float = 6.0,
    minimum_week_hours: float = 1.0,
) -> pd.DataFrame:
    """Add raw and smoothed working-pattern quality scores.

    Quality and score values range from 0 to 100. Higher values indicate
    that a smaller proportion of recorded time fell into the relevant
    exceptional working category.

    Weeks below ``minimum_week_hours`` do not update the smoothed score.

    Parameters
    ----------
    weekly : pandas.DataFrame
        Weekly working-pattern totals.
    half_life_weeks : float, default=6.0
        Half-life used for exponential score smoothing.
    minimum_week_hours : float, default=1.0
        Minimum recorded hours required to update a score.

    Returns
    -------
    pandas.DataFrame
        Copy of ``weekly`` containing raw quality values and smoothed
        scores.

    """
    result = weekly.copy()

    if result.empty:
        for column in WORKING_SCORE_COLUMNS:
            result[column] = pd.Series(dtype=float)
    else:
        result = result.sort_values("week_start").reset_index(drop=True)

        total_hours = result["total_hours"].replace(
            0,
            pd.NA,
        )

        result["weekend_share"] = (result["weekend_hours"] / total_hours).fillna(0.0)

        result["outside_core_share"] = (
            result["outside_core_hours"] / total_hours
        ).fillna(0.0)

        result["non_working_day_share"] = (
            result["non_working_day_hours"] / total_hours
        ).fillna(0.0)

        result["undesirable_share"] = (
            result["weekend_share"]
            + result["outside_core_share"]
            + result["non_working_day_share"]
        ).clip(
            lower=0.0,
            upper=1.0,
        )

        result["weekend_quality"] = (100.0 * (1.0 - result["weekend_share"])).clip(
            0.0, 100.0
        )

        result["core_hours_quality"] = (
            100.0 * (1.0 - result["outside_core_share"])
        ).clip(0.0, 100.0)

        result["day_off_quality"] = (
            100.0 * (1.0 - result["non_working_day_share"])
        ).clip(0.0, 100.0)

        result["overall_quality"] = (100.0 * (1.0 - result["undesirable_share"])).clip(
            0.0, 100.0
        )

        result["weekend_score"] = _smooth_values(
            weekly=result,
            quality_column="weekend_quality",
            half_life_weeks=half_life_weeks,
            minimum_week_hours=minimum_week_hours,
        )
        result["core_hours_score"] = _smooth_values(
            weekly=result,
            quality_column="core_hours_quality",
            half_life_weeks=half_life_weeks,
            minimum_week_hours=minimum_week_hours,
        )
        result["day_off_score"] = _smooth_values(
            weekly=result,
            quality_column="day_off_quality",
            half_life_weeks=half_life_weeks,
            minimum_week_hours=minimum_week_hours,
        )
        result["overall_score"] = _smooth_values(
            weekly=result,
            quality_column="overall_quality",
            half_life_weeks=half_life_weeks,
            minimum_week_hours=minimum_week_hours,
        )

    return result


def add_smoothed_tag_score(
    weekly: pd.DataFrame,
    half_life_weeks: float = 6.0,
    minimum_week_hours: float = 1.0,
) -> pd.DataFrame:
    """Add an exponentially smoothed tag-quality score.

    Weeks below ``minimum_week_hours`` retain the preceding score rather
    than updating it from potentially incomplete data.

    Parameters
    ----------
    weekly : pandas.DataFrame
        Weekly tag-quality values.
    half_life_weeks : float, default=6.0
        Half-life used for exponential smoothing.
    minimum_week_hours : float, default=1.0
        Minimum recorded hours required to update the score.

    Returns
    -------
    pandas.DataFrame
        Copy of ``weekly`` containing ``smoothed_score``.

    """
    result = weekly.copy()

    if result.empty:
        result["smoothed_score"] = pd.Series(dtype=float)
    else:
        result = result.sort_values("week_start").reset_index(drop=True)

        result["smoothed_score"] = _smooth_values(
            weekly=result,
            quality_column="weekly_quality",
            half_life_weeks=half_life_weeks,
            minimum_week_hours=minimum_week_hours,
        )

    return result
