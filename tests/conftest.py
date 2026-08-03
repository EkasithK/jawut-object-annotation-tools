"""Shared fixtures.

Integration tests run against a real SQLite file in ``tmp_path`` — nothing about storage
is mocked, since SQLite is the actual dependency rather than a stand-in for one.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jawut.app import create_app
from jawut.db import connection


@pytest.fixture(autouse=True)
def _isolate_connections() -> Iterator[None]:
    """Guarantee no connection leaks between tests."""
    connection.close_all()
    yield
    connection.close_all()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "project.db"
