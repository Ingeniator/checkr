
# core/app.py
from fastapi import FastAPI, Depends, Request
from contextlib import asynccontextmanager
from core.config import settings
from core.logging_config import setup_logging
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.metrics_middleware import PrometheusMiddleware, metrics

from api.validators import router as validator_router, init_validators

logger = setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Application startup...")
    init_validators(app)
    
    yield  # ← This is where the app runs

    # Shutdown logic (optional)
    logger.info("Application shutdown...")
    # e.g., await app.state.backend_validators.cleanup() if needed

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title=settings.app_name, docs_url="/docs", debug=settings.debug, lifespan=lifespan)
    app.include_router(validator_router, prefix="/api/v1")
    # Add Logging Middleware
    app.add_middleware(LoggingMiddleware)
    # Add Prometheus middleware
    app.add_middleware(PrometheusMiddleware)

    # Expose metrics endpoint
    @app.get("/metrics")
    async def get_metrics():
        return await metrics()

    @app.get("/health")
    async def health_check():
        """Check the health of the service and its components."""

        return {
            "status": "ok",
            "version": settings.version
        }

    return app