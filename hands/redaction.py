import re
from typing import Any


_SENSITIVE_KEYS = re.compile(r"password|secret|token|ssn|account_number|routing_number", re.I)
_SSN = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
_LONG_NUMBER = re.compile(r"\b\d{9,19}\b")


def redact(value: Any, key: str = "") -> Any:
    if _SENSITIVE_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = _SSN.sub("[REDACTED-SSN]", value)
        return _LONG_NUMBER.sub(lambda m: "*" * (len(m.group()) - 4) + m.group()[-4:], value)
    return value

