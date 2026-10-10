"""Clear-sky index kc = GHI / GHI_clear — exclusion rules, no cap, pipeline versioning."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from greenhouse_mpc.ingestion.versioning import read_parquet_version, write_parquet
from greenhouse_mpc.provenance import ProvenanceError
from greenhouse_mpc.solar.clearsky import clearsky_five_minute, load_clearsky_config
from greenhouse_mpc.solar.clearsky_index import clear_sky_index
from greenhouse_mpc.solar.clearsky_index_pipeline import run_clearsky_index_pipeline

CONFIG = load_clearsky_config()
KST = "Asia/Seoul"
CONFIG_TEXT = (Path(__file__).resolve().parents[1] / "config" / "solar_reference.yaml").read_text(encoding="utf-8")


def tables(ghi, status, elevation, clear):
    times = pd.date_range("2026-09-07 06:00", periods=len(ghi), freq="5min", tz=KST)
    outside = pd.DataFrame({"timestamp": times, "ghi": ghi, "ghi_status": status,
                            "ghi_input": ghi, "ghi_input_status": status})
    clearsky = pd.DataFrame({"timestamp": times, "ghi_clear": clear, "sun_elevation_deg": elevation,
                             "sun_azimuth_deg": np.full(len(ghi), 180.0)})
    return outside, clearsky


class ClearSkyIndexTests(unittest.TestCase):
    def test_config_decisions(self):
        self.assertEqual(CONFIG.value("clear_sky_index.min_sun_elevation_deg"), 20.0)
        self.assertEqual(CONFIG.value("clear_sky_index.upper_bound"), "none")
        self.assertEqual(CONFIG.value("clear_sky_index.ghi_statuses"), ["observed"])

    def test_unsupported_cap_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "solar_reference.yaml"
            bad.write_text(CONFIG_TEXT.replace("value: none", "value: 1.5"), encoding="utf-8")
            with self.assertRaises(ProvenanceError):
                load_clearsky_config(bad)

    def test_kc_definition_and_exclusions(self):
        outside, clearsky = tables(
            ghi=[0.0, 50.0, 400.0, 900.0, 300.0, 300.0],
            status=["invalid", "observed", "observed", "observed", "interpolated", "observed"],
            elevation=[-5.0, 15.0, 40.0, 50.0, 40.0, 20.0],
            clear=[0.0, 150.0, 500.0, 600.0, 500.0, 300.0])
        frame = clear_sky_index(outside, clearsky, CONFIG)
        self.assertEqual(list(frame.kc_status), ["night", "low_sun", "valid", "valid", "ghi_not_observed", "valid"])
        np.testing.assert_allclose(frame.kc, [np.nan, np.nan, 0.8, 1.5, np.nan, 1.0])   # 1.5 kept: no cap

    def test_input_kc_uses_causal_status(self):
        outside, clearsky = tables([400.0, 400.0], ["suspect", "observed"], [40.0, 40.0], [500.0, 500.0])
        outside["ghi_input_status"] = ["observed", "observed"]           # freeze not yet known at issue time
        frame = clear_sky_index(outside, clearsky, CONFIG)
        self.assertEqual(list(frame.kc_status), ["ghi_not_observed", "valid"])
        self.assertEqual(list(frame.kc_input_status), ["valid", "valid"])

    def test_grid_mismatch_rejected(self):
        outside, clearsky = tables([1.0, 2.0], ["observed"] * 2, [30.0, 30.0], [100.0, 100.0])
        with self.assertRaises(ValueError):
            clear_sky_index(outside, clearsky.iloc[::-1], CONFIG)

    def test_index_settings_do_not_change_clearsky_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "solar_reference.yaml"
            other.write_text(CONFIG_TEXT.replace("value: 20.0", "value: 10.0"), encoding="utf-8")
            changed = load_clearsky_config(other)
        self.assertEqual(changed.fingerprint(), CONFIG.fingerprint())
        self.assertNotEqual(changed.fingerprint(include_index=True), CONFIG.fingerprint(include_index=True))


class ClearSkyIndexPipelineTests(unittest.TestCase):
    def test_pipeline_outputs_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            times = pd.date_range("2026-09-07 05:00", periods=48, freq="5min", tz=KST)
            clearsky = clearsky_five_minute(times, CONFIG)
            outside = pd.DataFrame({"timestamp": times, "ghi": clearsky.ghi_clear * 0.9, "ghi_status": "observed",
                                    "ghi_input": clearsky.ghi_clear * 0.9, "ghi_input_status": "observed"})
            (tmp / "outside").mkdir()
            (tmp / "clearsky").mkdir()
            write_parquet(outside, tmp / "outside" / "outside_5min.parquet",
                          {"dataset_id": "o1", "pipeline": "outside", "pipeline_version": "x", "config_sha256": "c", "inputs_sha256": "i"})
            write_parquet(clearsky, tmp / "clearsky" / "clearsky_5min.parquet",
                          {"dataset_id": "c1", "pipeline": "clearsky", "pipeline_version": "x", "config_sha256": "c", "inputs_sha256": "i"})
            args = dict(outside_file=tmp / "outside" / "outside_5min.parquet",
                        clearsky_file=tmp / "clearsky" / "clearsky_5min.parquet", output_dir=tmp / "kc")
            frame, version, summary = run_clearsky_index_pipeline(CONFIG, **args)
            first = {p.name: p.read_bytes() for p in (tmp / "kc").iterdir()}
            run_clearsky_index_pipeline(CONFIG, **args)
            self.assertEqual(first, {p.name: p.read_bytes() for p in (tmp / "kc").iterdir()})     # deterministic
            self.assertEqual(version["derived_from"], [{"pipeline": "outside", "dataset_id": "o1"},
                                                       {"pipeline": "clearsky", "dataset_id": "c1"}])
            self.assertEqual(read_parquet_version(tmp / "kc" / "kc_5min.parquet")["dataset_id"], version["dataset_id"])
            valid = frame[frame.kc_status == "valid"]
            self.assertTrue((valid.sun_elevation_deg >= 20).all() and len(valid) > 0)
            np.testing.assert_allclose(valid.kc, 0.9)
            manifest = json.loads((tmp / "kc" / "dataset_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["summary"]["kc_status_counts"]["valid"], len(valid))


if __name__ == "__main__":
    unittest.main()
