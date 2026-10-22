"""Live forecast vs observed report (forecast/live_eval.py)."""

import unittest

import numpy as np
import pandas as pd

from greenhouse_mpc.forecast.live_eval import matched_pairs, report, summary

T0 = pd.Timestamp("2026-10-16 10:45", tz="Asia/Seoul")


def kc_table():
    times = pd.date_range(T0, periods=4, freq="5min")
    return pd.DataFrame({"timestamp": times, "ghi": [400.0, 420.0, 440.0, np.nan],
                         "kc": [0.6, 0.62, 0.64, np.nan], "kc_status": ["valid", "valid", "valid", "missing"],
                         "kc_input": [0.6, 0.62, 0.64, np.nan], "kc_input_status": ["valid", "valid", "valid", "missing"]})


def live_log():
    rows = []
    for h, ghi_hat in ((1, 430.0), (2, 430.0), (3, 500.0)):
        rows.append({"issue_time": T0, "h_steps": h, "target_time": T0 + pd.Timedelta(minutes=5 * h),
                     "ghi_clear": 700.0, "ghi_hat": ghi_hat, "ghi_hat_xgb_expanding": ghi_hat,
                     "ghi_hat_convex_combination": 450.0, "method": "xgb_expanding"})
    return pd.DataFrame(rows)


class LiveEvalTests(unittest.TestCase):
    def test_pairs_use_valid_observations_only(self):
        pairs = matched_pairs(live_log(), kc_table())
        self.assertEqual(pairs.horizon_min.tolist(), [5, 10])          # +15 min target is not observed (missing)
        self.assertEqual(pairs.ghi_obs.tolist(), [420.0, 440.0])
        self.assertAlmostEqual(pairs.ghi_hat_persistence.iloc[0], 0.6 * 700.0)   # kc at issue x clear at target

    def test_metrics_and_skill(self):
        table = summary(matched_pairs(live_log(), kc_table()))
        first = table.iloc[0]
        self.assertEqual((first.samples, first.days), (1, 1))
        self.assertAlmostEqual(first.rmse_used, 10.0)
        self.assertAlmostEqual(first.bias_used, 10.0)
        self.assertAlmostEqual(first.rmse_cc, 30.0)
        self.assertAlmostEqual(first.skill_vs_cc, 1 - 10.0 / 30.0)
        self.assertIn("RMSE", report(table))

    def test_empty_log(self):
        self.assertTrue(matched_pairs(None, kc_table()).empty)
        self.assertIn("아직", report(pd.DataFrame()))



class ModelCompleteTests(unittest.TestCase):
    def test_empty_or_partial_model_folder_counts_as_missing(self):
        import tempfile
        from pathlib import Path

        from greenhouse_mpc.forecast.operation import model_complete
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "m1"
            folder.mkdir()
            self.assertFalse(model_complete(tmp, "m1", [1, 2]))            # empty folder (10-16 incident)
            (folder / "h01.json").write_text("{}")
            (folder / "h02.json").write_text("{}")
            self.assertFalse(model_complete(tmp, "m1", [1, 2]))            # no meta.json: training interrupted
            (folder / "meta.json").write_text("{}")
            self.assertTrue(model_complete(tmp, "m1", [1, 2]))


if __name__ == "__main__":
    unittest.main()
