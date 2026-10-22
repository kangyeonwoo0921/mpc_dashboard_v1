"""Live runner: forecast payload states, failure handling, input file selection."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from greenhouse_mpc.forecast import live_runner
from greenhouse_mpc.forecast.config import load_forecast_config
from greenhouse_mpc.forecast.operation import OperationPaths, update
from greenhouse_mpc.ingestion.outside_schema import load_outside_config
from test_forecast_model import synthetic_table

KST = "Asia/Seoul"


class LiveRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        table = synthetic_table(days=40)                                     # 2026-07-28 .. 2026-09-05
        table["ghi_input_status"] = "observed"
        table["ghi_status"] = table.kc_status.map({"valid": "observed"}).fillna("missing")
        cls.table = table
        cls.config = load_forecast_config()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.paths = OperationPaths.sandbox(cls.tmp.name)
        update(cls.config, table, date(2026, 8, 31), cls.paths)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def payload(self, now, max_age=15):
        return live_runner.forecast_payload(self.config, self.table, pd.Timestamp(now, tz=KST), self.paths, max_age)

    def test_last_complete_bin(self):
        self.assertEqual(live_runner.last_complete_bin(pd.Timestamp("2026-09-01 12:07:30", tz=KST)),
                         pd.Timestamp("2026-09-01 12:00", tz=KST))

    def test_ok_payload_has_all_horizons(self):
        p = self.payload("2026-09-01 12:07")
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["issue_time"], "2026-09-01T12:00:00+09:00")
        self.assertEqual([h["horizon_min"] for h in p["horizons"]], list(range(5, 65, 5)))
        self.assertEqual({h["method"] for h in p["horizons"][:6]}, {"xgb_expanding"})
        self.assertEqual({h["method"] for h in p["horizons"][6:]}, {"convex_combination"})
        self.assertTrue(all(h["ghi_w_m2"] is not None for h in p["horizons"]))
        recent = p["recent_observations"]
        self.assertEqual(len(recent), 12)
        self.assertEqual(recent[-1]["time"], "2026-09-01T12:00:00+09:00")                # up to the issue bin
        json.dumps(p)                                                         # serialisable

    def test_rain_switches_every_horizon_to_persistence(self):
        now = pd.Timestamp("2026-09-01 12:07", tz=KST)
        dry = live_runner.forecast_payload(self.config, self.table, now, self.paths, 15, rain=False)
        wet = live_runner.forecast_payload(self.config, self.table, now, self.paths, 15, rain=True)
        unknown = live_runner.forecast_payload(self.config, self.table, now, self.paths, 15, rain=None)
        self.assertEqual({h["method"] for h in wet["horizons"]}, {"persistence_rain"})
        self.assertEqual([h["method"] for h in dry["horizons"]], [h["method"] for h in unknown["horizons"]])
        kc_now = self.table.set_index("timestamp").at[pd.Timestamp("2026-09-01 12:00", tz=KST), "kc_input"]
        self.assertTrue(all(abs(h["kc"] - round(kc_now, 4)) < 1e-4 for h in wet["horizons"]))   # kc held at the issue value
        self.assertIs(wet["rain"], True)
        logged = pd.read_parquet(self.paths.live)
        self.assertIn("kc_hat_persistence", logged.columns)                  # persistence kept for later evaluation

    def test_rain_flag_from_collector_file(self):
        now = pd.Timestamp("2026-10-20 15:00", tz=KST)
        with tempfile.TemporaryDirectory() as field:
            latest = Path(field) / "latest.json"

            def write(status, collected="2026-10-20T14:59:05+09:00"):
                latest.write_text(json.dumps({"collected_at": collected, "response": {"status": status}}, ensure_ascii=False),
                                  encoding="utf-8")
            write({"감우": "ON"})
            self.assertIs(live_runner.rain_now(field, now, 15), True)
            write({"감우": "OFF"})
            self.assertIs(live_runner.rain_now(field, now, 15), False)
            write({"감우": "ON"}, collected="2026-10-20T14:00:00+09:00")
            self.assertIsNone(live_runner.rain_now(field, now, 15))           # stale -> unknown -> no override
            write({})
            self.assertIsNone(live_runner.rain_now(field, now, 15))
        self.assertIsNone(live_runner.rain_now(None, now, 15))

    def test_rain_is_held_for_an_hour_after_the_last_on_minute(self):
        with tempfile.TemporaryDirectory() as field, tempfile.TemporaryDirectory() as ops:
            state = Path(ops) / "rain_state.json"
            latest = Path(field) / "latest.json"

            def sample(minute, value):
                collected = pd.Timestamp("2026-10-20 13:00", tz=KST) + pd.Timedelta(minutes=minute)
                latest.write_text(json.dumps({"collected_at": collected.isoformat(), "response": {"status": {"감우": value}}},
                                             ensure_ascii=False), encoding="utf-8")
                return collected + pd.Timedelta(seconds=30)

            now = sample(0, "ON")
            self.assertIs(live_runner.rain_recent(field, now, 15, 60, state), True)
            now = sample(1, "OFF")                                            # flicker: still rain
            self.assertIs(live_runner.rain_recent(field, now, 15, 60, state), True)
            now = sample(55, "OFF")
            self.assertIs(live_runner.rain_recent(field, now, 15, 60, state), True)
            now = sample(61, "OFF")                                           # 61 min after the last ON minute
            self.assertIs(live_runner.rain_recent(field, now, 15, 60, state), False)
            now = sample(70, "ON")
            live_runner.observe_rain(field, now, 15, state)                   # per-minute sampling between cycles
            now = sample(75, "OFF")
            self.assertIs(live_runner.rain_recent(field, now, 15, 60, state), True)   # remembered from the file

    def test_rain_memory_is_seeded_from_the_raw_log(self):
        with tempfile.TemporaryDirectory() as field, tempfile.TemporaryDirectory() as ops:
            (Path(field) / "raw").mkdir()
            lines = [{"collected_at": f"2026-10-20T15:{m:02d}:05+09:00", "response": {"status": {"감우": v}}}
                     for m, v in ((38, "OFF"), (40, "ON"), (41, "OFF"))]
            (Path(field) / "raw" / "live_2026-10-20.jsonl").write_text(
                "".join(json.dumps(x, ensure_ascii=False) + chr(10) for x in lines), encoding="utf-8")
            (Path(field) / "latest.json").write_text(json.dumps({"collected_at": "2026-10-20T15:56:05+09:00",
                "response": {"status": {"감우": "OFF"}}}, ensure_ascii=False), encoding="utf-8")
            now = pd.Timestamp("2026-10-20 15:57", tz=KST)
            self.assertIs(live_runner.rain_recent(field, now, 15, 60, Path(ops) / "rain_state.json"), True)
            later = pd.Timestamp("2026-10-20 16:41", tz=KST)              # 61 min after 15:40
            self.assertIs(live_runner.rain_recent(field, later, 15, 60, Path(ops) / "rain_state.json"), None)

    def test_unavailable_states(self):
        self.assertEqual(self.payload("2026-09-01 22:07")["reason"], "night")
        late = self.payload("2026-09-10 12:07")                              # data ends 09-05
        self.assertEqual((late["status"], late["reason"]), ("unavailable", "data_stale"))
        self.assertIsNone(late["horizons"])

    def test_failing_cycle_writes_error_and_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            latest = Path(tmp) / "latest.json"
            with patch.object(live_runner, "run_outside_pipeline", side_effect=OSError("file locked by sync")):
                payload = live_runner.run_cycle(now=pd.Timestamp("2026-09-01 12:07", tz=KST), field_dir=tmp,
                                                paths=self.paths, latest_file=latest)
            self.assertEqual(payload["status"], "error")
            self.assertIn("file locked by sync", json.loads(latest.read_text(encoding="utf-8"))["reason"])

    def test_input_files_include_field_outside_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "outside").mkdir()
            (Path(tmp) / "outside" / "outside_2026-10-11.csv").write_text("x", encoding="utf-8")
            (Path(tmp) / "outside" / "notes.txt").write_text("x", encoding="utf-8")
            files = live_runner.input_files(load_outside_config(), tmp)
        self.assertEqual(files[-1].name, "outside_2026-10-11.csv")
        self.assertFalse(any(f.name == "notes.txt" for f in files))
        self.assertEqual(live_runner.input_files(load_outside_config(), None)[-1].parent.name, "ouside_data")


if __name__ == "__main__":
    unittest.main()
