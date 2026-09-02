import json
import logging
import queue
from datetime import UTC, datetime
from logging.handlers import QueueHandler, QueueListener

_listener: QueueListener | None = None

SENSITIVE_THIRD_PARTY_LOGGERS = (
    "httpcore",
    "httpx",
    "httpx2",
    "openai",
)
NOISY_THIRD_PARTY_LOGGERS = (
    "asyncio",
    "celery",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("request_id", "method", "path", "status_code", "duration_ms"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(environment: str) -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    log_queue: queue.SimpleQueue = queue.SimpleQueue()
    _listener = QueueListener(log_queue, handler, respect_handler_level=True)
    _listener.start()
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(QueueHandler(log_queue))
    root.setLevel(logging.DEBUG if environment == "development" else logging.INFO)
    for logger_name in SENSITIVE_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    for logger_name in NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.INFO)
