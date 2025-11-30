import logging
import sys
import os
from logging.handlers import RotatingFileHandler, SMTPHandler
import json as _json

def setup_logger(name: str) -> logging.Logger:
    """
    Configures a production-grade logger with console output, file rotation,
    and placeholders for critical email alerts.
    
    Args:
        name (str): The name of the module calling the logger (usually __name__).
    
    Returns:
        logging.Logger: Configured logger instance.
    """
    # 1. Define Log Directory
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    # 2. Basic Configuration
    logger = logging.getLogger(name)
    # Log level configurable via env
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))

    # Prevent duplicate logs if function is called multiple times
    if logger.hasHandlers():
        return logger

    # 3. Formatter
    # Detailed format: Time - Level - Module - Message
    log_format = os.getenv("LOG_FORMAT", "plain").lower()

    if log_format == "json":
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                payload = {
                    "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                    "level": record.levelname,
                    "logger": record.name,
                    "func": record.funcName,
                    "message": record.getMessage(),
                }
                return _json.dumps(payload)
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(message)s'
        )

    # 4. Console Handler (Standard Output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO) # Console sees INFO and up
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 5. File Handler (Rotating)
    # Keeps 5 files of 5MB each. Good for debugging history.
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG) # File sees DEBUG (everything)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 6. CRITICAL ALERT HANDLER (Email Stub)
    # =========================================================================
    # PRODUCTION NOTE: To enable, uncomment and set env vars.
    # This sends an email whenever logger.critical() is called.
    # =========================================================================
    """
    if os.getenv('EMAIL_HOST'):
        mail_handler = SMTPHandler(
            mailhost=(os.getenv('EMAIL_HOST'), 587),
            fromaddr=os.getenv('EMAIL_FROM'),
            toaddrs=[os.getenv('EMAIL_ADMIN')],
            subject="CRITICAL: Scraper Failure",
            credentials=(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS')),
            secure=()
        )
        mail_handler.setLevel(logging.CRITICAL)
        mail_handler.setFormatter(formatter)
        logger.addHandler(mail_handler)
    """
    
    return logger
