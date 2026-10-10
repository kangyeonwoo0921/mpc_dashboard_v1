"""Reference forecasts and metrics (Chu et al. 2021; Alonso-Suarez et al. 2022; Yang 2019; Yang et al. 2020)."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from greenhouse_mpc.forecast.baseline_pipeline import run_baseline_pipeline
from greenhouse_mpc.forecast.baselines import evaluate, forecast_kc, internal_statistics
from greenhouse_mpc.forecast.config import load_forecast_config
from greenhouse_mpc.forecast.metrics import mae, mbe, rmse, skill
from greenhouse_mpc.ingestion.versioning import write_parquet
from greenhouse_mpc.provenance import ProvenanceError

CONFIG_TEXT = (Path(__file__).resolve().parents[1] / "config" / "ghi_forecast.yaml").read_text(encoding="utf-8")


def table(kc, clear=None):
    kc = np.asarray(kc, dtype=float)
    clear = np.full(len(kc), 500.0) if clear is None else np.asarray(clear, dtype=float)
    times = pd.date_range("2026-09-07 08:00", periods=len(kc), freq="5min", tz="Asia/Seoul")
    status = np.where(np.isfinite(kc), "valid", "low_sun")
    return pd.DataFrame({"timestamp": times, "kc": kc, "ghi_clear": clear, "ghi": kc * clear,
                         "kc_status": status, "kc_input": kc, "kc_input_status": status})


def ar1(length, phi=0.9, seed=0):
    rng = np.random.default_rng(seed)
    x = np.zeros(length)
    for i in range(1, length):
        x[i] = phi * x[i - 1] + rng.normal(0, 0.05)
    return 0.7 + x


class MetricTests(unittest.TestCase):
    def test_definitions(self):
        f, o = np.array([110.0, 90.0, 130.0]), np.array([100.0, 100.0, 100.0])
        self.assertAlmostEqual(mbe(f, o), 10.0)
        self.assertAlmostEqual(mae(f, o), 50.0 / 3)
        self.assertAlmostEqual(rmse(f, o), np.sqrt(1100.0 / 3))
        self.assertAlmostEqual(skill(80.0, 100.0), 0.2)
        with self.assertRaises(ValueError):
            rmse([np.nan], [1.0])


class ReferenceForecastTests(unittest.TestCase):
    def test_persistence_equals_chu_form(self):
        clear = [400.0, 450.0, 500.0, 520.0]
        frame = table([0.5, 0.6, 0.7, 0.8], clear)
        kc_hat = forecast_kc(frame, 2, "persistence")
        # I_hat(t+FH) = I(t) / I_clr(t) * I_clr(t+FH)
        self.assertAlmostEqual(kc_hat.iloc[2] * clear[2], frame.ghi[0] / clear[0] * clear[2])
        self.assertTrue(kc_hat.iloc[:2].isna().all())

    def test_window_mean_strict(self):
        kc_hat = forecast_kc(table([0.2, 0.4, 0.6, np.nan, 0.8, 1.0]), 1, "window_mean", n=2)
        np.testing.assert_allclose(kc_hat, [np.nan, np.nan, 0.3, 0.5, np.nan, np.nan])

    def test_internal_statistics_and_convex_combination(self):
        values = [0.2, 0.4, np.nan, 0.6, 0.8, 0.5]
        stats = internal_statistics(table(values), [1])
        x = np.array([0.2, 0.4, 0.6, 0.8, 0.5])
        mu, s2 = x.mean(), x.var()
        self.assertAlmostEqual(stats.mu, mu)
        self.assertAlmostEqual(stats.sigma2, s2)
        pairs = [(0.4, 0.2), (0.8, 0.6), (0.5, 0.8)]                  # lag 1 on the grid; gap not bridged
        self.assertEqual(stats.pairs[1], 3)
        self.assertAlmostEqual(stats.rho[1], np.mean([(a - mu) * (b - mu) for a, b in pairs]) / s2)
        cc = forecast_kc(table(values), 1, "convex_combination", stats)
        self.assertAlmostEqual(cc.iloc[1], stats.rho[1] * 0.2 + (1 - stats.rho[1]) * mu)

    def test_convex_combination_not_worse_than_either_reference(self):
        results, stats = evaluate(table(ar1(3000)), [1, 6, 24])
        for _, group in results.groupby("h_steps"):
            by_method = group.set_index("method")
            self.assertLessEqual(by_method.rmse["convex_combination"],
                                 min(by_method.rmse["persistence"], by_method.rmse["climatology"]) + 1e-9)
            self.assertAlmostEqual(by_method.skill["convex_combination"], 0.0)
            self.assertEqual(group["count"].nunique(), 1)
        self.assertGreater(stats.rho[1], stats.rho[24])

    def test_inputs_are_causal_kc(self):
        frame = table([0.5, 0.6, 0.7])
        frame.loc[0, "kc_input_status"] = "ghi_not_observed"            # not usable at issue time
        kc_hat = forecast_kc(frame, 1, "persistence")
        self.assertTrue(np.isnan(kc_hat.iloc[1]))
        self.assertAlmostEqual(kc_hat.iloc[2], 0.6)

    def test_irregular_grid_rejected(self):
        with self.assertRaises(ValueError):
            forecast_kc(table([0.5, 0.6, 0.7]).drop(index=1), 1, "persistence")


class ForecastConfigTests(unittest.TestCase):
    def test_option_a(self):
        config = load_forecast_config()
        self.assertEqual(config.value("horizon_steps"), list(range(1, 13)))
        self.assertEqual(config.value("reference"), "convex_combination")

    def test_bad_reference_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "ghi_forecast.yaml"
            bad.write_text(CONFIG_TEXT.replace("value: convex_combination", "value: smart"), encoding="utf-8")
            with self.assertRaises(ProvenanceError):
                load_forecast_config(bad)

    def test_pipeline_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            write_parquet(table(ar1(600)), tmp / "kc.parquet",
                          {"dataset_id": "k1", "pipeline": "clear_sky_index", "pipeline_version": "x",
                           "config_sha256": "c", "inputs_sha256": "i"})
            results, version = run_baseline_pipeline(kc_file=tmp / "kc.parquet", output_dir=tmp / "out")
            first = (tmp / "out" / "baseline_metrics.csv").read_bytes()
            run_baseline_pipeline(kc_file=tmp / "kc.parquet", output_dir=tmp / "out")
            self.assertEqual(first, (tmp / "out" / "baseline_metrics.csv").read_bytes())
            self.assertEqual(version["derived_from"], {"pipeline": "clear_sky_index", "dataset_id": "k1"})
            self.assertEqual(len(results), 12 * 6)        # 12 horizons x (3 references + 3 window means)


if __name__ == "__main__":
    unittest.main()
