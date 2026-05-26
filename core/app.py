
# core/app.py
import asyncio

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from contextlib import asynccontextmanager
from core.config import settings
from middlewares.logging_middleware import LoggingMiddleware
import structlog
from middlewares.metrics_middleware import PrometheusMiddleware, metrics

from api.validators import router as validator_router, init_validators
from api.jobs import router as jobs_router

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application startup...")
    await init_validators(app)

    # Async job queue — only when Redis is configured
    if settings.redis_url:
        import redis.asyncio as aioredis
        from services.job_worker import worker_loop

        logger.info("Connecting to Redis", url=settings.redis_url)
        app.state.redis = await aioredis.from_url(
            settings.redis_url, decode_responses=True
        )
        app.state.worker_task = asyncio.create_task(worker_loop(app))
        logger.info("Job worker task started")
    else:
        logger.info("No CHECKR_REDIS_URL — running in sync mode (no job queue)")

    yield  # ← app is running

    # Shutdown
    logger.info("Application shutdown...")
    if settings.redis_url:
        task: asyncio.Task = getattr(app.state, "worker_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        redis = getattr(app.state, "redis", None)
        if redis:
            await redis.aclose()
        logger.info("Redis connection closed")

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title=settings.app_name, root_path=settings.root_path, debug=settings.debug, lifespan=lifespan)
    app.include_router(validator_router, prefix="/api/v0")
    app.include_router(jobs_router, prefix="/api/v0/jobs")
    # Add Logging Middleware
    app.add_middleware(LoggingMiddleware)
    # Add Prometheus middleware
    app.add_middleware(PrometheusMiddleware)

    # Serve static files (e.g., CSS, JS, images) at /static
    app.mount("/static", StaticFiles(directory="static"), name="static")
    # Serve index.html as sync playground
    @app.get("/playground", include_in_schema=False)
    async def playground():
        return FileResponse(Path("static/index.html"))

    # Async playground (job queue / polling)
    @app.get("/async-playground", include_in_schema=False)
    async def async_playground():
        return FileResponse(Path("static/async-playground.html"))

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url=f"{settings.root_path}/playground", status_code=302)

    # Expose metrics endpoint
    @app.get("/metrics")
    async def get_metrics():
        return await metrics()

    @app.get("/livez")
    async def livez():
        """Liveness probe — process is alive, no dependency checks."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        """Readiness probe — returns 200 if LLM backend is reachable, 503 otherwise."""
        import asyncio
        import httpx
        from starlette.responses import Response as StarletteResponse

        from utils.yaml import load_and_expand_yaml

        try:
            llm_cfg = load_and_expand_yaml(settings.llm_config_path)
            api_base = llm_cfg.get("geval", {}).get("api_base", "")
            if api_base:
                models_url = f"{api_base}/models"
                async with httpx.AsyncClient(timeout=3, verify=settings.http_verify_ssl) as client:
                    resp = await asyncio.wait_for(
                        client.get(models_url),
                        timeout=5,
                    )
                    resp.raise_for_status()
        except Exception:
            return StarletteResponse(status_code=503)

        return StarletteResponse(status_code=200)

    @app.get("/health")
    async def health_check():
        """Full health status with component details — for dashboards and monitoring."""
        import asyncio
        import httpx

        from utils.yaml import load_and_expand_yaml

        components: dict[str, str] = {}
        details: dict[str, str] = {}

        # Probe the LLM backend (yallmp) used by G-Eval / GABRIEL validators
        try:
            llm_cfg = load_and_expand_yaml(settings.llm_config_path)
            api_base = llm_cfg.get("geval", {}).get("api_base", "")
            if api_base:
                # Hit yallmp's models endpoint as a lightweight probe
                models_url = f"{api_base}/models"
                async with httpx.AsyncClient(timeout=3, verify=settings.http_verify_ssl) as client:
                    resp = await asyncio.wait_for(
                        client.get(models_url),
                        timeout=5,
                    )
                    resp.raise_for_status()
                components["llm_backend"] = "ok"
            else:
                components["llm_backend"] = "disabled"
        except Exception as exc:
            components["llm_backend"] = "degraded"
            details["llm_backend"] = str(exc)

        enabled = {k: v for k, v in components.items() if v != "disabled"}
        status = "ok" if all(v == "ok" for v in enabled.values()) else "degraded"

        result: dict = {
            "status": status,
            "version": settings.version,
            "components": components,
        }
        if details:
            result["details"] = details
        return result

    return app
