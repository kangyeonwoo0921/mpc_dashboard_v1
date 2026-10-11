"""GET /api/forecast/ghi/: file written by mpc_lab's live runner; missing/old files never look current."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenhouse_web.settings")
import django  # noqa: E402

django.setup()
from django.test import Client  # noqa: E402

from live_data.forecast import load_ghi_forecast  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 11, 12, 7, tzinfo=KST)


def payload(generated):
    return {"schema_version": "ghi-forecast/0.1", "generated_at": generated.isoformat(), "status": "ok",
            "reason": None, "issue_time": "2026-10-11T12:00:00+09:00", "traceback": "x",
            "horizons": [{"h_steps": 1, "horizon_min": 5, "target_time": "2026-10-11T12:05:00+09:00",
                          "method": "xgb_expanding", "ghi_w_m2": 512.3, "kc": 0.71, "ghi_clear_w_m2": 721.6}]}


class GhiForecastTests(unittest.TestCase):
    def write(self, tmp, data):
        path = Path(tmp) / "latest_forecast.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_fresh_forecast_passes_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = load_ghi_forecast(self.write(tmp, payload(NOW)), NOW + timedelta(minutes=2))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["horizons"][0]["ghi_w_m2"], 512.3)
        self.assertNotIn("traceback", result)

    def test_old_missing_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = load_ghi_forecast(self.write(tmp, payload(NOW)), NOW + timedelta(minutes=30))
            broken = Path(tmp) / "broken.json"
            broken.write_text("{", encoding="utf-8")
            self.assertEqual((old["status"], old["horizons"]), ("stale", None))
            self.assertEqual(load_ghi_forecast(Path(tmp) / "none.json", NOW)["reason"], "no_forecast_file")
            self.assertEqual(load_ghi_forecast(broken, NOW)["reason"], "unreadable_forecast_file")
            self.assertEqual(load_ghi_forecast(None, NOW)["reason"], "forecast_not_configured")

    def test_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, payload(datetime.now(KST)))
            with patch.dict(os.environ, {"GHI_FORECAST_FILE": str(path)}):
                response = Client().get("/api/forecast/ghi/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(Client().post("/api/forecast/ghi/").status_code, 405)


if __name__ == "__main__":
    unittest.main()
