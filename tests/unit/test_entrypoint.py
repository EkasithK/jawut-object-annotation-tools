from __future__ import annotations

import socket
from pathlib import Path

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


# ── Unblocking the bundle ────────────────────────────────────────────────────


def test_running_from_source_has_no_bundle_to_unblock() -> None:
    """Nothing is frozen during development, so there is nothing to clear."""
    assert entry.bundle_dir() is None
    assert entry.unblock_bundle() is False


def test_the_bundle_directory_sits_beside_the_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(entry.sys, "frozen", True, raising=False)
    monkeypatch.setattr(entry.sys, "executable", str(tmp_path / "app.exe"))
    assert entry.bundle_dir() == tmp_path


def test_unblocking_is_skipped_off_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The internet mark is an NTFS alternate data stream; elsewhere there is none."""
    monkeypatch.setattr(entry.sys, "frozen", True, raising=False)
    monkeypatch.setattr(entry.sys, "executable", str(tmp_path / "app.exe"))
    monkeypatch.setattr(entry.sys, "platform", "linux")
    assert entry.unblock_bundle() is False


def _frozen_on_windows(monkeypatch: pytest.MonkeyPatch, root: Path) -> list[list[str]]:
    monkeypatch.setattr(entry.sys, "frozen", True, raising=False)
    monkeypatch.setattr(entry.sys, "executable", str(root / "app.exe"))
    monkeypatch.setattr(entry.sys, "platform", "win32")

    calls: list[list[str]] = []

    class Completed:
        returncode = 0

    def fake_run(argv: list[str], **kwargs: object) -> Completed:
        calls.append(argv)
        return Completed()

    monkeypatch.setattr(entry.subprocess, "run", fake_run)
    return calls


def test_unblocking_shells_out_to_unblock_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Deleting the stream in-process does not work on Windows; this does."""
    calls = _frozen_on_windows(monkeypatch, tmp_path)

    assert entry.unblock_bundle() is True

    argv = calls[0]
    # An absolute path, not a bare name: a user-writable powershell.exe earlier
    # on PATH would otherwise run as part of this launch.
    assert argv[0].endswith("powershell.exe")
    assert argv[0] != "powershell.exe"
    assert "Unblock-File" in argv[-1]
    assert str(tmp_path) in argv[-1]
    # -NonInteractive matters: a prompt would hang a build with no console.
    assert "-NonInteractive" in argv


def test_a_quote_in_the_path_cannot_break_out_of_the_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    odd = tmp_path / "kowz's tools"
    odd.mkdir()
    calls = _frozen_on_windows(monkeypatch, odd)

    entry.unblock_bundle()

    assert "kowz''s tools" in calls[0][-1]


def test_unblocking_reports_failure_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(entry.sys, "frozen", True, raising=False)
    monkeypatch.setattr(entry.sys, "executable", str(tmp_path / "app.exe"))
    monkeypatch.setattr(entry.sys, "platform", "win32")

    def explode(argv: list[str], **kwargs: object) -> None:
        raise OSError("powershell is not on PATH")

    monkeypatch.setattr(entry.subprocess, "run", explode)
    assert entry.unblock_bundle() is False


def test_a_slow_unblock_is_given_up_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A hung helper must not leave the user staring at nothing forever."""
    monkeypatch.setattr(entry.sys, "frozen", True, raising=False)
    monkeypatch.setattr(entry.sys, "executable", str(tmp_path / "app.exe"))
    monkeypatch.setattr(entry.sys, "platform", "win32")

    def timeout(argv: list[str], **kwargs: object) -> None:
        raise entry.subprocess.TimeoutExpired(cmd="powershell", timeout=1)

    monkeypatch.setattr(entry.subprocess, "run", timeout)
    assert entry.unblock_bundle() is False


# ── Falling back to the browser ──────────────────────────────────────────────


class FakeServer:
    should_exit = False


def test_a_failed_window_offers_the_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[str] = []
    opened: list[str] = []

    monkeypatch.setattr(
        entry, "message_box", lambda text, **_: (shown.append(text), entry.IDYES)[1]
    )
    monkeypatch.setattr(entry.webbrowser, "open", lambda url: opened.append(url))

    server = FakeServer()
    code = entry.offer_browser_fallback(
        server,  # type: ignore[arg-type]
        "http://127.0.0.1:9/",
        RuntimeError("Failed to resolve Python.Runtime.Loader.Initialize"),
    )

    assert code == 0
    assert opened == ["http://127.0.0.1:9/"]
    assert server.should_exit is True
    # The first dialog has to name the real cause, or nobody can act on it.
    assert "Unblock" in shown[0]
    assert "Python.Runtime.Loader.Initialize" in shown[0]


def test_declining_the_browser_stops_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(entry, "message_box", lambda text, **_: 7)  # IDNO
    opened: list[str] = []
    monkeypatch.setattr(entry.webbrowser, "open", lambda url: opened.append(url))

    server = FakeServer()
    code = entry.offer_browser_fallback(
        server,  # type: ignore[arg-type]
        "http://127.0.0.1:9/",
        RuntimeError("nope"),
    )

    assert code == 1
    assert opened == []
    assert server.should_exit is True


def test_message_box_falls_back_to_stderr_off_windows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(entry.sys, "platform", "linux")
    assert entry.message_box("something broke", "Caption") == 0
    assert "something broke" in capsys.readouterr().err
