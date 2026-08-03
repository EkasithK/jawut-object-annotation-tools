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
"""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import sys
import threading

import uvicorn

from jawut import APP_NAME, __version__
from jawut.app import LAUNCH_TOKEN_ENV

DEFAULT_WINDOW = (1360, 860)
MINIMUM_WINDOW = (1024, 640)


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

    # The token reaches the page through the server, which injects it into
    # index.html. Doing it here instead would race the app's first request.
    webview.create_window(
        APP_NAME,
        f"http://127.0.0.1:{port}/",
        width=DEFAULT_WINDOW[0],
        height=DEFAULT_WINDOW[1],
        min_size=MINIMUM_WINDOW,
        background_color="#0e1013",
        text_select=False,
    )
    webview.start(private_mode=False)

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
