"""Provide small utility functions used by the Streamlit dashboard.

The helpers in this module deal with dashboard command-line arguments and
safe numeric operations on DataFrames. Application analysis and database
queries belong in their corresponding analysis or repository modules.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd


def parse_dashboard_args(
    arguments: Sequence[str] | None = None,
) -> argparse.Namespace:
    """Parse arguments passed to the Streamlit dashboard.

    Unknown arguments are ignored because Streamlit adds its own command-line
    arguments before those supplied to the dashboard application.

    Parameters
    ----------
    arguments : Sequence[str] or None, optional
        Arguments to parse. If omitted, command-line arguments from
        ``sys.argv`` are used.

    Returns
    -------
    argparse.Namespace
        Parsed dashboard arguments.

    """
    parser = argparse.ArgumentParser(
        add_help=False,
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=None,
    )

    if arguments is None:
        arguments_to_parse = sys.argv[1:]
    else:
        arguments_to_parse = list(arguments)

    parsed_arguments, _ = parser.parse_known_args(arguments_to_parse)

    return parsed_arguments


def numeric_sum(
    data: pd.DataFrame,
    column: str,
) -> float:
    """Return the numeric total of a DataFrame column.

    Non-numeric and missing values are treated as zero. An empty DataFrame
    or a missing column also produces zero.

    Parameters
    ----------
    data : pandas.DataFrame
        Data containing the values to sum.
    column : str
        Name of the column to sum.

    Returns
    -------
    float
        Sum of the numeric values in the column.

    """
    total = 0.0

    if data.empty is False and column in data.columns:
        numeric_values = pd.to_numeric(
            data[column],
            errors="coerce",
        ).fillna(0.0)

        total = float(numeric_values.sum())

    return total
