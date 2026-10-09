import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenhouse_web.settings")

import django

django.setup()

from django.test import Client, SimpleTestCase

from digital_twin.mpc_mock import SCHEMA_VERSION, build_payload

KST = ZoneInfo("Asia/Seoul")
CONTROLS = ("roof_vent_percent", "shade_screen_open_percent", "diffuse_screen_open_percent")


class MpcMockPayloadTests(unittest.TestCase):
    def test_ok_shape_and_horizon(self):
        payload = build_payload(datetime(2026, 10, 9, 12, 0, tzinfo=KST))
        self.assertTrue(payload["is_mock"])
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertEqual((payload["status"], payload["mode"]), ("ok", "recommendation_only"))
        self.assertEqual(len(payload["trajectory"]["times"]), 12)           # 60 min / 5 min
        self.assertEqual(len(payload["predicted"]["times"]), 13)            # includes t0
        for key in CONTROLS:
            self.assertTrue(0 <= payload["recommendation"][key] <= 100)
            self.assertEqual(len(payload["trajectory"][key]), 12)
            self.assertTrue(all(0 <= v <= 100 for v in payload["trajectory"][key]))
        for key in ("T_air_C", "RH_air_percent", "VPD_air_kPa", "radiation_crop_W_m2", "Q_vent_W_m2"):
            self.assertEqual(len(payload["predicted"][key]), 13)

    def test_moves_are_held_after_control_horizon(self):
        trajectory = build_payload(datetime(2026, 10, 9, 10, 0, tzinfo=KST))["trajectory"]["roof_vent_percent"]
        self.assertEqual(len(set(trajectory[3:])), 1)                       # control horizon = 4 steps

    def test_night_closes_vents_and_deploys_shade(self):
        payload = build_payload(datetime(2026, 10, 9, 23, 0, tzinfo=KST))
        self.assertEqual(payload["supervisor"]["day_phase_state"], "NIGHT_INSULATION")
        self.assertEqual(payload["recommendation"]["roof_vent_percent"], 0.0)
        self.assertLess(payload["recommendation"]["shade_screen_open_percent"], 100)

    def test_unavailable_and_degraded(self):
        now = datetime(2026, 10, 9, 12, 0, tzinfo=KST)
        unavailable = build_payload(now, "unavailable")
        self.assertEqual(unavailable["status"], "recommendation_unavailable")
        self.assertTrue(unavailable["reasons"])
        for key in ("recommendation", "trajectory", "predicted", "diagnostics"):
            self.assertIsNone(unavailable[key])
        degraded = build_payload(now, "degraded")
        self.assertEqual(degraded["status"], "degraded")
        self.assertTrue(degraded["reasons"])
        self.assertIsNotNone(degraded["recommendation"])

    def test_current_maps_live_channels(self):
        snapshot = {"actuators": {"roof_vent_left_pct": 40, "roof_vent_right_pct": 60,
                                  "shade_screen_1_pct": 90, "shade_screen_2_pct": 30}}
        current = build_payload(datetime(2026, 10, 9, 12, 0, tzinfo=KST), snapshot=snapshot)["current"]
        self.assertEqual(current, {"roof_vent_percent": 50.0, "diffuse_screen_open_percent": 90,
                                   "shade_screen_open_percent": 30})
        missing = build_payload(datetime(2026, 10, 9, 12, 0, tzinfo=KST), snapshot={})["current"]
        self.assertTrue(all(v is None for v in missing.values()))           # missing is never 0

    def test_unknown_scenario_rejected(self):
        with self.assertRaises(ValueError):
            build_payload(datetime(2026, 10, 9, 12, 0, tzinfo=KST), "fault")


class MpcMockEndpointTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    def test_endpoint_statuses(self):
        for scenario, status in (("ok", "ok"), ("degraded", "degraded"), ("unavailable", "recommendation_unavailable")):
            response = self.client.get("/api/mpc/recommendation/", {"scenario": scenario})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(response.json()["status"], status)
            self.assertTrue(response.json()["is_mock"])

    def test_bad_requests(self):
        self.assertEqual(self.client.get("/api/mpc/recommendation/", {"scenario": "x"}).status_code, 400)
        self.assertEqual(self.client.post("/api/mpc/recommendation/").status_code, 405)


if __name__ == "__main__":
    unittest.main()
