# Async Job Queue

## Overview

All current validation endpoints (`POST /validate`, `/g-eval`, `/rubric-eval`) block the HTTP connection until every gate finishes. For slow LLM-based validators (G-Eval, Gabriel, remote validators) this can take tens of seconds and gives the client no progress visibility.

The async job pattern fixes this: the client submits a validation request and gets a `job_id` back immediately. It then polls a status endpoint until the job is `completed` or `failed`.

**Redis is optional.** When `CHECKR_REDIS_URL` is not set, the `/jobs/validate` endpoints fall back to the existing inline sync behaviour and return results directly — no `job_id`, no polling needed. This means checkr works out of the box without any additional infrastructure.

---

## API Design

### Submit

```
POST /api/v0/jobs/validate
POST /api/v0/jobs/validate/{source}
```

Request body is identical to the existing `/validate` endpoints (`DatasetValidationRequest` / `DatasetGroupValidationRequest`).

**Async mode** (Redis configured) — returns immediately:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2026-05-25T10:00:00Z",
  "dataset_size": 1000,
  "gates": ["gate7_automatic_quality_grading/geval_rubric_validator"],
  "result_url": "/api/v0/jobs/550e8400-e29b-41d4-a716-446655440000"
}
```

**Sync mode** (no Redis) — blocks and returns the validation result directly:
```json
{
  "status": "ok",
  "validated_gates": ["gate7_automatic_quality_grading/geval_rubric_validator"],
  "errors": [],
  "info": [...]
}
```

### Poll

```
GET /api/v0/jobs/{job_id}
```

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "progress": { "current": 420, "total": 1000 },
  "created_at": "2026-05-25T10:00:00Z",
  "started_at": "2026-05-25T10:00:01Z",
  "completed_at": null,
  "result": null,
  "error": null
}
```

`status` values: `queued` → `running` → `completed` | `failed`

When `completed`, `result` contains the same payload the sync endpoint would have returned.

---

## Storage — Redis

| Key | Type | Value | TTL |
|-----|------|-------|-----|
| `checkr:jobs:{job_id}` | String (JSON) | `JobRecord` | 24 h |
| `checkr:queue` | List | JSON-encoded job payload | — |

Worker uses `BLPOP checkr:queue` (blocking pop) so it sleeps when the queue is empty.

---

## Mode Detection

```
CHECKR_REDIS_URL not set  →  sync mode (default)
CHECKR_REDIS_URL=redis://...  →  async mode
```

The Redis connection pool and background worker task are only created during app startup when `CHECKR_REDIS_URL` is set. No Redis = no extra dependencies at runtime.

---

## New Files

| File | Purpose |
|------|---------|
| `schemas/jobs.py` | `JobStatus` enum, `JobRecord` Pydantic model, `JobSubmissionResponse` |
| `services/job_service.py` | `create_job`, `get_job`, `update_job`, `enqueue_job` — thin interface over Redis (or in-memory fallback) |
| `services/job_worker.py` | `async def worker_loop()` — BLPOP queue, run `_validate()`, write result back |
| `api/jobs.py` | `POST /jobs/validate[/{source}]`, `GET /jobs/{job_id}` |

---

## Modified Files

| File | Change |
|------|--------|
| `core/config.py` | Add `redis_url: str \| None = None`, `job_ttl: int = 86400`, `job_queue_key`, `job_key_prefix` (env prefix `CHECKR_`) |
| `core/app.py` | Mount `api/jobs` router; init Redis pool + `asyncio.create_task(worker_loop())` in lifespan when `redis_url` is set |
| `pyproject.toml` | Add `redis>=5.0` (async client is built-in since v5) |

---

## Implementation Steps

1. Add `redis>=5.0` to `pyproject.toml`
2. Add Redis config fields to `core/config.py`
3. Create `schemas/jobs.py`
   - `JobStatus(str, Enum)`: `queued`, `running`, `completed`, `failed`
   - `JobRecord(BaseModel)`: `job_id`, `status`, `gates`, `dataset_size`, `progress`, `created_at`, `started_at`, `completed_at`, `result`, `error`
   - `JobSubmissionResponse(BaseModel)`: `job_id`, `status`, `created_at`, `dataset_size`, `gates`, `result_url`
4. Create `services/job_service.py`
   - Interface: `async create_job(...)`, `async get_job(job_id)`, `async update_job(job_id, **fields)`, `async enqueue_job(job_id)`
   - Uses `redis.asyncio.from_url(settings.redis_url)` connection pool stored on `app.state`
5. Create `services/job_worker.py`
   - `async def worker_loop(app)`: loop forever, `BLPOP checkr:queue`, deserialise, run `_validate()`, update job record
   - Progress updates: wrap validator's `progress_callback` to call `update_job(job_id, progress=...)`
6. Create `api/jobs.py`
   - `POST /jobs/validate[/{source}]`: if `settings.redis_url` → create+enqueue job, return `JobSubmissionResponse`; else → inline `_validate()`, return result directly
   - `GET /jobs/{job_id}`: `get_job(job_id)`, 404 if missing
7. Update `core/app.py`
   - Mount jobs router at `/api/v0`
   - In lifespan: if `redis_url` set → `app.state.redis = await redis.asyncio.from_url(...)`, `asyncio.create_task(worker_loop(app))`
   - On shutdown: cancel worker task, close Redis pool

---

## Client Usage

### Python (httpx)

```python
import httpx, time

base = "http://localhost:5000/api/v0"
dataset = [...]  # list of message dicts

# Submit
r = httpx.post(f"{base}/jobs/validate", json={"dataset": dataset, "gates": ["gate7_..."]})
body = r.json()

# Sync fallback (no Redis) — result is already here
if "job_id" not in body:
    print(body)
else:
    # Async mode — poll
    job_id = body["job_id"]
    while True:
        r = httpx.get(f"{base}/jobs/{job_id}")
        job = r.json()
        print(f"status={job['status']} progress={job.get('progress')}")
        if job["status"] in ("completed", "failed"):
            print(job["result"] or job["error"])
            break
        time.sleep(2)
```

### curl

```bash
# Submit
curl -s -X POST http://localhost:5000/api/v0/jobs/validate \
  -H "Content-Type: application/json" \
  -d '{"dataset": [...], "gates": ["gate7_.../geval_rubric_validator"]}' | jq .

# Poll
curl -s http://localhost:5000/api/v0/jobs/<job_id> | jq .
```

---

## Verification

```bash
# Unit tests — existing suite must stay green
uv run pytest tests/

# Manual async flow (requires Redis running)
CHECKR_REDIS_URL=redis://localhost:6379 uv run python entrypoint.py &
curl -s -X POST http://localhost:5000/api/v0/jobs/validate \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_dataset.json | jq .job_id

# Inspect Redis
redis-cli KEYS "checkr:jobs:*"
redis-cli GET "checkr:jobs:<job_id>"

# Manual sync flow (no Redis, should work identically to /validate)
uv run python entrypoint.py &
curl -s -X POST http://localhost:5000/api/v0/jobs/validate \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_dataset.json | jq .status
```

---

## Notes

- Existing sync endpoints (`/validate`, `/g-eval`, `/rubric-eval`) are **not changed** — async support is purely additive.
- The worker runs as an `asyncio` background task in the same process, so no separate worker container is needed initially. If throughput demands it, the `job_service.py` interface is designed to be storage-agnostic — swapping the backing store (or moving to a separate worker process) won't touch the API layer.
- Only backend validators go through the queue. Frontend (Pyodide) validators run in-browser and are unaffected.
- `BaseValidator.report_progress(current, total)` already exists — the worker will wire it to `update_job(job_id, progress={"current": ..., "total": ...})`.
