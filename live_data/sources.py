"""Local-only LIVE data sources for Phase 1.7.

This module contains no network client.  Phase 1.8 can add a read-only source
behind ``load_raw_snapshot`` while preserving the adapter and frontend DTO.
"""

from __future__ import annotations

import copy
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import psychrometrics
from .adapter import apply_growlink_mock_overrides, normalize_growlink_live


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "growlink_live_sample.json"
SUPPORTED_SOURCES = frozenset({"mock_static", "mock_dynamic"})
SEOUL = ZoneInfo("Asia/Seoul")


def load_mock_raw() -> dict[str, Any]:
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _wave(seconds: float, minimum: float, maximum: float, period: float, phase: float = 0.0) -> float:
    midpoint = (minimum + maximum) / 2.0
    amplitude = (maximum - minimum) / 2.0
    return midpoint + amplitude * math.sin((seconds / period) * math.tau + phase)


def build_dynamic_raw(now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(tz=SEOUL)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SEOUL)
    seconds = current.timestamp()
    raw = copy.deepcopy(load_mock_raw())
    temperature_c = round(_wave(seconds, 27.0, 31.0, 120.0), 2)
    rh_pct = round(_wave(seconds, 65.0, 80.0, 150.0, 0.7), 2)
    dew_point = psychrometrics.dew_point_c(temperature_c, rh_pct)
    return apply_growlink_mock_overrides(
        raw,
        environment={
            "indoor_temperature_c": temperature_c,
            "indoor_rh_pct": rh_pct,
            "vpd_kpa": round(psychrometrics.vpd_kpa(temperature_c, rh_pct), 3),
            "dew_point_c": None if dew_point is None else round(dew_point, 1),
            "solar_w_m2": round(_wave(seconds, 150.0, 650.0, 180.0, 1.2), 1),
        },
        actuators={
            "roof_vent_left_pct": round(_wave(seconds, 10.0, 80.0, 50.0), 2),
            "roof_vent_right_pct": round(_wave(seconds, 10.0, 80.0, 50.0, 1.1), 2),
            "shade_screen_1_pct": round(_wave(seconds, 0.0, 100.0, 70.0, 0.4), 2),
            "shade_screen_2_pct": round(_wave(seconds, 0.0, 100.0, 90.0, 1.6), 2),
        },
    )


def load_raw_snapshot(source: str, now: datetime | None = None) -> dict[str, Any]:
    """Return raw source data without performing any network request."""

    if source == "mock_static":
        return load_mock_raw()
    if source == "mock_dynamic":
        return build_dynamic_raw(now)
    raise ValueError(f"Unsupported LIVE_DATA_SOURCE {source!r}; expected mock_static or mock_dynamic")


def get_live_snapshot(
    source: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    selected = source or os.environ.get("LIVE_DATA_SOURCE", "mock_dynamic")
    current = now or datetime.now(tz=SEOUL)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SEOUL)
    raw = load_raw_snapshot(selected, current)
    return normalize_growlink_live(raw, timestamp=current, source=selected)
