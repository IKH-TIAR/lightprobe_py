"""Background jobs. Model calls are slow, so every step that calls the model runs in a background
thread while the window stays responsive. One job per universe at a time. A job saves its results to
the universe folder as it goes, so closing the window never loses finished work.

A stop request takes effect at the next progress point (the call in flight finishes first)."""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Callable

from . import llm, storage

log = logging.getLogger("lightprobe.jobs")


class JobStopped(Exception):
    pass


@dataclass
class Job:
    id: str
    universe: str
    action: str
    label: str
    status: str = "running"          # running | done | error | stopped
    message: str = "Starting..."
    percentage: int = 0
    logs: list[tuple[str, str]] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    finished: float | None = None
    error: str | None = None
    stop_requested: bool = False

    @property
    def elapsed(self) -> int:
        return int((self.finished or time.time()) - self.started)


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def current(universe: str) -> Job | None:
    return _jobs.get(universe)


def running(universe: str) -> bool:
    job = _jobs.get(universe)
    return bool(job and job.status == "running")


def clear(universe: str) -> None:
    with _lock:
        job = _jobs.get(universe)
        if job and job.status != "running":
            del _jobs[universe]


def request_stop(universe: str) -> None:
    job = _jobs.get(universe)
    if job and job.status == "running":
        job.stop_requested = True
        job.message = "Stopping after the current step..."


def start(universe: str, action: str, label: str, fn: Callable[[str, dict, Callable], object]) -> Job:
    """Runs fn(universe, state, progress) in a background thread. The state is re-read from disk so the
    job always starts from what is saved."""
    with _lock:
        if running(universe):
            raise RuntimeError(f"Another step is already running for this universe ({_jobs[universe].label}).")
        job = Job(id=uuid.uuid4().hex[:8], universe=universe, action=action, label=label)
        _jobs[universe] = job

    def progress(message: str, percentage: int | None = None, **extra) -> None:
        if job.stop_requested:
            raise JobStopped()
        job.message = message
        if percentage is not None:
            job.percentage = max(0, min(100, int(percentage)))
        job.logs.append((time.strftime("%H:%M:%S"), message))
        del job.logs[:-200]
        log.info("[%s] %s", universe, message)

    def target() -> None:
        token = llm.current_universe.set(universe)
        try:
            state = storage.load_state(universe)
            if state is None:
                raise ValueError(f"Universe {universe} not found.")
            fn(universe, state, progress)
            job.status = "done"
            job.percentage = 100
        except JobStopped:
            job.status = "stopped"
            job.message = "Stopped. Finished work is saved; run the step again to continue."
        except Exception as err:  # noqa: BLE001 - shown to the creators in the window
            log.error("Job %s failed: %s\n%s", label, err, traceback.format_exc())
            job.status = "error"
            job.error = str(err)
            job.message = f"{label} stopped: {err}"
        finally:
            job.finished = time.time()
            llm.current_universe.reset(token)

    threading.Thread(target=target, name=f"job-{universe}-{action}", daemon=True).start()
    return job
