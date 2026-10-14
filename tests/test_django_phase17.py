import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenhouse_web.settings")

import django

django.setup()

from django.contrib.staticfiles import finders
from django.test import Client, SimpleTestCase


class DigitalTwinDjangoTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    def test_viewer_route_renders_real_three_entrypoints(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8")
        self.assertIn("greenhouse.glb", text)
        self.assertIn("digital_twin/vendor/three/three.module.js", text)
        self.assertNotIn("cdn.jsdelivr.net", text)
        self.assertIn("GLTFLoader", Path(finders.find("digital_twin/js/viewer.mjs")).read_text(encoding="utf-8"))
        self.assertIn("OrbitControls", Path(finders.find("digital_twin/js/viewer.mjs")).read_text(encoding="utf-8"))
        self.assertIn("실시간 — 모의 데이터", text)

    def test_three_runtime_is_vendored_for_local_execution(self):
        for name in (
            "digital_twin/vendor/three/three.module.js",
            "digital_twin/vendor/three/three.core.js",
            "digital_twin/vendor/three/addons/loaders/GLTFLoader.js",
            "digital_twin/vendor/three/addons/controls/OrbitControls.js",
            "digital_twin/vendor/three/addons/utils/BufferGeometryUtils.js",
            "digital_twin/vendor/three/LICENSE",
        ):
            self.assertIsNotNone(finders.find(name), name)

    def test_live_api_returns_normalized_dynamic_dto(self):
        with patch.dict(os.environ, {"LIVE_DATA_SOURCE": "mock_dynamic"}, clear=False):
            response = self.client.get("/api/digital-twin/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        dto = response.json()
        self.assertEqual(dto["source"], "mock_dynamic")
        self.assertIn("environment", dto)
        self.assertIn("actuators", dto)
        self.assertIn("roof_vent_left_pct", dto["actuators"])
        self.assertNotIn("실내온도", json.dumps(dto, ensure_ascii=False))

    def test_live_api_is_get_only(self):
        response = self.client.post("/api/digital-twin/live/", data={})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers["Allow"], "GET")

    def test_static_glb_is_discoverable_and_valid(self):
        path = Path(finders.find("digital_twin/models/greenhouse.glb"))
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_bytes()[:4], b"glTF")


if __name__ == "__main__":
    unittest.main()
