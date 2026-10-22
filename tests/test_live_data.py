import copy
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from live_data.adapter import ACTUATOR_FIELDS, ENVIRONMENT_FIELDS, normalize_growlink_live
from live_data.sources import get_live_snapshot, load_mock_raw


SEOUL = ZoneInfo("Asia/Seoul")


class GrowlinkAdapterTests(unittest.TestCase):
    def test_fixture_maps_required_fields(self):
        dto = normalize_growlink_live(
            load_mock_raw(),
            timestamp="2026-09-23T17:13:10+09:00",
            source="mock_static",
        )
        self.assertTrue(dto["connected"])
        self.assertEqual(dto["environment"]["indoor_temperature_c"], 34.0)
        self.assertEqual(dto["environment"]["indoor_rh_pct"], 99.6)
        self.assertEqual(dto["environment"]["solar_w_m2"], 233.0)
        self.assertEqual(dto["actuators"]["roof_vent_left_pct"], 50.0)
        self.assertEqual(dto["actuators"]["roof_vent_right_pct"], 50.0)
        self.assertEqual(dto["actuators"]["shade_screen_1_pct"], 68.0)
        self.assertEqual(dto["actuators"]["shade_screen_2_pct"], 50.0)
        self.assertFalse(any(any(ord(char) > 127 for char in key) for key in dto["environment"]))

    def test_missing_invalid_and_clamped_values(self):
        raw = copy.deepcopy(load_mock_raw())
        house = raw["farm"]["zones"][0]["houses"][0]
        del house["meas"]["실내온도"]
        house["meas"]["내부습도"] = "invalid"
        house["acts"]["천창 좌(L)"] = -15
        house["acts"]["천창 우(R)"] = 150
        dto = normalize_growlink_live(raw)
        self.assertIsNone(dto["environment"]["indoor_temperature_c"])
        self.assertIsNone(dto["environment"]["indoor_rh_pct"])
        self.assertEqual(dto["actuators"]["roof_vent_left_pct"], 0.0)
        self.assertEqual(dto["actuators"]["roof_vent_right_pct"], 100.0)

    def test_missing_house_returns_complete_disconnected_dto(self):
        dto = normalize_growlink_live({"farm": {"outside": {}, "zones": []}})
        self.assertFalse(dto["connected"])
        self.assertEqual(set(dto["environment"]), set(ENVIRONMENT_FIELDS))
        self.assertEqual(set(dto["actuators"]), set(ACTUATOR_FIELDS))
        self.assertTrue(all(value is None for value in dto["environment"].values()))
        self.assertTrue(all(value is None for value in dto["actuators"].values()))

    def test_dynamic_source_changes_and_remains_bounded(self):
        first = get_live_snapshot("mock_dynamic", now=datetime(2026, 1, 1, 0, 0, 0, tzinfo=SEOUL))
        second = get_live_snapshot("mock_dynamic", now=datetime(2026, 1, 1, 0, 0, 7, tzinfo=SEOUL))
        self.assertNotEqual(first["actuators"]["roof_vent_left_pct"], second["actuators"]["roof_vent_left_pct"])
        self.assertNotEqual(first["environment"]["indoor_temperature_c"], second["environment"]["indoor_temperature_c"])
        for dto in (first, second):
            self.assertGreaterEqual(dto["actuators"]["shade_screen_1_pct"], 0.0)
            self.assertLessEqual(dto["actuators"]["shade_screen_1_pct"], 100.0)
            self.assertEqual(dto["source"], "mock_dynamic")

    def test_environment_source_selection(self):
        with patch.dict(os.environ, {"LIVE_DATA_SOURCE": "mock_static"}, clear=False):
            self.assertEqual(get_live_snapshot()["source"], "mock_static")

    def test_unsupported_source_does_not_fall_through_to_network(self):
        with self.assertRaisesRegex(ValueError, "Unsupported LIVE_DATA_SOURCE"):
            get_live_snapshot("growlink")

    def test_source_selection_has_no_growlink_field_translation(self):
        source_text = (Path(__file__).resolve().parents[1] / "live_data" / "sources.py").read_text(encoding="utf-8")
        for raw_key in ("실내온도", "내부습도", "천창 좌", "천창 우", "차광커튼"):
            self.assertNotIn(raw_key, source_text)



class StatusBlockTests(unittest.TestCase):
    def test_status_block_is_normalized(self):
        from live_data.adapter import normalize_status_block
        raw = {"status": {"운전모드": "자동", "감우": "ON", "강풍": "OFF", "전체경보": "OFF", "전체주의": "OFF", "알람 발생횟수": "0개"}}
        self.assertEqual(normalize_status_block(raw), {"operation_mode": "자동", "rain": True, "strong_wind": False,
                                                       "alarm": False, "caution": False, "alarm_count": 0})
        self.assertEqual(normalize_status_block({}), {k: None for k in ("operation_mode", "rain", "strong_wind",
                                                                         "alarm", "caution", "alarm_count")})


if __name__ == "__main__":
    unittest.main()
