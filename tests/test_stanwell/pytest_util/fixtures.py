import pytest

from stanwell.data_repository.database_schema import (
    initialise_database,
)
from stanwell.data_repository.db import connect_db


@pytest.fixture
def conn():
    connection = connect_db(":memory:")
    initialise_database(connection)

    yield connection

    connection.close()


@pytest.fixture
def cfg():
    return {
        "api_chunk_days": 2,
        "timezone": "Europe/London",
    }
