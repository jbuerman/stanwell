from pathlib import Path

import pandas as pd
import pytest

from stanwell.ui.dashboard.helpers import (
    numeric_sum,
    parse_dashboard_args,
)


def test_parse_dashboard_args_reads_config_path():
    arguments = [
        "--config",
        "somewhere/config.yml",
    ]

    result = parse_dashboard_args(arguments)

    assert result.config == Path("somewhere/config.yml")


def test_parse_dashboard_args_defaults_config_to_none():
    result = parse_dashboard_args([])

    assert result.config is None


def test_parse_dashboard_args_ignores_unknown_arguments():
    arguments = [
        "--something-from-streamlit",
        "value",
        "--config",
        "config.yml",
    ]

    result = parse_dashboard_args(arguments)

    assert result.config == Path("config.yml")


def test_numeric_sum():
    data = pd.DataFrame(
        {
            "hours": [
                1.0,
                2.5,
                3.0,
            ]
        }
    )

    result = numeric_sum(
        data,
        "hours",
    )

    assert result == pytest.approx(6.5)


def test_numeric_sum_treats_non_numeric_values_as_zero():
    data = pd.DataFrame(
        {
            "hours": [
                1.0,
                "not a number",
                None,
                2.0,
            ]
        }
    )

    result = numeric_sum(
        data,
        "hours",
    )

    assert result == pytest.approx(3.0)


def test_numeric_sum_returns_zero_for_empty_dataframe():
    data = pd.DataFrame()

    result = numeric_sum(
        data,
        "hours",
    )

    assert result == pytest.approx(0.0)


def test_numeric_sum_returns_zero_for_missing_column():
    data = pd.DataFrame({"something_else": [1, 2, 3]})

    result = numeric_sum(
        data,
        "hours",
    )

    assert result == pytest.approx(0.0)
