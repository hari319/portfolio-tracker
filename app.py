"""Entry point for the Portfolio and Stock Monitor.

    python app.py                 # opens a native desktop window
    python app.py --browser       # opens in the system browser
    python app.py --debug         # Flask debug mode, opens in browser
    python app.py --port 8000     # custom port
"""

from __future__ import annotations

import argparse
import logging
import socket
import threading
import time

from stockmon.logging_config import configure_logging
from stockmon.paths import APP_LOG_FILE, ensure_directories
from stockmon.db import open_database, open_screener_cache
from stockmon.web import create_app

configure_logging(APP_LOG_FILE)
logger = logging.getLogger("stockmon.app")

ensure_directories()
open_database()
open_screener_cache()
app = create_app()


def _wait_for_server(host: str, port: int, timeout: float = 5.0) -> bool:
    """Block until Flask is accepting connections (or *timeout* seconds elapse)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Portfolio and Stock Monitor.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode (opens in browser)")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open in the system browser instead of a desktop window",
    )
    args = parser.parse_args()

    if args.debug or args.browser:
        # ---------- browser mode ----------
        logger.info("Starting web UI on http://%s:%s (browser mode)", args.host, args.port)
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            threaded=True,
            use_reloader=args.debug,
        )
    else:
        # ---------- desktop window mode ----------
        import webview

        webview.settings["ALLOW_DOWNLOADS"] = True

        logger.info("Starting web UI on http://%s:%s (desktop window)", args.host, args.port)

        # Start Flask in a daemon thread so it stops when the window is closed.
        threading.Thread(
            target=lambda: app.run(
                host=args.host, port=args.port, threaded=True, use_reloader=False
            ),
            daemon=True,
        ).start()

        _wait_for_server(args.host, args.port)

        webview.create_window(
            "Portfolio and Stock Monitor",
            f"http://{args.host}:{args.port}",
            width=1200,
            height=800,
            text_select=True,
        )
        webview.start()


if __name__ == "__main__":
    main()
