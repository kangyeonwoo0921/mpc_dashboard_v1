"""GHI forecast for the dashboard: reads the file written by mpc_lab's live runner.

``GHI_FORECAST_FILE`` points to ``mpc_lab/data/processed/forecast_live/latest_forecast.json``
(``python -m greenhouse_mpc.forecast.live_runner --loop`` in the mpc_lab environment). A missing,
unreadable or old file (``GHI_FORECAST_MAX_AGE_S``, default 600 s) gives ``status`` other than
``ok`` and ``horizons: null``; old forecasts are never shown as current ones.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "ghi-forecast/0.1"
MAX_AGE_S = 600.0
SEOUL = ZoneInfo("Asia/Seoul")


def _unavailable(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "status": status, "reason": reason, "issue_time": None,
            "generated_at": None, "horizons": None, **extra}


def load_ghi_forecast(path: str | Path | None, now: datetime, max_age_s: float = MAX_AGE_S) -> dict[str, Any]:
    if not path:
        return _unavailable("unavailable", "forecast_not_configured")
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(payload["generated_at"])
    except FileNotFoundError:
        return _unavailable("unavailable", "no_forecast_file")
    except (OSError, ValueError, KeyError, TypeError):
        return _unavailable("unavailable", "unreadable_forecast_file")
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=SEOUL)
    payload.pop("traceback", None)
    if (now - generated).total_seconds() > max_age_s:
        return {**payload, "status": "stale", "reason": "forecast_too_old", "horizons": None}
    return payload


def get_ghi_forecast(now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(tz=SEOUL)
    max_age = float(os.environ.get("GHI_FORECAST_MAX_AGE_S", MAX_AGE_S))
    return load_ghi_forecast(os.environ.get("GHI_FORECAST_FILE"), current, max_age)
