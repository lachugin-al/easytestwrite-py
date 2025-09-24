import structlog


def setup_logging() -> None:
    """
    Configure structured logging with structlog.

    Sets up:
    - Log level injection (adds "level" field to each log entry).
    - ISO-formatted timestamps.
    - JSON rendering for machine-readable logs (useful for CI/CD, log aggregators).
    """
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,  # Include log level in output
            structlog.processors.TimeStamper(fmt="iso"),  # Add timestamp in ISO 8601 format
            structlog.processors.JSONRenderer(),  # Render logs as JSON
        ]
    )
