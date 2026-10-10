"""Operational layer: weekly update, gate, sanity checks, live forecasts without future rows, replay."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from greenhouse_mpc.forecast.config import load_forecast_config
from greenhouse_mpc.forecast.operation import OperationPaths, forecast_at, gate, load_state, replay, update
from test_forecast_model import synthetic_table

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "ghi_forecast.yaml"


def config_with(tmp, **replacements):
    text = CONFIG_PATH.read_text(encoding="utf-8")
    for old, new in replacements.items():
        assert old in text, old
        text = text.replace(old, new)
    path = Path(tmp) / "ghi_forecast.yaml"
    path.write_text(text, encoding="utf-8")
    return load_forecast_config(path)


class OperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = synthetic_table(days=40)                       # 2026-07-28 .. 2026-09-05
        cls.config = load_forecast_config()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = OperationPaths.sandbox(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_update_initial_policy_and_state(self):
        state, record = update(self.config, self.table, date(2026, 8, 31), self.paths, "k1")
        self.assertEqual(list(state["active"]), ["xgb_expanding"])
        methods = {h: p["method"] for h, p in state["policy"].items()}
        self.assertEqual({methods[str(h)] for h in range(1, 7)}, {"xgb_expanding"})
        self.assertEqual({methods[str(h)] for h in range(7, 13)}, {"convex_combination"})
        self.assertEqual(state["reference_statistics"]["estimated_from"][1], "2026-08-30")   # before as_of only
        self.assertTrue(record["training"]["xgb_expanding"]["activated"])
        self.assertEqual(load_state(self.paths), state)
        self.assertEqual(len(self.paths.log.read_text(encoding="utf-8").splitlines()), 1)

    def test_forecast_uses_no_future_rows(self):
        update(self.config, self.table, date(2026, 8, 31), self.paths)
        issue = pd.Timestamp("2026-09-01 11:00", tz="Asia/Seoul")
        full = forecast_at(self.config, self.table, [issue], self.paths, log=False)
        cut = forecast_at(self.config, self.table[self.table.timestamp <= issue], [issue], self.paths, log=False)
        pd.testing.assert_frame_equal(full, cut)
        self.assertEqual(len(full), 12)
        np.testing.assert_allclose(full.ghi_hat, full.kc_hat * full.ghi_clear)
        self.assertTrue((full.method.iloc[:6] == "xgb_expanding").all() and (full.method.iloc[6:] == "convex_combination").all())

    def test_gate_switches_to_reference_and_keeps_on_sparse_record(self):
        update(self.config, self.table, date(2026, 8, 24), self.paths)
        days = pd.Series(pd.DatetimeIndex(self.table.timestamp).date)
        week = self.table[((days >= date(2026, 8, 24)) & (days <= date(2026, 8, 30))).to_numpy()]
        live = forecast_at(self.config, self.table, week.timestamp[week.kc_input_status.eq("valid")], self.paths)
        live["ghi_hat_xgb_expanding"] = live.ghi_hat_xgb_expanding + 300.0           # make the model clearly worse
        state = load_state(self.paths)
        policy, evidence = gate(self.config, state, live, self.table, date(2026, 8, 31))
        self.assertEqual(policy["1"]["method"], "convex_combination")
        self.assertGreater(evidence["1"]["rmse"]["xgb_expanding"], evidence["1"]["rmse"]["convex_combination"])
        sparse = live[pd.Series(pd.DatetimeIndex(live.target_time).date).isin([date(2026, 8, 24), date(2026, 8, 25)]).to_numpy()]
        kept, _ = gate(self.config, state, sparse, self.table, date(2026, 8, 31))
        self.assertEqual(kept["1"]["method"], state["policy"]["1"]["method"])
        self.assertIn("kept", kept["1"]["reason"])

    def test_sanity_check_blocks_activation(self):
        update(self.config, self.table, date(2026, 8, 24), self.paths)
        first = load_state(self.paths)["active"]["xgb_expanding"]
        strict = config_with(self.tmp.name, **{"value: [0.0, 2.0]": "value: [0.0, 0.1]"})
        state, record = update(strict, self.table, date(2026, 8, 31), self.paths)
        self.assertFalse(record["training"]["xgb_expanding"]["activated"])
        self.assertEqual(state["active"]["xgb_expanding"], first)                   # previous model stays

    def test_replay_writes_only_to_sandbox(self):
        records = replay(self.config, self.table, "2026-08-24", "2026-09-04", self.paths)
        self.assertEqual([r["as_of"] for r in records], ["2026-08-24", "2026-08-31"])
        self.assertIn("gate_evidence", records[1])
        self.assertTrue(records[1]["gate_evidence"])                                 # second week judged on the live record
        self.assertTrue(all(r["training"]["xgb_expanding"]["activated"] for r in records))
        second = json.loads((self.paths.models / records[1]["training"]["xgb_expanding"]["model_id"] / "meta.json").read_text())
        self.assertEqual(second["active_model_id"], records[0]["training"]["xgb_expanding"]["model_id"])
        self.assertIn("active_validation_kc_rmse", second["horizons"]["1"])   # compared on the same days
        live = pd.read_parquet(self.paths.live)
        self.assertEqual(live.groupby(["issue_time", "h_steps"]).size().max(), 1)
        self.assertTrue(set(Path(self.tmp.name).iterdir()) >= {self.paths.state, self.paths.log, self.paths.live})


if __name__ == "__main__":
    unittest.main()
