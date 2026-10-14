import os
import unittest


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenhouse_web.settings")

import django

django.setup()

from django.contrib.staticfiles import finders
from django.test import Client, SimpleTestCase


class DigitalTwinPhase18Tests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    def test_viewer_contains_phase18_controls_without_permanent_mapping_panel(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8")
        for label in ("전체", "앞면", "뒷면", "지붕", "내부", "설비", "제어 장치", "시점 초기화", "개발자", 'id="ops-panel"', 'id="ops-status"'):
            self.assertIn(label, text)
        self.assertIn('id="developer-drawer"', text)
        self.assertIn('aria-hidden="true"', text)
        self.assertIn('id="live-panel-toggle"', text)
        self.assertNotIn('class="mapping-panel"', text)

    def test_phase18_frontend_modules_are_discoverable(self):
        for name in (
            "digital_twin/js/viewer-config.mjs",
            "digital_twin/js/camera-runtime.mjs",
            "digital_twin/js/visibility-runtime.mjs",
            "digital_twin/js/interaction-runtime.mjs",
            "digital_twin/js/scene-registry.mjs",
        ):
            self.assertIsNotNone(finders.find(name), name)


if __name__ == "__main__":
    unittest.main()
