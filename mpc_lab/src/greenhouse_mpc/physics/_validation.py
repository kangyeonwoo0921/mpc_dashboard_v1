"""Input checks shared by the equation functions.

A missing (None) field-specific value raises ``MissingParameterError``: the equation is not
evaluated with a substitute. Out-of-domain values raise ``PhysicsInputError``. No clipping.
"""

import math


class MissingParameterError(ValueError):
    """A required parameter/input is None (field_required / calibration_required / TBD)."""


class PhysicsInputError(ValueError):
    """A value is present but outside the domain where the source equation is defined."""


def number(name, value):
    if value is None:
        raise MissingParameterError(f"{name} is required (value is None)")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PhysicsInputError(f"{name}: finite number required, got {value!r}")
    return float(value)


def non_negative(name, value):
    value = number(name, value)
    if value < 0:
        raise PhysicsInputError(f"{name}: must be >= 0, got {value}")
    return value


def positive(name, value):
    value = number(name, value)
    if value <= 0:
        raise PhysicsInputError(f"{name}: must be > 0, got {value}")
    return value


def fraction(name, value):
    value = number(name, value)
    if not 0.0 <= value <= 1.0:
        raise PhysicsInputError(f"{name}: must be in [0, 1], got {value}")
    return value


def celsius(name, value):
    """Temperature in degC; must be above absolute zero."""
    value = number(name, value)
    if value <= -273.15:
        raise PhysicsInputError(f"{name}: {value} degC is not above absolute zero")
    return value
