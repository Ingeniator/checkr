import structlog
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time

logger = structlog.get_logger()

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """Middleware to log detailed request and response information"""
        # Bind request_id to structlog context so every log line includes it
        request_id = request.headers.get("x-request-id", "")
        structlog.contextvars.clear_contextvars()
        if request_id:
            structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.time()
        is_debug = logging.getLogger().isEnabledFor(logging.DEBUG)

        # Logging request details
        log_data = {
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
        }

        if is_debug:
            body = await request.body()
            body_str = body.decode("utf-8") if body else None
            if body_str:
                log_data["body"] = body_str
            log_data["headers"] = dict(request.headers)

        logger.debug("Incoming Request", **log_data)

        # Process the request
        response = await call_next(request)

        process_time = time.time() - start_time
        logger.debug("Response", status_code=response.status_code, process_time=f"{process_time:.4f}s")

        return response
