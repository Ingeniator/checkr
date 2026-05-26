from __future__ import annotations

import asyncio
import json
import structlog
from datetime import datetime, timezone

from core.config import settings

logger = structlog.get_logger().bind(module=__name__)


def _make_progress_callback(
    service,
    job_id: str,
    loop: asyncio.AbstractEventLoop,
):
    """
    Returns a *sync* callable suitable for BaseValidator.progress_callback.

    BaseValidator.report_progress() may be called from a thread (CPU-bound
    validators run inside asyncio.to_thread), so we use
    run_coroutine_threadsafe to safely schedule the Redis update back on the
    event loop.
    """
    def _cb(info: dict) -> None:
        current = info.get("current")
        total = info.get("total")
        if current is not None and total is not None:
            asyncio.run_coroutine_threadsafe(
                service.update_job(job_id, progress={"current": current, "total": total}),
                loop,
            )

    return _cb


async def worker_loop(app) -> None:
    """
    Pulls jobs from the Redis queue (BLPOP) and runs validation.
    Runs as an asyncio background task; cancelled cleanly on shutdown.
    """
    from services.job_service import JobService
    from schemas.jobs import JobStatus

    redis = app.state.redis
    service = JobService(redis)
    validators_dict = app.state.backend_validators_dict
    loop = asyncio.get_event_loop()

    logger.info("Job worker started")

    while True:
        job_id: str | None = None
        try:
            # Block up to 5 s so CancelledError can be raised between polls
            result = await redis.blpop(settings.job_queue_key, timeout=5)
            if result is None:
                continue

            _, payload_str = result
            payload = json.loads(payload_str)
            job_id = payload["job_id"]
            dataset = payload["dataset"]
            options = payload.get("options", {})

            job = await service.get_job(job_id)
            if job is None:
                logger.warning("Job not found in store, skipping", job_id=job_id)
                continue

            logger.info("Processing job", job_id=job_id, gates=job.gates)
            await service.update_job(
                job_id,
                status=JobStatus.running,
                started_at=datetime.now(timezone.utc),
            )

            progress_cb = _make_progress_callback(service, job_id, loop)

            async def _run_gate(gate: str):
                validator = validators_dict[gate](options, progress_callback=progress_cb)
                return gate, await validator.validate(dataset)

            gate_results = await asyncio.gather(
                *(_run_gate(g) for g in job.gates),
                return_exceptions=True,
            )

            all_errors: list = []
            all_info: list = []
            for item in gate_results:
                if isinstance(item, Exception):
                    logger.error("Gate error", error=str(item), job_id=job_id)
                    all_errors.append({"error": str(item), "code": "worker_error"})
                    continue
                _, res = item
                if res.get("status") == "failed":
                    all_errors.extend(res.get("errors", []))
                if "info" in res:
                    all_info.extend(res["info"])

            final_result: dict = {
                "status": "ok" if not all_errors else "failed",
                "validated_gates": job.gates,
                "errors": all_errors,
            }
            if all_info:
                final_result["info"] = all_info

            await service.update_job(
                job_id,
                status=JobStatus.completed,
                completed_at=datetime.now(timezone.utc),
                result=final_result,
            )
            logger.info(
                "Job completed",
                job_id=job_id,
                status=final_result["status"],
                errors=len(all_errors),
            )

        except asyncio.CancelledError:
            logger.info("Job worker shutting down")
            break
        except Exception as exc:
            logger.error("Worker unhandled error", error=str(exc), job_id=job_id)
            if job_id:
                try:
                    from schemas.jobs import JobStatus as _JS
                    await service.update_job(
                        job_id,
                        status=_JS.failed,
                        completed_at=datetime.now(timezone.utc),
                        error=str(exc),
                    )
                except Exception:
                    pass
