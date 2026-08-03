"""Desktop entry point.

Starts the FastAPI server on loopback and opens a native window pointed at it.
Three details matter for the packaged application:

* **Port 0.** The OS picks a free port, so two copies never collide and no fixed
  port has to be reserved.
* **A per-launch token.** The port is discoverable by anything on the machine, so
  every request must carry a secret generated at startup and injected into the
  page. Without it another local process could drive the API.
* **The window owns the process.** Closing it shuts the server down, rather than
  leaving a stray process holding the project database open.
* **The bundle unblocks itself.** See :func:`unblock_bundle` — without it a build
  extracted from a downloaded zip cannot open its own window at all.
"""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from jawut import APP_NAME, __version__, desktop
from jawut.app import LAUNCH_TOKEN_ENV

DEFAULT_WINDOW = (1360, 860)
MINIMUM_WINDOW = (1024, 640)

#: user32 MessageBox flags, repeated so this imports on every platform.
MB_YESNO = 0x04
MB_ICONWARNING = 0x30
IDYES = 6

#: The alternate data stream Windows attaches to anything downloaded.
ZONE_STREAM = "Zone.Identifier"

#: CREATE_NO_WINDOW. A windowed build must not flash a console when it shells
#: out. Ignored on other platforms, where the helper never runs.
CREATE_NO_WINDOW = 0x08000000


def bundle_dir() -> Path | None:
    """Where PyInstaller put our files, or ``None`` when running from source."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).parent


def powershell_path() -> str:
    """The absolute path to Windows PowerShell.

    Spelled out rather than left to ``PATH``: a bare name would run whatever
    ``powershell.exe`` happened to come first, which in a user-writable
    directory is somebody else's code running inside this process's launch.
    """
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(
        system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
    )


def unblock_bundle(timeout: float = 60.0) -> bool:
    """Strip the "came from the internet" mark from the files we shipped.

    Windows tags a downloaded zip, and Explorer's *Extract All* copies that tag
    onto every file it extracts. .NET Framework then refuses to load
    ``Python.Runtime.dll`` out of an internet-zone file, and pywebview — which
    needs it to open the window on Windows — dies before anything reaches the
    screen. The user sees a stack trace and an application that will not start,
    with nothing to suggest the cause is a file property rather than a bug.

    Delegated to PowerShell's ``Unblock-File`` rather than done in-process,
    which was tried first and does not work: deleting an alternate data stream
    by path fails on Windows with "the filename, directory name, or volume
    label syntax is incorrect", both from :func:`os.remove` and from ``del``.
    ``Unblock-File`` is the mechanism Windows documents for this, it ships with
    every supported version, and it needs no elevation because the user owns
    these files.

    Runs on every frozen launch rather than only when a mark is detected —
    detecting one means reading the stream that cannot reliably be addressed in
    the first place. It costs roughly a second, and only for the packaged build.

    Never raises: failing here only risks the window not opening, which the
    caller already handles.
    """
    root = bundle_dir()
    if root is None or sys.platform != "win32":
        return False

    # A single quote in the path would end the string literal early; PowerShell
    # escapes one by doubling it.
    quoted = str(root).replace("'", "''")
    script = f"Get-ChildItem -LiteralPath '{quoted}' -Recurse -File | Unblock-File"

    try:
        completed = subprocess.run(  # noqa: S603  fixed argv, no shell
            [
                powershell_path(),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            timeout=timeout,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def message_box(text: str, caption: str = APP_NAME, style: int = 0) -> int:
    """A native dialog drawn by user32 — no .NET, and no window of our own.

    Deliberately not pywebview: this is what reports that pywebview failed.
    """
    if sys.platform != "win32":
        print(f"{caption}: {text}", file=sys.stderr)
        return 0

    import ctypes

    return int(ctypes.windll.user32.MessageBoxW(None, text, caption, style))


def ensure_streams() -> None:
    """Give the process usable output streams even when Windows withholds them.

    A windowed build has no console, so ``sys.stdout`` and ``sys.stderr`` are
    ``None``. The first ``print`` then raises, and uvicorn's logging setup fails
    the same way — which kills the application before it ever serves a request.
    Pointing them at the null device keeps it alive whether or not anyone is
    watching the output.
    """
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115


def free_port() -> int:
    """Ask the OS for a free port and release it immediately."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Server(uvicorn.Server):
    """A uvicorn server that can be started on a thread and stopped cleanly."""

    def install_signal_handlers(self) -> None:
        # Signal handlers can only be installed on the main thread, and the window
        # is what ends this process anyway.
        return


def _serve(port: int, token: str) -> Server:
    os.environ[LAUNCH_TOKEN_ENV] = token

    from jawut.app import create_app

    config = uvicorn.Config(
        create_app(),
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="jawut-server")
    thread.start()
    return server


def run_windowed(port: int, token: str) -> int:
    """Open the native window. Returns the process exit code."""
    # Before importing pywebview, not after: importing it is what loads the .NET
    # assembly that a blocked file makes unloadable.
    unblock_bundle()

    try:
        import webview
    except ImportError:
        print(
            "The desktop window needs pywebview. Install it with\n"
            "    pip install 'jawut[desktop]'\n"
            "or run with --no-window and open the printed address yourself.",
            file=sys.stderr,
        )
        return 1

    server = _serve(port, token)
    url = f"http://127.0.0.1:{port}/"

    try:
        # The token reaches the page through the server, which injects it into
        # index.html. Doing it here instead would race the app's first request.
        window = webview.create_window(
            APP_NAME,
            url,
            width=DEFAULT_WINDOW[0],
            height=DEFAULT_WINDOW[1],
            min_size=MINIMUM_WINDOW,
            background_color="#f7f3ea",
            text_select=False,
        )
        # Native Browse buttons need this handle; without it the API reports that
        # dialogs are unavailable and the frontend leaves its typed field in place.
        desktop.set_window(window)
        webview.start(private_mode=False)
    except Exception as exc:  # noqa: BLE001  any GUI failure must stay recoverable
        desktop.set_window(None)
        return offer_browser_fallback(server, url, exc)

    desktop.set_window(None)
    server.should_exit = True
    return 0


def offer_browser_fallback(server: Server, url: str, exc: Exception) -> int:
    """Explain why the window did not open, and offer the browser instead.

    A windowed build has no console, so an unhandled exception here is invisible
    — the application simply fails to appear. Anything that stops the GUI
    toolkit loading still leaves a perfectly good server running, so the work is
    reachable either way rather than lost.
    """
    answer = message_box(
        f"{APP_NAME} could not open its own window.\n\n"
        f"{type(exc).__name__}: {exc}\n\n"
        "This is nearly always Windows blocking the files because they came out "
        "of a downloaded zip. To fix it for good: close this, right-click the "
        "folder you extracted, choose Properties, tick Unblock, click OK, and "
        "start it again.\n\n"
        "Open it in your web browser instead for now?",
        style=MB_YESNO | MB_ICONWARNING,
    )
    if answer != IDYES:
        server.should_exit = True
        return 1

    webbrowser.open(url)
    # A modal is the only close button the user has left, since the window that
    # would normally own the process never opened.
    message_box(
        f"{APP_NAME} is running at {url} in your browser.\n\n"
        "Leave this message open while you work, and click OK to stop it.\n\n"
        "The Browse buttons cannot appear in a browser tab — type or paste "
        "folder paths instead.",
    )
    server.should_exit = True
    return 0


def run_headless(port: int, token: str) -> int:
    """Serve without a window, for development and for debugging a packaged build."""
    server = _serve(port, token)
    # Flushed explicitly: stdout is block-buffered when this is piped to a file,
    # and the address would otherwise not appear until the process ended.
    print(f"{APP_NAME} {__version__}", flush=True)
    print(f"  serving  http://127.0.0.1:{port}/", flush=True)
    print(f"  token    {token}", flush=True)
    print("  press Ctrl+C to stop", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    server.should_exit = True
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jawut", description=APP_NAME)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="serve without opening a window and print the address",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="port to bind (0 asks the operating system for a free one)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ensure_streams()
    args = parse_args(argv)
    port = args.port or free_port()
    # A caller may supply the token — a windowed build has nowhere to print it,
    # so an automated check could not otherwise learn what it is.
    token = os.environ.get(LAUNCH_TOKEN_ENV) or secrets.token_urlsafe(32)

    if args.no_window:
        return run_headless(port, token)
    return run_windowed(port, token)


if __name__ == "__main__":
    sys.exit(main())
