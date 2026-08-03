from __future__ import annotations

import socket

import pytest

from jawut import __main__ as entry
from jawut import __version__


def test_free_port_is_actually_free() -> None:
    port = entry.free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


def test_free_port_varies_across_calls() -> None:
    ports = {entry.free_port() for _ in range(5)}
    assert len(ports) > 1


def test_defaults_open_a_window_on_an_os_assigned_port() -> None:
    args = entry.parse_args([])
    assert args.no_window is False
    assert args.port == 0


def test_no_window_is_available_for_debugging() -> None:
    assert entry.parse_args(["--no-window"]).no_window is True


def test_an_explicit_port_is_honoured() -> None:
    assert entry.parse_args(["--port", "9001"]).port == 9001


def test_version_is_reported() -> None:
    with pytest.raises(SystemExit) as excinfo:
        entry.parse_args(["--version"])
    assert excinfo.value.code == 0


def test_the_server_subclass_skips_signal_handlers() -> None:
    """Signal handlers can only be installed on the main thread, and the server
    runs on a worker so the window can own the process."""
    assert entry.Server.install_signal_handlers is not None


def test_a_missing_pywebview_fails_with_guidance(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import builtins

    real_import = builtins.__import__

    def blocked(name: str, *args: object, **kwargs: object) -> object:
        if name == "webview":
            raise ImportError("no module named webview")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", blocked)

    assert entry.run_windowed(0, "token") == 1
    assert "pywebview" in capsys.readouterr().err


def test_version_string_is_exposed() -> None:
    assert __version__


def test_missing_streams_are_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    """A windowed Windows build starts with stdout and stderr set to None; the
    first print would otherwise kill the process before it serves anything."""
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)

    entry.ensure_streams()

    import sys as sys_module

    assert sys_module.stdout is not None
    assert sys_module.stderr is not None
    print("this must not raise")


def test_existing_streams_are_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys as sys_module

    replacement = io.StringIO()
    monkeypatch.setattr("sys.stdout", replacement)

    entry.ensure_streams()

    assert sys_module.stdout is replacement


def test_a_supplied_token_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """A windowed build cannot print its token, so a caller may supply one."""
    from jawut.app import LAUNCH_TOKEN_ENV

    monkeypatch.setenv(LAUNCH_TOKEN_ENV, "supplied-token")
    captured: dict[str, str] = {}

    def fake_headless(port: int, token: str) -> int:
        captured["token"] = token
        return 0

    monkeypatch.setattr(entry, "run_headless", fake_headless)
    entry.main(["--no-window", "--port", "9999"])

    assert captured["token"] == "supplied-token"


def test_a_token_is_generated_when_none_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jawut.app import LAUNCH_TOKEN_ENV

    monkeypatch.delenv(LAUNCH_TOKEN_ENV, raising=False)
    captured: dict[str, str] = {}

    def fake_headless(port: int, token: str) -> int:
        captured["token"] = token
        return 0

    monkeypatch.setattr(entry, "run_headless", fake_headless)
    entry.main(["--no-window"])

    assert len(captured["token"]) > 20
