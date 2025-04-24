
from fastapi import FastAPI, Depends, Request
from core.config import settings
from core.logging_config import setup_logging
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.metrics_middleware import PrometheusMiddleware, metrics

from api.validators import router as validator_router

logger = setup_logging()

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title=settings.app_name, docs_url="/docs", debug=settings.debug)
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

    @app.on_event("startup")
    async def startup_event():
        logger.info("Application startup...")

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Application shutdown...")

    return app