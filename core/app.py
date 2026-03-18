
# core/app.py
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

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Application startup...")
    await init_validators(app)
    
    yield  # ← This is where the app runs

    # Shutdown logic (optional)
    logger.info("Application shutdown...")
    # e.g., await app.state.backend_validators.cleanup() if needed

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title=settings.app_name, root_path=settings.root_path, debug=settings.debug, lifespan=lifespan)
    app.include_router(validator_router, prefix="/api/v0")
    # Add Logging Middleware
    app.add_middleware(LoggingMiddleware)
    # Add Prometheus middleware
    app.add_middleware(PrometheusMiddleware)

    # Serve static files (e.g., CSS, JS, images) at /static
    app.mount("/static", StaticFiles(directory="static"), name="static")
    # Serve index.html as playground
    @app.get("/playground", include_in_schema=False)
    async def playground():
        return FileResponse(Path("static/index.html"))

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
