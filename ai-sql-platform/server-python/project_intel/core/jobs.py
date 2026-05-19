from __future__ import annotations

"""
Lightweight in-memory job store for background tasks.

Designed for single-process deployments (FastAPI + uvicorn).
If you scale to multiple workers, replace this with a Redis-backed store
or a proper task queue (Celery / Dramatiq).

Jobs are automatically evicted after JOB_TTL_SECONDS (default: 1 hour).
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


JOB_TTL_SECONDS = 3600


@dataclass
class Job:
    job_id: str
    status: str          # queued | running | done | failed
    label: str = ""      # human-readable description, e.g. "rag_rebuild"
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, label: str = "") -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = Job(job_id=job_id, status="queued", label=label)
            self._evict_locked()
        return job_id

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            self._patch(job_id, status="running")

    def mark_done(self, job_id: str, result: dict) -> None:
        with self._lock:
            self._patch(job_id, status="done", result=result)

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            self._patch(job_id, status="failed", error=error)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _patch(self, job_id: str, **kwargs: Any) -> None:
        j = self._jobs.get(job_id)
        if j is None:
            return
        for k, v in kwargs.items():
            setattr(j, k, v)
        j.updated_at = time.time()

    def _evict_locked(self) -> None:
        cutoff = time.time() - JOB_TTL_SECONDS
        self._jobs = {k: v for k, v in self._jobs.items() if v.created_at >= cutoff}


job_store = JobStore()
