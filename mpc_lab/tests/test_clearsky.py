"""Clear-sky reference (Ineichen-Perez via pvlib) — config, physics sanity and pipeline."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

from greenhouse_mpc.ingestion.versioning import read_parquet_version, write_parquet
from greenhouse_mpc.provenance import ProvenanceError
from greenhouse_mpc.solar.clearsky import (clearsky_at, clearsky_five_minute, clearsky_minute,
                                           load_clearsky_config)
from greenhouse_mpc.solar.clearsky_pipeline import run_clearsky_pipeline

CONFIG = load_clearsky_config()
KST = "Asia/Seoul"
CONFIG_TEXT = (Path(__file__).resolve().parents[1] / "config" / "solar_reference.yaml").read_text(encoding="utf-8")


class ClearSkyConfigTests(unittest.TestCase):
    def test_literature_choices_recorded(self):
        for dotted, author in (("clear_sky_model", "Ineichen & Perez (2002)"), ("linke_turbidity", "Remund et al. (2003)"),
                               ("airmass_model", "Kasten & Young (1989)"), ("solar_position", "Reda & Andreas (2004)")):
            node = CONFIG.tree[dotted]
            self.assertIn(author, node.source_id)
            self.assertEqual(node.status, "literature_baseline")
        self.assertFalse(CONFIG.value("perez_enhancement"))

    def test_unsupported_choice_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "solar_reference.yaml"
            bad.write_text(CONFIG_TEXT.replace("value: kastenyoung1989", "value: simple"), encoding="utf-8")
            with self.assertRaises(ProvenanceError):
                load_clearsky_config(bad)

    def test_fingerprint_tracks_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "solar_reference.yaml"
            other.write_text(CONFIG_TEXT.replace("value: 1366.1", "value: 1361.0"), encoding="utf-8")
            self.assertNotEqual(load_clearsky_config(other).fingerprint(), CONFIG.fingerprint())
        self.assertEqual(load_clearsky_config().fingerprint(), CONFIG.fingerprint())


class ClearSkyPhysicsTests(unittest.TestCase):
    def times(self, start, periods, freq="1min"):
        return pd.date_range(start, periods=periods, freq=freq, tz=KST)

    def test_matches_standard_pvlib_chain(self):
        t = self.times("2026-08-05 05:00", 900)
        ours = clearsky_at(t, CONFIG)
        ref = pvlib.location.Location(35.837, 126.709, KST, 3.0).get_clearsky(t, model="ineichen")
        for column in ("ghi", "dni", "dhi"):
            np.testing.assert_allclose(ours[f"{column}_clear"], ref[column], atol=1e-9)

    def test_night_zero_day_positive_and_closure(self):
        frame = clearsky_at(self.times("2026-10-08 00:00", 1440), CONFIG)
        night = frame[frame.sun_elevation_deg < -1]
        self.assertTrue((night[["ghi_clear", "dni_clear", "dhi_clear"]] == 0).all().all())
        day = frame[frame.sun_elevation_deg > 5]
        self.assertTrue((day.ghi_clear > 0).all())
        closure = day.dni_clear * np.cos(np.deg2rad(day.sun_zenith_apparent_deg)) + day.dhi_clear
        np.testing.assert_allclose(closure, day.ghi_clear, rtol=1e-6)
        self.assertLess(day.ghi_clear.max(), day.dni_extra_w_m2.max())

    def test_intermediates(self):
        frame = clearsky_at(self.times("2026-08-05 12:00", 60), CONFIG)
        np.testing.assert_allclose(frame.airmass_absolute, frame.airmass_relative * frame.pressure_pa / 101325.0, rtol=1e-9)
        self.assertTrue(frame.linke_turbidity.between(1.5, 8.0).all())          # climatology range sanity
        self.assertTrue(frame.dni_extra_w_m2.between(1300, 1420).all())

    def test_minute_and_five_minute_aggregation(self):
        starts = self.times("2026-09-07 06:00", 24, "5min")
        five = clearsky_five_minute(starts, CONFIG).set_index("timestamp")
        minute = clearsky_minute(self.times("2026-09-07 06:00", 120), CONFIG).set_index("timestamp")
        expected = minute.ghi_clear.resample("5min").mean()
        np.testing.assert_allclose(five.ghi_clear, expected.reindex(five.index), atol=1e-9)
        centre = clearsky_at(starts + pd.Timedelta(seconds=150), CONFIG)
        np.testing.assert_allclose(five.sun_elevation_deg, centre.sun_elevation_deg)

    def test_naive_times_rejected(self):
        with self.assertRaises(ValueError):
            clearsky_at(pd.date_range("2026-08-05", periods=3, freq="1min"), CONFIG)


class ClearSkyPipelineTests(unittest.TestCase):
    def test_pipeline_outputs_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside, out = Path(tmp) / "outside", Path(tmp) / "clearsky"
            outside.mkdir()
            source = {"dataset_id": "abc123", "pipeline": "outside", "pipeline_version": "x",
                      "config_sha256": "c", "inputs_sha256": "i"}
            minute = pd.DataFrame({"timestamp": pd.date_range("2026-09-07 06:00", periods=30, freq="1min", tz=KST)})
            five = pd.DataFrame({"timestamp": pd.date_range("2026-09-07 06:00", periods=6, freq="5min", tz=KST)})
            write_parquet(minute, outside / "outside_1min.parquet", source)
            write_parquet(five, outside / "outside_5min.parquet", source)
            m1, f1, v1 = run_clearsky_pipeline(CONFIG, outside, out)
            first = {p.name: p.read_bytes() for p in out.iterdir()}
            run_clearsky_pipeline(CONFIG, outside, out)
            self.assertEqual(first, {p.name: p.read_bytes() for p in out.iterdir()})       # deterministic
            self.assertEqual(v1["derived_from"], {"pipeline": "outside", "dataset_id": "abc123"})
            self.assertEqual(read_parquet_version(out / "clearsky_5min.parquet")["dataset_id"], v1["dataset_id"])
            manifest = json.loads((out / "dataset_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["pipeline"], "clearsky")
            self.assertEqual((len(m1), len(f1)), (30, 6))
            self.assertTrue((f1.timestamp.to_numpy() == five.timestamp.to_numpy()).all())  # same join key


if __name__ == "__main__":
    unittest.main()
