from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import time

# Request count metric
REQUEST_COUNT = Counter(
    "http_requests_total", "Total number of HTTP requests",
    ["method", "endpoint", "status_code"]
)

# Request duration metric
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "Histogram of request processing time",
    ["method", "endpoint"]
)

# Business metrics: validation pass/fail tracking
VALIDATION_RESULTS = Counter(
    "checkr_validation_results_total",
    "Total validation results by gate and outcome",
    ["gate", "status"]
)

VALIDATION_ITEMS = Counter(
    "checkr_validation_items_total",
    "Total dataset items validated",
    ["gate"]
)

VALIDATION_ERRORS = Counter(
    "checkr_validation_errors_total",
    "Total validation errors by gate and error code",
    ["gate", "code"]
)

VALIDATION_DURATION = Histogram(
    "checkr_validation_duration_seconds",
    "Validation execution time per gate",
    ["gate"]
)

# Middleware for collecting metrics
class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path

        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=response.status_code).inc()
        REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

        return response

# Metrics endpoint handler
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
