"""Recommendation settings store and endpoints."""

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenhouse_web.settings")
import django  # noqa: E402

django.setup()
from django.test import Client  # noqa: E402

from recommendation import settings_store  # noqa: E402


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RECOMMENDATION_DATA_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_defaults_match_user_decisions(self):
        values = settings_store.load()["values"]
        self.assertEqual((values["shade_threshold_w_m2"], values["persistence_min"], values["growth_stage"],
                          values["operation_mode"]), (700, 15, "vegetative", "auto"))

    def test_validation(self):
        bad = {"shade_threshold_w_m2": 1500, "persistence_min": 7, "growth_stage": "x", "transplant_date": "22/09",
               "unknown": 1, "diffuse_tout_threshold_c": "warm"}
        with self.assertRaises(settings_store.SettingsError) as ctx:
            settings_store.save(bad)
        self.assertEqual(set(ctx.exception.errors), set(bad))
        self.assertEqual(settings_store.load()["values"]["shade_threshold_w_m2"], 700)      # nothing stored

    def test_save_logs_only_changes_and_reset(self):
        now = datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        settings_store.save({"shade_threshold_w_m2": 650, "persistence_min": 15}, changed_by="연우", note="현장 설정값", now=now)
        state = settings_store.load()
        self.assertEqual((state["values"]["shade_threshold_w_m2"], state["updated_by"]), (650, "연우"))
        log = settings_store.history()
        self.assertEqual(log[0]["changes"], {"shade_threshold_w_m2": {"from": 700, "to": 650}})
        settings_store.save({"shade_threshold_w_m2": 650})                                   # no change -> no log line
        self.assertEqual(len(settings_store.history()), 1)
        settings_store.reset()
        self.assertEqual(settings_store.load()["values"]["shade_threshold_w_m2"], 700)
        self.assertEqual(settings_store.history()[0]["note"], "기본값으로 되돌림")

    def test_corrupt_file_falls_back_to_defaults(self):
        Path(self.tmp.name, "settings.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(settings_store.load()["values"], settings_store.DEFAULTS)

    def test_every_default_is_valid(self):
        self.assertEqual(settings_store.validate(dict(settings_store.DEFAULTS)), settings_store.DEFAULTS)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RECOMMENDATION_DATA_DIR": self.tmp.name, "LIVE_DATA_SOURCE": "mock_static"})
        self.env.start()
        self.client = Client()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_settings_get_post_reset(self):
        desc = self.client.get("/api/recommendation/settings/").json()
        self.assertEqual(desc["schema_version"], "recommendation-settings/0.1")
        self.assertTrue(all({"key", "label", "source", "default"} <= set(f) for f in desc["fields"]))
        bad = self.client.post("/api/recommendation/settings/", json.dumps({"values": {"persistence_min": 3}}),
                               content_type="application/json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("persistence_min", bad.json()["errors"])
        ok = self.client.post("/api/recommendation/settings/", json.dumps({"values": {"operation_mode": "cold"}, "changed_by": "test"}),
                              content_type="application/json")
        self.assertEqual(ok.json()["values"]["operation_mode"], "cold")
        reset = self.client.post("/api/recommendation/settings/reset/", "{}", content_type="application/json")
        self.assertEqual(reset.json()["values"]["operation_mode"], "auto")
        self.assertEqual(self.client.put("/api/recommendation/settings/").status_code, 405)

    def test_screens_endpoint_and_page(self):
        response = self.client.get("/api/recommendation/screens/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual((payload["schema_version"], payload["mode"]), ("screen-recommendation/0.1", "recommendation_only"))
        self.assertEqual(set(payload["screens"]), {"shade_screen", "diffuse_screen"})
        self.assertEqual(len(payload["plan_times"]), 13)
        self.assertIn(payload["crop_light"]["status"], ("ok", "unavailable"))     # physics is optional
        page = self.client.get("/recommendation/")
        self.assertEqual(page.status_code, 200)
        text = page.content.decode("utf-8")
        self.assertIn("recommendation.mjs?v=", text)
        self.assertIn('type="importmap"', text)                                  # shared modules are versioned too
        self.assertIn("ops-status.mjs?v=", text)

    def test_radiation_preview_parameters(self):
        ok = self.client.get("/api/digital-twin/radiation/v1/",
                             {"time": "2026-10-12T12:30:00+09:00", "ghi": "600", "ghi_source": "forecast", "shade_screen_2": "0"})
        self.assertEqual(ok.status_code, 200)
        body = ok.json()
        self.assertEqual(body["inputs"]["weather"]["source"], "forecast")
        self.assertEqual(body["inputs"]["weather"]["decomposition"]["model"], "engerer2")
        self.assertEqual(body["inputs"]["actuators"]["shade_screen_2_opening_percent"], 0.0)
        self.assertEqual(self.client.get("/api/digital-twin/radiation/v1/", {"ghi": "-5"}).status_code, 400)
        self.assertEqual(self.client.get("/api/digital-twin/radiation/v1/", {"shade_screen_1": "x"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
