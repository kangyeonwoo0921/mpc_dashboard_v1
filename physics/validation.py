"""Small, dependency-free validators. Null is missing, never numeric zero."""

import math
from datetime import datetime


class PhysicsValidationError(ValueError):
    """Invalid data, distinct from accepted missing/unverified data."""


def require(condition, path, value, expected):
    if not condition:
        raise PhysicsValidationError(f"{path}: invalid {value!r}; expected {expected}")


def number(value, path, lower=None, upper=None, *, nullable=True):
    if value is None and nullable:
        return
    require(type(value) in (int, float) and math.isfinite(value), path, value,
            "finite number" + (" or null" if nullable else ""))
    require((lower is None or value >= lower) and (upper is None or value <= upper),
            path, value, f"range [{lower}, {upper}]")


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
        valid = parsed is not None and parsed.utcoffset() is not None
    except ValueError:
        valid = False
    require(valid, "timestamp", value, "ISO 8601 timestamp with timezone offset")


def angle(value, path):
    number(value, path, 0, 360)
    require(value is None or value < 360, path, value, "0 <= degrees < 360")


def opening_to_deployment(opening_percent):
    number(opening_percent, "opening_percent", 0, 100)
    return None if opening_percent is None else 1 - opening_percent / 100
