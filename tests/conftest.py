"""Shared fixtures.

Integration tests run against a real SQLite file in ``tmp_path`` — nothing about storage
is mocked, since SQLite is the actual dependency rather than a stand-in for one. Test
images are real encoded files for the same reason: Pillow decoding and sha256 dedupe are
part of what the import path is supposed to get right.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from jawut import session
from jawut.app import create_app
from jawut.db import connection
from jawut.services import projects
from jawut.services.projects import Project


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep every test off the real settings file and out of each other's state."""
    monkeypatch.setenv("JAWUT_APP_DATA_DIR", str(tmp_path / "appdata"))
    session.clear()
    connection.close_all()
    yield
    session.clear()
    connection.close_all()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "project.db"


@pytest.fixture
def project(tmp_path: Path) -> Project:
    """A created, opened project. Most service tests need nothing more."""
    created = projects.create(tmp_path / "workspace", "Test Project")
    session.set_current(created)
    return created


@pytest.fixture
def conn(project: Project) -> sqlite3.Connection:
    return connection.connect(project.db_path)


MakeImage = Callable[..., Path]


@pytest.fixture
def make_image(tmp_path: Path) -> MakeImage:
    """Write a real image file, distinct by default so hashes never collide."""
    counter = {"n": 0}

    def _make(
        name: str,
        *,
        folder: Path | None = None,
        size: tuple[int, int] = (640, 480),
        color: tuple[int, int, int] | None = None,
    ) -> Path:
        counter["n"] += 1
        target = (folder or tmp_path / "source") / name
        target.parent.mkdir(parents=True, exist_ok=True)
        # Widely spaced channels: JPEG quantization collapses near-identical solid
        # colours into byte-identical files, which the importer would rightly treat
        # as duplicates.
        n = counter["n"]
        shade = color or (n * 53 % 256, n * 97 % 256, n * 151 % 256)
        Image.new("RGB", size, shade).save(target)
        return target

    return _make
