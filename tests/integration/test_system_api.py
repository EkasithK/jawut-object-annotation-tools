"""The endpoints behind every Browse button."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jawut import desktop
from tests.unit.test_desktop import FakeWindow


@pytest.fixture(autouse=True)
def _clear_window() -> Iterator[None]:
    yield
    desktop.set_window(None)


def test_capabilities_reports_no_dialogs_when_headless(client: TestClient) -> None:
    desktop.set_window(None)
    body = client.get("/api/v1/system/capabilities").json()
    assert body["data"] == {"native_dialogs": False}


def test_capabilities_reports_dialogs_inside_the_window(client: TestClient) -> None:
    desktop.set_window(FakeWindow(None))
    assert client.get("/api/v1/system/capabilities").json()["data"] == {
        "native_dialogs": True
    }


def test_browsing_returns_the_chosen_folder(client: TestClient) -> None:
    desktop.set_window(FakeWindow(("C:\\datasets\\helmet",)))
    response = client.post("/api/v1/system/browse", json={"kind": "folder"})
    assert response.status_code == 200
    assert response.json()["data"] == {"path": "C:\\datasets\\helmet"}


def test_browsing_for_a_data_yaml_uses_a_file_dialog(client: TestClient) -> None:
    window = FakeWindow(("C:\\datasets\\data.yaml",))
    desktop.set_window(window)

    response = client.post("/api/v1/system/browse", json={"kind": "data_yaml"})
    assert response.json()["data"]["path"] == "C:\\datasets\\data.yaml"
    assert window.calls[0]["dialog_type"] == desktop.OPEN_DIALOG


def test_cancelling_is_not_an_error(client: TestClient) -> None:
    desktop.set_window(FakeWindow(None))
    response = client.post("/api/v1/system/browse", json={"kind": "folder"})
    assert response.status_code == 200
    assert response.json()["data"] == {"path": None}


def test_the_start_directory_is_passed_through(client: TestClient) -> None:
    window = FakeWindow(None)
    desktop.set_window(window)

    client.post(
        "/api/v1/system/browse",
        json={"kind": "folder", "start_in": "C:\\datasets"},
    )
    assert window.calls[0]["directory"] == "C:\\datasets"


def test_browsing_without_a_window_is_refused(client: TestClient) -> None:
    """The frontend asks capabilities first, so this is only reachable directly."""
    desktop.set_window(None)
    response = client.post("/api/v1/system/browse", json={"kind": "folder"})
    assert response.status_code == 409
    assert "desktop window" in response.json()["error"]["message"]


def test_an_unknown_kind_is_rejected(client: TestClient) -> None:
    desktop.set_window(FakeWindow(None))
    response = client.post("/api/v1/system/browse", json={"kind": "printer"})
    assert response.status_code == 422


def test_a_failing_dialog_surfaces_as_an_error(client: TestClient) -> None:
    class Broken:
        def create_file_dialog(self, *args: Any, **kwargs: Any) -> Any:
            raise OSError("the shell is unavailable")

    desktop.set_window(Broken())
    response = client.post("/api/v1/system/browse", json={"kind": "folder"})
    assert response.status_code == 500
    assert "file dialog failed" in response.json()["error"]["message"]
