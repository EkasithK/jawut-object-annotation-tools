from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from jawut import __version__
from jawut.app import LAUNCH_TOKEN_ENV, create_app, require_launch_token
from jawut.db import connection


def test_health_reports_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"status": "ok", "version": __version__}
    assert body["error"] is None


def test_every_response_carries_envelope_meta(client: TestClient) -> None:
    meta = client.get("/health").json()["meta"]
    assert meta["request_id"]
    assert meta["timestamp"]


def test_ready_is_healthy_with_no_project_open(client: TestClient) -> None:
    assert client.get("/ready").json()["data"] == {"db": "no project open"}


def test_ready_reflects_an_open_project(client: TestClient, db_path: Path) -> None:
    connection.connect(db_path)
    assert client.get("/ready").json()["data"] == {"db": "ok"}


def test_errors_use_the_envelope_error_shape(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["data"] is None
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["meta"]["request_id"]


def test_lifespan_shutdown_closes_connections(db_path: Path) -> None:
    with TestClient(create_app()):
        connection.connect(db_path)
    assert connection.probe() == "no project open"


def test_launch_token_is_skipped_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LAUNCH_TOKEN_ENV, raising=False)
    require_launch_token(x_jawut_token=None)


def test_launch_token_rejects_a_wrong_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAUNCH_TOKEN_ENV, "secret")
    with pytest.raises(HTTPException) as excinfo:
        require_launch_token(x_jawut_token="guess")
    assert excinfo.value.status_code == 401


def test_launch_token_rejects_a_missing_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAUNCH_TOKEN_ENV, "secret")
    with pytest.raises(HTTPException):
        require_launch_token(x_jawut_token=None)


def test_launch_token_accepts_the_right_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAUNCH_TOKEN_ENV, "secret")
    require_launch_token(x_jawut_token="secret")
