"""Field collector: GET only, outputs, outside CSV compatible with the dashboard export."""

import csv
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from live_data.sources import get_live_snapshot, load_field_snapshot

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collector", ROOT / "field_collector" / "collector.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
SAMPLE = json.loads((ROOT / "field_collector" / "sample_live_response.json").read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        Handler.requests.append(("GET", self.path, self.headers.get("Cookie")))
        body = json.dumps(SAMPLE, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        Handler.requests.append(("POST", self.path, None))
        self.send_response(405)
        self.end_headers()

    def log_message(self, *args):
        pass


class CollectorTests(unittest.TestCase):
    def test_fetch_is_a_plain_get_without_cookies(self):
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            Handler.requests.clear()
            data = collector.fetch(f"http://127.0.0.1:{server.server_port}/api/live", 5)
        finally:
            server.shutdown()
        self.assertEqual(data["farm"]["outside"]["일사량"], 173.0)
        self.assertEqual(Handler.requests, [("GET", "/api/live", None)])

    def test_outputs_and_outside_csv_layout(self):
        when = datetime(2026, 10, 11, 15, 43, 5, tzinfo=collector.KST)
        with tempfile.TemporaryDirectory() as tmp:
            collector.write_outputs(tmp, SAMPLE, when)
            collector.write_outputs(tmp, SAMPLE, when.replace(minute=44))
            with (Path(tmp) / "outside" / "outside_2026-10-11.csv").open(encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["시각", "누적일사량", "외부온도", "외부풍속", "외부풍향", "일사센서"])
            self.assertEqual(rows[1], ["2026-10-11 15:43:05", "835.0", "25.9", "1.1", "0° 북", "173.0"])
            self.assertEqual(len(rows), 3)
            raw = (Path(tmp) / "raw" / "live_2026-10-11.jsonl").read_text(encoding="utf-8").splitlines()
            first = json.loads(raw[0])
            self.assertEqual(first["collected_at"], "2026-10-11T15:43:05+09:00")
            self.assertNotIn("cards", first["response"])
            self.assertNotIn("act_rows", first["response"]["farm"])
            self.assertIn("zones", first["response"]["farm"])
            latest = json.loads((Path(tmp) / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["response"], SAMPLE)

    def test_config_only_allows_local_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"url": "http://192.168.0.2/api", "output_dir": tmp}), encoding="utf-8")
            with self.assertRaises(ValueError):
                collector.load_config(path)
            path.write_text(json.dumps({"url": "http://127.0.0.1:8000/api/live", "output_dir": tmp}), encoding="utf-8")
            self.assertEqual(collector.load_config(path)["interval_s"], 60)

    def test_missing_fields_stay_empty(self):
        row = collector.outside_row({"farm": {"outside": {"외부기온": 20.0}}}, datetime(2026, 10, 11, tzinfo=collector.KST))
        self.assertEqual(row, ["2026-10-11 00:00:00", "", 20.0, "", "", ""])


    def test_single_instance_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = collector.SingleInstance(tmp), collector.SingleInstance(tmp)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_step_pauses_on_low_disk_and_waits_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {"url": "http://127.0.0.1:1/api/live", "timeout_s": 1, "retry_wait_s": 300,
                      "min_free_disk_gb": 5, "output_dir": tmp}
            state = {}
            with patch.object(collector, "disk_ok", return_value=False), patch.object(collector, "fetch") as fetch:
                self.assertEqual(collector.step(config, state), 0)
                fetch.assert_not_called()                                   # no request while paused
            self.assertTrue(state["disk_paused"])
            with patch.object(collector, "fetch", side_effect=OSError("refused")):
                self.assertEqual(collector.step(config, state), 300)        # back off after a failure
                self.assertEqual(collector.step(config, state), 300)
            with patch.object(collector, "fetch", return_value=SAMPLE):
                self.assertEqual(collector.step(config, state), 0)
            log = (Path(tmp) / "collector.log").read_text(encoding="utf-8")
            self.assertEqual(log.count("read failed"), 1)                   # logged once, not every minute
            self.assertIn("resumed", log)
            self.assertIn("recovered", log)
            self.assertFalse(list((Path(tmp) / "outside").glob("*.csv")) == [])

    def test_interval_cannot_be_too_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"url": "http://127.0.0.1:8000/api/live", "output_dir": tmp, "interval_s": 2}),
                            encoding="utf-8")
            with self.assertRaises(ValueError):
                collector.load_config(path)


class FieldSourceTests(unittest.TestCase):
    def write_latest(self, tmp, collected_at):
        path = Path(tmp) / "latest.json"
        path.write_text(json.dumps({"collected_at": collected_at.isoformat(), "response": SAMPLE}, ensure_ascii=False),
                        encoding="utf-8")
        return path

    def test_fresh_file_is_normalized(self):
        collected = datetime(2026, 10, 11, 15, 43, 5, tzinfo=collector.KST)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_latest(tmp, collected)
            dto = load_field_snapshot(path, collected + timedelta(seconds=40))
        self.assertEqual(dto["source"], "field_collector")
        self.assertTrue(dto["connected"])
        self.assertEqual(dto["timestamp"], collected.isoformat())
        self.assertEqual(dto["environment"]["indoor_temperature_c"], 29.3)
        self.assertEqual(dto["environment"]["solar_w_m2"], 173.0)
        self.assertEqual(dto["actuators"]["roof_vent_left_pct"], 100.0)
        self.assertEqual(dto["actuators"]["shade_screen_1_pct"], 50.0)

    def test_old_missing_or_broken_file_gives_nulls(self):
        collected = datetime(2026, 10, 11, 15, 43, 5, tzinfo=collector.KST)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_latest(tmp, collected)
            old = load_field_snapshot(path, collected + timedelta(minutes=10))
            broken = Path(tmp) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            for dto in (old, load_field_snapshot(Path(tmp) / "none.json", collected), load_field_snapshot(broken, collected),
                        load_field_snapshot(None, collected)):
                self.assertFalse(dto["connected"])
                self.assertTrue(all(v is None for v in dto["environment"].values()))
                self.assertTrue(all(v is None for v in dto["actuators"].values()))
        self.assertEqual(old["timestamp"], collected.isoformat())           # shows when the last data was taken

    def test_environment_selects_field_source(self):
        now = datetime.now(collector.KST)
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_latest(tmp, now)
            with patch.dict(os.environ, {"LIVE_DATA_SOURCE": "field_collector", "LIVE_DATA_FILE": str(path)}):
                dto = get_live_snapshot()
        self.assertEqual(dto["source"], "field_collector")
        self.assertTrue(dto["connected"])


if __name__ == "__main__":
    unittest.main()
