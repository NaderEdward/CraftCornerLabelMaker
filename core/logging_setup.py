from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

LOGGER_NAME = "craftcorner"

_TOKEN_RE = re.compile(r"\b(shp(?:at|ca|pa|ss)_[A-Za-z0-9]{8,})\b")
_HEADER_RE = re.compile(r"(X-Shopify-Access-Token[\"']?\s*[:=]\s*)\S+", re.I)


class _RedactingFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = _TOKEN_RE.sub("<redacted-token>", msg)
        redacted = _HEADER_RE.sub(r"\1<redacted>", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure(run_dir: Optional[Path] = None, console_level: int = logging.INFO) -> logging.Logger:
    logger = get_logger()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    redactor = _RedactingFilter()

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in logger.handlers):
        console = logging.StreamHandler()
        console.setLevel(console_level)
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        console.addFilter(redactor)
        logger.addHandler(console)

    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()

    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(run_dir / "log.txt", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s %(message)s"
        ))
        file_handler.addFilter(redactor)
        logger.addHandler(file_handler)

    return logger
