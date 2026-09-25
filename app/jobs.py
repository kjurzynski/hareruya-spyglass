from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .hareruya import CardResult, run_cards


@dataclass
class Job:
    job_id: str
    cards: list[str]
    finish: str
    output: str
    status: str = "queued"
    completed: int = 0
    results: list[CardResult] = field(default_factory=list)
    error: str | None = None


class JobManager:
    def __init__(self, max_jobs: int = 2):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_jobs)

    def create(self, cards: list[str], finish: str, output: str) -> Job:
        job = Job(str(uuid.uuid4()), cards, finish, output)
        with self._lock:
            self._jobs[job.job_id] = job
        self._executor.submit(self._run, job.job_id)
        return job

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"

        def progress(completed: int, _total: int) -> None:
            with self._lock:
                job.completed = completed

        try:
            results = run_cards(job.cards, job.finish, progress=progress)
            with self._lock:
                job.results = results
                job.completed = len(job.cards)
                job.status = "complete"
        except Exception as exc:
            with self._lock:
                job.status = "error"
                job.error = str(exc)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            # Return a shallow snapshot so API serialization isn't racing mutation.
            return Job(
                job_id=job.job_id,
                cards=list(job.cards),
                finish=job.finish,
                output=job.output,
                status=job.status,
                completed=job.completed,
                results=list(job.results),
                error=job.error,
            )
