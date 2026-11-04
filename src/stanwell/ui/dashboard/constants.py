"""Define colour palettes shared by dashboard visualisations."""

from __future__ import annotations

WEEKDAY_PALETTE: dict[str, str] = {
    "Monday": "#81B29A",
    "Tuesday": "#81B29A",
    "Wednesday": "#81B29A",
    "Thursday": "#81B29A",
    "Friday": "#81B29A",
    "Saturday": "#E07A5F",
    "Sunday": "#E07A5F",
}


WORKING_PATTERN_PALETTE: dict[str, str] = {
    "Normal working hours": "#81B29A",
    "Outside core hours": "#F2CC8F",
    "Weekend": "#E07A5F",
    "Day off / holiday": "#B56576",
}
