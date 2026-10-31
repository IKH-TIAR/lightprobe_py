"""Pages and startup."""

from __future__ import annotations

import logging
import sys

from nicegui import app, ui

from . import config
from .ui import dashboard, universe


def register_pages() -> None:
    @ui.page("/")
    def index_page() -> None:
        dashboard.build()

    @ui.page("/universe/{name}")
    def universe_page(name: str) -> None:
        universe.build(name)


def main(native: bool = True, port: int = 8765, open_window: bool = True) -> None:
    if sys.stdout is None or sys.stderr is None:
        # Started without a console (pythonw / "Start Light Probe.bat"): write the log to a file instead
        log_file = open(config.APP_ROOT / "lightprobe.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - kept open for the app's lifetime
        sys.stdout = sys.stdout or log_file
        sys.stderr = sys.stderr or log_file
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    register_pages()
    app.native.window_args["min_size"] = (1100, 720)
    ui.run(
        title="Light Probe",
        native=native,
        window_size=(1500, 950) if native else None,
        host="127.0.0.1",          # local only: never reachable from other computers
        port=port,
        dark=True,
        reload=False,
        show=open_window and not native,
        show_welcome_message=False,
        favicon="✨",
    )
