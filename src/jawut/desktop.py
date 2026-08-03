"""Native file and folder dialogs, owned by the desktop window.

The window is created in :mod:`jawut.__main__`, which hands it here so the API can
reach it. Everything in this module therefore has two modes: with a window, it
opens a real Windows dialog; without one — a dev server in a browser, a test, a
packaged build run with ``--no-window`` — :func:`is_available` reports ``False``
and the frontend keeps its typed path field instead.

The dialogs block until the user answers, so callers must not run them on the
event loop; :mod:`jawut.routers.system` moves them to a worker thread.
"""

from __future__ import annotations

from typing import Any, Protocol

# pywebview's dialog type constants, repeated so this module imports without it.
FOLDER_DIALOG = 20
OPEN_DIALOG = 10


class Window(Protocol):
    """The part of ``webview.Window`` this module uses."""

    def create_file_dialog(
        self,
        dialog_type: int = ...,
        directory: str = ...,
        allow_multiple: bool = ...,
        save_filename: str = ...,
        file_types: tuple[str, ...] = ...,
    ) -> Any: ...


_window: Window | None = None


def set_window(window: Window | None) -> None:
    """Register the window that dialogs should be parented to."""
    global _window
    _window = window


def is_available() -> bool:
    """Whether a native dialog can be opened at all."""
    return _window is not None


def _first_path(result: Any) -> str | None:
    """Normalise a dialog result to one path, or ``None`` when cancelled.

    pywebview returns a sequence for open dialogs and ``None`` on cancel, but the
    exact type varies by platform backend — a tuple, a list, or a bare string.
    """
    if result is None:
        return None
    if isinstance(result, str):
        return result or None
    if isinstance(result, (list, tuple)):
        return str(result[0]) if result else None
    return str(result)


def pick_folder(directory: str = "") -> str | None:
    """Open a folder chooser. Returns the chosen path, or ``None`` if cancelled."""
    if _window is None:
        raise RuntimeError("no desktop window — native dialogs are unavailable")
    return _first_path(_window.create_file_dialog(FOLDER_DIALOG, directory=directory))


def pick_file(directory: str = "", file_types: tuple[str, ...] = ()) -> str | None:
    """Open a file chooser. Returns the chosen path, or ``None`` if cancelled."""
    if _window is None:
        raise RuntimeError("no desktop window — native dialogs are unavailable")
    return _first_path(
        _window.create_file_dialog(
            OPEN_DIALOG,
            directory=directory,
            allow_multiple=False,
            file_types=file_types,
        )
    )
