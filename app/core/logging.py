import logging
import json
import sys
from datetime import datetime, timezone
from app.core.config import settings


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "filename": record.filename,
            "line_number": record.lineno,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Merge extra fields if present
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict): # type: ignore
            log_data.update(record.extra_fields)
            
        return json.dumps(log_data)


def setup_logging():
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    handler = logging.StreamHandler(sys.stdout)
    if settings.is_development:
        # Standard human-readable format for dev
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(module)s (%(filename)s:%(lineno)d): %(message)s"
        )
    else:
        # JSON formatter for production
        formatter = JSONFormatter()
        
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Configure uvicorn loggers too
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).handlers = [handler]
        logging.getLogger(logger_name).setLevel(log_level)
