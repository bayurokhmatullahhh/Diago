"""Setup logging + filter sederhana agar secret tidak bocor ke log."""
import logging
import re
import sys

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)(\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"bot\d+:[A-Za-z0-9_-]{20,}"),  # token Telegram di URL
]


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        msg = _SECRET_PATTERNS[0].sub(r"\1\2***", msg)
        msg = _SECRET_PATTERNS[1].sub("bot***", msg)
        record.msg, record.args = msg, ()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    handler.addFilter(RedactSecretsFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
