from core.config import settings
import logging
import structlog

_configured = False

def setup_logging():
    """Configures logging for the entire application. Safe to call multiple times."""
    global _configured
    if _configured:
        return structlog.get_logger()

    # 1. Standard logging configuration
    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",  # Structlog will handle formatting
        handlers=[logging.StreamHandler()]  # Add more handlers if needed
    )

    # 2. Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),  # Add timestamp
            structlog.processors.add_log_level,  # Include log level
            structlog.stdlib.add_logger_name,  # Include logger name
            structlog.processors.StackInfoRenderer(),  # Adds stack info on errors
            structlog.processors.format_exc_info,  # Adds exception trace
            structlog.processors.JSONRenderer(),  # Output logs in JSON format
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 3. Optional: Reduce noisy logs from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _configured = True
    return structlog.get_logger()
