"""Pop up the Portfolio and Stock Monitor as a desktop window (reminder).

Launched by the scheduled task runner after a successful data refresh.
Opens on top of all currently running applications. If the app is already
running, brings the existing window to the front and top.
"""

from __future__ import annotations

import logging
import socket
import sys
import threading
import time

from stockmon.logging_config import configure_logging
from stockmon.paths import APP_LOG_FILE, ensure_directories
from stockmon.web import create_app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000


def _port_in_use(host: str, port: int) -> bool:
    """Return *True* if something is already listening on *host*:*port*."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def _bring_existing_window_to_top() -> bool:
    """Find the existing Portfolio and Stock Monitor window and bring it to the top."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found_hwnd = None

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_proc(hwnd, lparam):
            nonlocal found_hwnd
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if (
                        "Portfolio and Stock Monitor" in buf.value
                        or "Portfolio EMA Monitor" in buf.value
                    ):
                        found_hwnd = hwnd
                        return False
            return True

        user32.EnumWindows(enum_proc, 0)
        if found_hwnd:
            # SW_RESTORE = 9, HWND_TOPMOST = -1, SWP_NOSIZE = 1, SWP_NOMOVE = 2, SWP_SHOWWINDOW = 0x40
            user32.ShowWindow(found_hwnd, 9)
            user32.SetWindowPos(found_hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            user32.SetForegroundWindow(found_hwnd)
            return True
    except Exception:
        pass
    return False


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
    if _port_in_use(DEFAULT_HOST, DEFAULT_PORT):
        # App is already running — bring the existing window on top of all applications
        _bring_existing_window_to_top()
        sys.exit(0)

    import webview  # lazy import so the dependency is only needed when showing a window

    webview.settings["ALLOW_DOWNLOADS"] = True

    ensure_directories()
    configure_logging(APP_LOG_FILE)
    logger = logging.getLogger("stockmon.show_window")
    logger.info("Opening reminder window on top after scheduled refresh")

    app = create_app()

    threading.Thread(
        target=lambda: app.run(
            host=DEFAULT_HOST, port=DEFAULT_PORT, threaded=True, use_reloader=False
        ),
        daemon=True,
    ).start()

    _wait_for_server(DEFAULT_HOST, DEFAULT_PORT)

    webview.create_window(
        "Portfolio and Stock Monitor — Updated",
        f"http://{DEFAULT_HOST}:{DEFAULT_PORT}",
        width=1200,
        height=800,
        on_top=True,
        text_select=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
