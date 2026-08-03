"""Native dialog plumbing.

The real dialogs cannot run headless, so these exercise the parts that decide
whether one is offered at all and how its answer is normalised — which is where
the platform differences live.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from jawut import desktop


class FakeWindow:
    """Stands in for ``webview.Window``, recording how it was called."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def create_file_dialog(
        self,
        dialog_type: int = desktop.OPEN_DIALOG,
        directory: str = "",
        allow_multiple: bool = False,
        save_filename: str = "",
        file_types: tuple[str, ...] = (),
    ) -> Any:
        self.calls.append(
            {
                "dialog_type": dialog_type,
                "directory": directory,
                "file_types": file_types,
            }
        )
        return self.result


@pytest.fixture(autouse=True)
def _clear_window() -> Iterator[None]:
    yield
    desktop.set_window(None)


def test_dialogs_are_unavailable_without_a_window() -> None:
    desktop.set_window(None)
    assert desktop.is_available() is False


def test_a_registered_window_makes_dialogs_available() -> None:
    desktop.set_window(FakeWindow(None))
    assert desktop.is_available() is True


def test_picking_a_folder_returns_the_chosen_path() -> None:
    window = FakeWindow(("C:\\datasets\\helmet",))
    desktop.set_window(window)

    assert desktop.pick_folder("C:\\datasets") == "C:\\datasets\\helmet"
    assert window.calls[0]["dialog_type"] == desktop.FOLDER_DIALOG
    assert window.calls[0]["directory"] == "C:\\datasets"


def test_picking_a_file_passes_the_type_filter() -> None:
    window = FakeWindow(["C:\\datasets\\data.yaml"])
    desktop.set_window(window)

    assert desktop.pick_file("", ("Dataset config (*.yaml)",)) == (
        "C:\\datasets\\data.yaml"
    )
    assert window.calls[0]["dialog_type"] == desktop.OPEN_DIALOG
    assert window.calls[0]["file_types"] == ("Dataset config (*.yaml)",)


@pytest.mark.parametrize(
    ("returned", "expected"),
    [
        (None, None),
        ((), None),
        ([], None),
        ("", None),
        ("C:\\a", "C:\\a"),
        (("C:\\a", "C:\\b"), "C:\\a"),
        (["C:\\a"], "C:\\a"),
    ],
)
def test_cancelling_and_the_backend_result_shapes(
    returned: Any, expected: str | None
) -> None:
    """Backends return a tuple, a list, a bare string, or nothing on cancel."""
    desktop.set_window(FakeWindow(returned))
    assert desktop.pick_folder() == expected


def test_picking_without_a_window_is_a_programming_error() -> None:
    desktop.set_window(None)
    with pytest.raises(RuntimeError, match="no desktop window"):
        desktop.pick_folder()
