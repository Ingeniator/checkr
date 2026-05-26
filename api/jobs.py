from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request

from api.validators import _validate, proxy_request_headers
from schemas.jobs import JobRecord, JobSubmissionResponse, JobStatus
from schemas.validators import DatasetGroupValidationRequest, DatasetValidationRequest

logger = structlog.get_logger().bind(module=__name__)

router = APIRouter()


def _redis(app) :
    """Return the Redis client stored on app.state, or None in sync mode."""
    return getattr(app.state, "redis", None)


async def _submit_or_run(
    gates: list[str],
    request: DatasetValidationRequest | DatasetGroupValidationRequest,
    request_: Request,
) -> Any:
    app = request_.app

    # Validate gates exist up-front (both sync and async modes)
    unknown = [g for g in gates if g not in app.state.backend_validators_dict]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown gates: {', '.join(unknown)}")

    redis = _redis(app)

    # ------------------------------------------------------------------
    # Sync mode — no Redis configured
    # ------------------------------------------------------------------
    if redis is None:
        logger.debug("Sync fallback (no Redis)", gates=gates)
        return await _validate(gates, request.dataset, request.options, request_)

    # ------------------------------------------------------------------
    # Async mode — enqueue and return job_id immediately
    # ------------------------------------------------------------------
    from services.job_service import JobService

    proxy_request_headers(request_)  # preserve tracing headers in context var

    dataset_raw = [
        item.model_dump() if hasattr(item, "model_dump") else item.dict()
        for item in (request.dataset or [])
    ]

    service = JobService(redis)
    job = await service.create_job(gates=gates, dataset_size=len(dataset_raw))
    await service.enqueue_job(job.job_id, dataset_raw, request.options)

    logger.info("Job queued", job_id=job.job_id, gates=gates, dataset_size=job.dataset_size)

    return JobSubmissionResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        dataset_size=job.dataset_size,
        gates=job.gates,
        result_url=f"/api/v0/jobs/{job.job_id}",
    )


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/validate/{source:path}")
async def jobs_validate_single(
    source: str,
    request: DatasetValidationRequest,
    request_: Request,
):
    """Submit a single-gate validation job (or run inline when Redis is absent)."""
    return await _submit_or_run([source], request, request_)


@router.post("/validate")
async def jobs_validate_multi(
    request: DatasetGroupValidationRequest,
    request_: Request,
):
    """Submit a multi-gate validation job (or run inline when Redis is absent)."""
    return await _submit_or_run(request.gates, request, request_)


@router.get("/{job_id}", response_model=JobRecord)
async def get_job_status(job_id: str, request_: Request):
    """Poll job status and retrieve the result when completed."""
    redis = _redis(request_.app)
    if redis is None:
        raise HTTPException(
            status_code=404,
            detail="Async job queue is not enabled (CHECKR_REDIS_URL not configured).",
        )
    from services.job_service import JobService
    job = await JobService(redis).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job
