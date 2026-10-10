"""Chronological split, causal features, XGBoost pipeline and sealed-run log."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from greenhouse_mpc.forecast.config import load_forecast_config
from greenhouse_mpc.forecast.features import build_samples
from greenhouse_mpc.forecast.model_pipeline import SealedRunError, run_model_pipeline
from greenhouse_mpc.forecast.split import make_folds, table_for_role
from greenhouse_mpc.ingestion.versioning import write_parquet

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "ghi_forecast.yaml"
CONFIG = load_forecast_config()


def synthetic_table(start="2026-07-28", days=74, skip=(), seed=0):
    """5-min grid; 08:00-16:00 'valid' daylight with an AR(1) kc, the rest 'night'."""
    times = pd.date_range(start, periods=days * 288, freq="5min", tz="Asia/Seoul")
    minute = times.hour * 60 + times.minute
    day_fraction = (minute - 720) / 720.0
    elevation = 60 * np.cos(np.pi * day_fraction) - 10
    rng = np.random.default_rng(seed)
    kc = np.empty(len(times))
    kc[0] = 0.7
    for i in range(1, len(times)):
        kc[i] = 0.7 + 0.85 * (kc[i - 1] - 0.7) + rng.normal(0, 0.06)
    daylight = (minute >= 480) & (minute < 960)
    skipped = np.isin(times.date, [pd.Timestamp(d).date() for d in skip])
    valid = daylight & ~skipped
    status = np.where(valid, "valid", np.where(daylight, "ghi_not_observed", "night"))
    clear = np.where(daylight, 800 * np.clip(np.sin(np.deg2rad(elevation)), 0, None), 0.0)
    kc = np.where(valid, kc, np.nan)
    return pd.DataFrame({"timestamp": times, "ghi": kc * clear, "ghi_clear": clear, "sun_elevation_deg": elevation,
                         "sun_azimuth_deg": 90 + 180 * (minute / 1440.0), "kc": kc, "kc_status": status,
                         "kc_input": kc, "kc_input_status": status})


class SplitTests(unittest.TestCase):
    def test_folds_merge_short_week_and_roles(self):
        skip = pd.date_range("2026-09-16", "2026-09-21").date             # leaves 2 days in the 9/14 week
        folds = make_folds(CONFIG, synthetic_table(skip=skip))
        layout = [(f.role, str(f.test_start), str(f.test_end)) for f in folds]
        self.assertEqual(layout, [("development", "2026-08-31", "2026-09-06"), ("development", "2026-09-07", "2026-09-13"),
                                  ("development", "2026-09-14", "2026-09-27"), ("checkpoint", "2026-09-28", "2026-10-04"),
                                  ("final", "2026-10-05", "2026-10-09")])
        for f in folds:
            self.assertEqual((f.test_start - f.validation_start).days, 7)

    def test_role_table_is_cut(self):
        cut = table_for_role(synthetic_table(), CONFIG, "development")
        self.assertEqual(cut.timestamp.max().date(), date(2026, 9, 27))


class FeatureTests(unittest.TestCase):
    def test_no_measured_value_after_issue_and_same_day(self):
        table = synthetic_table(days=3)
        samples, features = build_samples(table, 6, CONFIG)
        changed = table.copy()
        cut = pd.Timestamp("2026-07-29 12:00", tz="Asia/Seoul")
        later = changed.timestamp > cut
        changed.loc[later, ["kc", "kc_input", "ghi"]] = 9.9                # alter everything after t
        again, _ = build_samples(changed, 6, CONFIG)
        measured = [c for c in features if c.startswith("kc_")]
        pd.testing.assert_frame_equal(samples.loc[:cut, measured], again.loc[:cut, measured])
        self.assertTrue((samples.target_time.dt.date == samples.issue_day).all())
        first = samples[samples.issue_day == date(2026, 7, 29)].iloc[0]
        self.assertTrue(np.isnan(first.kc_lag_1))                          # no lag from the previous day
        row = samples.loc[cut]
        self.assertAlmostEqual(row.kc_mean_3, np.mean([row.kc_lag_0, row.kc_lag_1, row.kc_lag_2]))


class PipelineTests(unittest.TestCase):
    def test_development_run_and_sealed_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            text = CONFIG_PATH.read_text(encoding="utf-8").replace(
                "value: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]", "value: [1, 6]")
            (tmp / "ghi_forecast.yaml").write_text(text, encoding="utf-8")
            config = load_forecast_config(tmp / "ghi_forecast.yaml")
            write_parquet(synthetic_table(skip=pd.date_range("2026-09-16", "2026-09-21").date), tmp / "kc.parquet",
                          {"dataset_id": "k1", "pipeline": "clear_sky_index", "pipeline_version": "x",
                           "config_sha256": "c", "inputs_sha256": "i"})
            args = dict(config=config, kc_file=tmp / "kc.parquet", runs_dir=tmp / "runs", log_file=tmp / "log.jsonl")
            predictions, metrics, daily, _, folds = run_model_pipeline("development", **args)
            self.assertEqual(set(predictions.fold), {"development_1", "development_2", "development_3"})
            self.assertLessEqual(pd.Timestamp(predictions.target_time.max()).date(), date(2026, 9, 27))
            pooled = metrics[metrics.fold == "pooled"].set_index("h_steps")
            self.assertGreater(pooled.loc[1, "rmse_climatology"], pooled.loc[1, "rmse_xgboost"])
            again, *_ = run_model_pipeline("development", **args)
            pd.testing.assert_frame_equal(predictions, again)                # deterministic
            run_model_pipeline("checkpoint", **args)
            with self.assertRaises(SealedRunError):
                run_model_pipeline("checkpoint", **args)
            run_model_pipeline("checkpoint", rerun_reason="test", **args)
            log = (tmp / "log.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(log), 4)
            self.assertIn('"rerun_reason": "test"', log[-1])


if __name__ == "__main__":
    unittest.main()
