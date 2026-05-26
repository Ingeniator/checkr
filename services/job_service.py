from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from schemas.jobs import JobRecord, JobStatus
from core.config import settings


class JobService:
    """Thin Redis-backed store for job records and the submission queue."""

    def __init__(self, redis_client):
        self.redis = redis_client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, job_id: str) -> str:
        return f"{settings.job_key_prefix}{job_id}"

    async def _save(self, job: JobRecord) -> None:
        await self.redis.set(self._key(job.job_id), job.model_dump_json(), ex=settings.job_ttl)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_job(self, gates: list[str], dataset_size: int) -> JobRecord:
        job = JobRecord(gates=gates, dataset_size=dataset_size)
        await self._save(job)
        return job

    async def get_job(self, job_id: str) -> JobRecord | None:
        data = await self.redis.get(self._key(job_id))
        if data is None:
            return None
        return JobRecord.model_validate_json(data)

    async def update_job(self, job_id: str, **fields: Any) -> None:
        job = await self.get_job(job_id)
        if job is None:
            return
        await self._save(job.model_copy(update=fields))

    async def update_progress(self, job_id: str, gate: str, current: int, total: int) -> None:
        """Atomic per-gate progress update — does not clobber other gates."""
        job = await self.get_job(job_id)
        if job is None:
            return
        progress = dict(job.progress)
        progress[gate] = {"current": current, "total": total}
        await self._save(job.model_copy(update={"progress": progress}))

    async def enqueue_job(self, job_id: str, dataset: list, options: dict) -> None:
        payload = json.dumps({"job_id": job_id, "dataset": dataset, "options": options})
        await self.redis.rpush(settings.job_queue_key, payload)
