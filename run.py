"""Start Light Probe.

    python run.py            opens the app in its own desktop window
    python run.py --browser  opens it in the web browser instead (still local only)

Starting it again while it is already open closes the running copy first and starts a fresh one.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PID_FILE = Path(__file__).resolve().parent / "lightprobe.pid"


def _running_pid() -> int | None:
    """The process id of a Light Probe that is still running, if any."""
    try:
        pid = int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid():
        return None
    if sys.platform.startswith("win"):
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.lower()
        return pid if "python" in out else None   # a reused id belonging to another program is left alone
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        return None


def stop_previous() -> None:
    pid = _running_pid()
    if not pid:
        return
    print(f"Light Probe is already running (process {pid}) - closing it to start again...", flush=True)
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        import signal
        os.kill(pid, signal.SIGTERM)
    time.sleep(1.5)  # let the window close and the port free up


if __name__ in {"__main__", "__mp_main__"}:
    parser = argparse.ArgumentParser(description="Light Probe - local novel engine")
    parser.add_argument("--browser", action="store_true", help="open in the web browser instead of a desktop window")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--headless", action="store_true", help="start the local server without opening a window (for testing)")
    parser.add_argument("--stop", action="store_true", help="close a running Light Probe and exit")
    args = parser.parse_args()
    if args.stop:
        stop_previous()
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)
    if __name__ == "__main__":   # the window helper process started by the app must not restart it
        stop_previous()
        PID_FILE.write_text(str(os.getpid()))
    from lightprobe.app import main
    main(native=not (args.browser or args.headless), port=args.port, open_window=not args.headless)
