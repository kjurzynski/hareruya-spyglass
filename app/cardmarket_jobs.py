from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from .cardmarket_data import _atomic_write_json, download_and_merge, is_stale, read_status, STATUS_FILE


@dataclass
class CardmarketUpdateJob:
    job_id: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued."
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class CardmarketUpdateManager:
    def __init__(self) -> None:
        self._jobs: dict[str, CardmarketUpdateJob] = {}
        self._lock = threading.Lock()
        self._active_job_id: str | None = None

    def create(self, force: bool = False) -> CardmarketUpdateJob:
        with self._lock:
            if self._active_job_id:
                active = self._jobs.get(self._active_job_id)
                if active and active.status in {"queued", "running"}:
                    return CardmarketUpdateJob(**active.__dict__)
            if not force and not is_stale():
                job = CardmarketUpdateJob(
                    job_id=str(uuid.uuid4()),
                    status="complete",
                    progress=100.0,
                    message="Local Cardmarket data is already up to date.",
                    finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                )
                self._jobs[job.job_id] = job
                return CardmarketUpdateJob(**job.__dict__)

            job = CardmarketUpdateJob(job_id=str(uuid.uuid4()))
            self._jobs[job.job_id] = job
            self._active_job_id = job.job_id
        thread = threading.Thread(target=self._run, args=(job.job_id,), daemon=True)
        thread.start()
        return CardmarketUpdateJob(**job.__dict__)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        def progress(percent: float, message: str) -> None:
            with self._lock:
                current = self._jobs[job_id]
                current.progress = max(0.0, min(100.0, float(percent)))
                current.message = message

        try:
            download_and_merge(progress)
            with self._lock:
                current = self._jobs[job_id]
                current.status = "complete"
                current.progress = 100.0
                current.message = "Cardmarket data is ready locally."
                current.finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                self._active_job_id = None
        except Exception as exc:
            finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            with self._lock:
                current = self._jobs[job_id]
                current.status = "error"
                current.error = str(exc)
                current.message = "Cardmarket update failed. Existing merged local data was left untouched."
                current.finished_at = finished_at
                self._active_job_id = None
            existing = read_status()
            existing.update({
                "state": "error",
                "message": str(exc),
                "last_attempt_at": finished_at,
            })
            try:
                _atomic_write_json(STATUS_FILE, existing)
            except OSError:
                pass

    def get(self, job_id: str) -> CardmarketUpdateJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return CardmarketUpdateJob(**job.__dict__) if job else None

    def current(self) -> CardmarketUpdateJob | None:
        with self._lock:
            if self._active_job_id:
                job = self._jobs.get(self._active_job_id)
                if job:
                    return CardmarketUpdateJob(**job.__dict__)
            return None


try:
    APP_TIMEZONE = ZoneInfo("Europe/Warsaw")
except ZoneInfoNotFoundError:
    # Windows Python installations can lack the optional IANA tzdata package.
    # Fall back to the machine's local timezone so the app can still start and
    # the daily refresh remains scheduled for 04:00 local time.
    APP_TIMEZONE = datetime.now().astimezone().tzinfo


def _next_four_am(now: datetime) -> datetime:
    target = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def start_daily_scheduler(manager: CardmarketUpdateManager) -> threading.Thread:
    def loop() -> None:
        # Give FastAPI a moment to finish startup before doing network I/O.
        time.sleep(2)
        if manager.current() is None and is_stale():
            manager.create(force=False)

        while True:
            now = datetime.now(APP_TIMEZONE)
            target = _next_four_am(now)
            time.sleep(max(1.0, (target - now).total_seconds()))
            if manager.current() is None:
                manager.create(force=True)

    thread = threading.Thread(target=loop, daemon=True, name="cardmarket-daily-updater")
    thread.start()
    return thread


def status_payload(manager: CardmarketUpdateManager) -> dict[str, Any]:
    status = read_status()
    active = manager.current()
    if active:
        status.update(
            {
                "state": "updating",
                "job_id": active.job_id,
                "progress": active.progress,
                "message": active.message,
            }
        )
    else:
        status.setdefault("progress", 100.0 if status.get("state") == "ready" else 0.0)
        status["job_id"] = None
    return status
