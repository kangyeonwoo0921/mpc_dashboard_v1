"""Step 1A outside ingestion: fixtures reproduce the edge cases seen in the real exports."""

import copy
import dataclasses
import math
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from greenhouse_mpc.ingestion.outside_pipeline import preprocess, run_outside_pipeline
from greenhouse_mpc.ingestion.outside_reader import parse_row, read_outside_exports
from greenhouse_mpc.ingestion.outside_schema import VARIABLES, load_outside_config
from greenhouse_mpc.ingestion.qc import QC
from greenhouse_mpc.ingestion.resample import circular_mean_deg
from greenhouse_mpc.provenance import Parameter, ProvenanceError

HEADER7 = "시각,누적일사량,외부습도,외부온도,외부풍속,외부풍향,일사센서"
HEADER6 = "시각,누적일사량,외부온도,외부풍속,외부풍향,일사센서"
BASE = load_outside_config()


def row6(ts, ghi=500.0, t=25.0, ws=0.4, wd="90° 동", cum=100.0, trailing=False):
    return f"{ts},{cum},{t},{ws},{wd},{ghi}" + ("," if trailing else "")


def row7(ts, rh=60.0, ghi=500.0, t=25.0, ws=0.4, wd="90° 동", cum=100.0):
    return f"{ts},{cum},{rh},{t},{ws},{wd},{ghi}"


class Fixture:
    """Temporary raw folder with given exports; returns (config, result)."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "raw"
        self.raw.mkdir()
        self.config = dataclasses.replace(BASE, raw_dir=self.raw, output_dir=Path(self.tmp.name) / "out")

    def file(self, name, header, rows):
        (self.raw / name).write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
        return self

    def run(self, config=None, write=False):
        return run_outside_pipeline(config or self.config, write=write)

    def close(self):
        self.tmp.cleanup()


def minutes(start, n, step_s=60, offset_s=45):
    t0 = pd.Timestamp(start) + timedelta(seconds=offset_s)
    return [(t0 + timedelta(seconds=step_s * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)]


def with_qc(config, path, value, status="provisional"):
    qc = copy.deepcopy(config.qc)
    node = qc
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = dataclasses.replace(node[path[-1]], value=value, status=status, source_type="temporary_test_fixture")
    return dataclasses.replace(config, qc=qc)


class OutsideIngestionTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    def obs_at(self, result, ts):
        o = result.observations
        return o[o["timestamp"] == pd.Timestamp(ts, tz="Asia/Seoul")].iloc[0]

    # 1
    def test_timestamp_parsing_and_timezone(self):
        record = parse_row(row6("2026-08-05 12:00:45").split(","), BASE.layouts, BASE.timestamp_format, BASE.timezone)
        self.assertEqual(record["timestamp"].utcoffset(), timedelta(hours=9))
        self.assertEqual(str(record["timestamp"].tzinfo), "Asia/Seoul")
        bad = parse_row(row6("2026/08/05 12:00").split(","), BASE.layouts, BASE.timestamp_format, BASE.timezone)
        self.assertFalse(bad["timestamp_ok"])

    # 2
    def test_overlapping_exports_merge(self):
        rows = [row6(t) for t in minutes("2026-08-05 12:00", 10)]
        single = Fixture().file("outside_a.csv", HEADER6, rows)
        try:
            alone = single.run()
        finally:
            single.close()
        self.fx.file("outside_a.csv", HEADER6, rows[:7]).file("outside_b.csv", HEADER6, rows[4:])
        merged = self.fx.run()
        self.assertEqual(len(merged.observations), 10)
        self.assertEqual(merged.summary["duplicate_count"], 3)
        flag_columns = [f"{name}_flags" for name in VARIABLES]
        pd.testing.assert_frame_equal(merged.five_min.drop(columns=["n_rows", *flag_columns]),
                                      alone.five_min.drop(columns=["n_rows", *flag_columns]))
        for column in flag_columns:                                    # only the merge marker differs
            self.assertTrue(((merged.five_min[column] & ~int(QC.DUPLICATE)) == alone.five_min[column]).all())

    # 3
    def test_exact_duplicate(self):
        ts = minutes("2026-08-05 12:00", 1)[0]
        result = self.fx.file("outside_a.csv", HEADER6, [row6(ts), row6(ts)]).run()
        self.assertEqual(list(result.parsed["dedup_status"]), ["kept", "duplicate"])
        obs = self.obs_at(result, ts)
        self.assertTrue(obs["ghi_flags"] & QC.DUPLICATE)
        self.assertEqual(obs["ghi_status"], "observed")

    # 4
    def test_conflicting_duplicate(self):
        ts = minutes("2026-08-05 12:00", 1)[0]
        result = self.fx.file("outside_a.csv", HEADER6, [row6(ts, ghi=500), row6(ts, ghi=510)]).run()
        self.assertEqual(set(result.parsed["dedup_status"]), {"conflicting"})
        obs = self.obs_at(result, ts)
        self.assertTrue(math.isnan(obs["ghi"]))
        self.assertTrue(obs["ghi_flags"] & QC.CONFLICTING_DUPLICATE)
        self.assertEqual(obs["ghi_status"], "missing")

    # 5
    def test_schema_drift_under_one_header(self):
        ts = minutes("2026-08-05 12:00", 4)
        result = self.fx.file("outside_a.csv", HEADER7, [
            row7(ts[0], rh=55),
            row6(ts[1]),                                  # humidity dropped, same header
            row6(ts[2], trailing=True),                   # extra empty trailing field
            row6(ts[3]) + ",0.0",                         # extra value: ambiguous
        ]).run()
        p = result.parsed.set_index("raw_timestamp")
        self.assertEqual(p.loc[ts[0], "layout"], "with_rh")
        self.assertEqual(p.loc[ts[1], "layout"], "without_rh")
        self.assertEqual((p.loc[ts[2], "layout"], p.loc[ts[2], "schema_status"]), ("without_rh", "trailing_empty_removed"))
        self.assertEqual(p.loc[ts[3], "schema_status"], "anomaly")
        self.assertTrue(pd.isna(p.loc[ts[3], "ghi"]))
        self.assertEqual(self.obs_at(result, ts[0])["rh_out"], 55)
        self.assertTrue(math.isnan(self.obs_at(result, ts[1])["rh_out"]))
        self.assertTrue(self.obs_at(result, ts[3])["ghi_flags"] & QC.SCHEMA_ANOMALY)

    # 6
    def test_night_ghi_zero_is_valid(self):
        ts = minutes("2026-08-05 23:00", 1)[0]
        obs = self.obs_at(self.fx.file("outside_a.csv", HEADER6, [row6(ts, ghi=0.0)]).run(), ts)
        self.assertEqual((obs["ghi_status"], int(obs["ghi_flags"])), ("observed", 0))

    # 7
    def test_daylight_zero_and_all_zero_pattern(self):
        ts = minutes("2026-08-05 12:00", 2)
        result = self.fx.file("outside_a.csv", HEADER6, [
            row6(ts[0], ghi=0.0, t=28.0),                                # GHI dropout only
            row6(ts[1], ghi=0.0, t=0.0, ws=0.0, wd="0° 북", cum=30.0),   # communication pattern
        ]).run()
        dropout = self.obs_at(result, ts[0])
        self.assertEqual(dropout["ghi_status"], "suspect")
        self.assertTrue(dropout["ghi_flags"] & QC.SUSPICIOUS_ZERO)
        self.assertEqual(dropout["ghi"], 0.0)                            # flagged, not overwritten
        comm = self.obs_at(result, ts[1])
        for name in ("ghi", "t_out", "wind_speed", "wind_dir"):
            self.assertEqual(comm[f"{name}_status"], "invalid")
            self.assertTrue(comm[f"{name}_flags"] & QC.SUSPECTED_COMMUNICATION_ERROR)
            self.assertTrue(math.isnan(comm[name]))
        self.assertEqual(comm["ghi_raw"], "0.0")                        # raw kept

    # 8
    def test_sensor_freeze_detection(self):
        long_run = [row6(t, ghi=564.0) for t in minutes("2026-08-05 11:00", 70)]
        short_run = [row6(t, ghi=400.0) for t in minutes("2026-08-05 13:00", 30)]
        night = [row6(t, ghi=564.0) for t in minutes("2026-08-05 23:00", 3)]
        result = self.fx.file("outside_a.csv", HEADER6, long_run + short_run + night).run()
        o = result.observations.set_index("timestamp")
        noon = o.loc[pd.Timestamp("2026-08-05 11:30:45", tz="Asia/Seoul")]
        self.assertTrue(noon["ghi_flags"] & QC.SENSOR_FREEZE)
        self.assertEqual((noon["ghi_status"], noon["ghi"]), ("suspect", 564.0))
        short = o.loc[pd.Timestamp("2026-08-05 13:10:45", tz="Asia/Seoul")]
        self.assertEqual(int(short["ghi_flags"]), 0)
        dark = o.loc[pd.Timestamp("2026-08-05 23:01:45", tz="Asia/Seoul")]
        self.assertTrue(dark["ghi_flags"] & QC.OUT_OF_RANGE)            # GHI > 0 at night
        self.assertEqual(dark["ghi_status"], "invalid")

    def test_causal_input_status_does_not_look_ahead(self):
        run = [row6(t, ghi=564.0) for t in minutes("2026-08-05 11:00", 70)]     # 11:00:45 .. 12:09:45
        result = self.fx.file("outside_a.csv", HEADER6, run).run()
        o = result.observations.set_index("timestamp")
        early = o.loc[pd.Timestamp("2026-08-05 11:30:45", tz="Asia/Seoul")]
        late = o.loc[pd.Timestamp("2026-08-05 12:05:45", tz="Asia/Seoul")]
        self.assertEqual((early["ghi_status"], early["ghi_input_status"]), ("suspect", "observed"))  # run not yet 60 min
        self.assertEqual((late["ghi_status"], late["ghi_input_status"]), ("suspect", "suspect"))
        # causal status of a row never changes when later rows are removed
        truncated = Fixture().file("outside_a.csv", HEADER6, run[:31])
        try:
            cut = truncated.run().observations.set_index("timestamp")
        finally:
            truncated.close()
        pd.testing.assert_series_equal(cut["ghi_input_status"], o["ghi_input_status"].loc[cut.index])
        five = result.five_min.set_index("timestamp")
        bin_early = five.loc[pd.Timestamp("2026-08-05 11:30", tz="Asia/Seoul")]
        self.assertEqual((bin_early["ghi_status"], bin_early["ghi_input_status"]), ("suspect", "observed"))
        self.assertEqual(bin_early["ghi_input"], 564.0)

    def test_input_columns_never_use_interpolation(self):
        times = minutes("2026-08-05 12:00", 2) + minutes("2026-08-05 12:04", 2)
        rows = [row6(t, t=20.0 + i) for i, t in enumerate(times)]
        config = with_qc(self.fx.config, ("interpolation_max_gap_minutes", "t_out"), 3)
        m = self.fx.file("outside_a.csv", HEADER6, rows).run(config).minute.set_index("timestamp")
        filled = m.loc[pd.Timestamp("2026-08-05 12:02", tz="Asia/Seoul")]
        self.assertEqual((filled["t_out_status"], filled["t_out_input_status"]), ("interpolated", "missing"))
        self.assertTrue(math.isnan(filled["t_out_input"]))

    # 9
    def test_missing_is_preserved_not_filled(self):
        times = minutes("2026-08-05 12:00", 3) + minutes("2026-08-05 12:10", 3)
        result = self.fx.file("outside_a.csv", HEADER6, [row6(t) for t in times]).run()
        m = result.minute.set_index("timestamp")
        gap = m.loc[pd.Timestamp("2026-08-05 12:05", tz="Asia/Seoul")]
        self.assertEqual((gap["ghi_status"], gap["n_rows"]), ("missing", 0))
        self.assertTrue(math.isnan(gap["ghi"]))
        self.assertTrue(gap["ghi_flags"] & QC.MISSING)
        self.assertTrue((m["rh_out_status"] == "missing").all())        # absent variable stays missing
        self.assertFalse((m["ghi_status"] == "interpolated").any())

    def test_optional_interpolation_is_marked(self):
        times = minutes("2026-08-05 12:00", 2) + minutes("2026-08-05 12:04", 2)
        rows = [row6(t, t=20.0 + i) for i, t in enumerate(times)]
        config = with_qc(self.fx.config, ("interpolation_max_gap_minutes", "t_out"), 3)
        m = self.fx.file("outside_a.csv", HEADER6, rows).run(config).minute.set_index("timestamp")
        filled = m.loc[pd.Timestamp("2026-08-05 12:02", tz="Asia/Seoul")]
        self.assertEqual(filled["t_out_status"], "interpolated")
        self.assertTrue(filled["t_out_flags"] & QC.INTERPOLATED)
        self.assertEqual(filled["ghi_status"], "missing")              # GHI interpolation stays off

    # 10
    def test_five_minute_resampling_by_timestamp(self):
        times = minutes("2026-08-05 12:00", 10, offset_s=45)          # 12:00:45 .. 12:09:45
        rows = [row6(t, ghi=100.0 * (i + 1), cum=10.0 * i) for i, t in enumerate(times)]
        five = self.fx.file("outside_a.csv", HEADER6, rows).run().five_min.set_index("timestamp")
        first = five.loc[pd.Timestamp("2026-08-05 12:00", tz="Asia/Seoul")]
        self.assertAlmostEqual(first["ghi"], np.mean([100, 200, 300, 400, 500]))
        self.assertEqual(first["solar_energy_cumulative"], 40.0)        # last, not mean
        self.assertEqual((first["ghi_n_obs"], first["ghi_coverage"]), (5, 1.0))
        second = five.loc[pd.Timestamp("2026-08-05 12:05", tz="Asia/Seoul")]
        self.assertAlmostEqual(second["ghi"], np.mean([600, 700, 800, 900, 1000]))

    def test_five_minute_coverage_with_gaps(self):
        rows = [row6(t) for t in minutes("2026-08-05 12:00", 2)]
        five = self.fx.file("outside_a.csv", HEADER6, rows).run().five_min
        self.assertEqual(five.iloc[0]["ghi_coverage"], 0.4)

    # 11
    def test_wind_direction_circular_mean(self):
        mean, r = circular_mean_deg([350.0, 10.0])
        self.assertAlmostEqual(mean % 360, 0.0, places=6)
        self.assertGreater(r, 0.98)
        rows = [row6(t, wd=w) for t, w in zip(minutes("2026-08-05 12:00", 4), ["337° 북북서", "22° 북북동", "337° 북북서", "22° 북북동"])]
        five = self.fx.file("outside_a.csv", HEADER6, rows).run().five_min
        self.assertTrue(five.iloc[0]["wind_dir"] < 1 or five.iloc[0]["wind_dir"] > 359)   # not 179.5

    # 12
    def test_idempotent_outputs(self):
        self.fx.file("outside_a.csv", HEADER6, [row6(t) for t in minutes("2026-08-05 12:00", 12)])
        self.fx.run(write=True)
        first = {p.name: p.read_bytes() for p in self.fx.config.output_dir.iterdir()}
        self.fx.run(write=True)
        second = {p.name: p.read_bytes() for p in self.fx.config.output_dir.iterdir()}
        self.assertEqual(first, second)
        raw = (self.fx.raw / "outside_a.csv").read_text(encoding="utf-8")
        self.assertTrue(raw.startswith(HEADER6))                       # raw untouched

    # 13
    def test_malformed_rows(self):
        ts = minutes("2026-08-05 12:00", 2)
        text = "\n".join([HEADER6, row6(ts[0], t="abc"), "", "not a timestamp,1,2,3,0° 북,4", row6(ts[1])]) + "\n"
        (self.fx.raw / "outside_a.csv").write_text(text, encoding="utf-8")
        result = self.fx.run()
        obs = self.obs_at(result, ts[0])
        self.assertTrue(obs["t_out_flags"] & QC.SCHEMA_ANOMALY)
        self.assertEqual(obs["t_out_status"], "missing")
        self.assertEqual(obs["ghi_status"], "observed")
        self.assertEqual(result.summary["unplaced_rows_bad_timestamp"], 1)
        self.assertEqual(result.summary["raw_row_count"], 3)            # blank line skipped

    # 14
    def test_canonical_schema_validation(self):
        self.assertEqual(set(BASE.variables), set(VARIABLES))
        for name, spec in BASE.variables.items():
            self.assertIn(spec["category"], ("disturbance", "disturbance_auxiliary"))
        self.assertIsNone(BASE.variables["wind_speed"]["unit"])         # unresolved, not assumed
        self.assertNotEqual(BASE.variables["ghi"]["raw_name"], BASE.variables["solar_energy_cumulative"]["raw_name"])
        bad = Path(self.fx.tmp.name) / "bad.yaml"
        text = (Path(__file__).resolve().parents[1] / "config" / "outside_data.yaml").read_text(encoding="utf-8")
        bad.write_text(text.replace("aggregation_5min: circular_mean", "aggregation_5min: arithmetic_mean"), encoding="utf-8")
        with self.assertRaises(ProvenanceError):
            load_outside_config(bad)
        ts = minutes("2026-08-05 12:00", 1)[0]
        obs = self.obs_at(self.fx.file("outside_a.csv", HEADER7, [row7(ts, rh=110.0)]).run(), ts)
        self.assertEqual(obs["rh_out_status"], "invalid")
        self.assertTrue(obs["rh_out_flags"] & QC.OUT_OF_RANGE)

    def test_output_columns_are_stable(self):
        result = self.fx.file("outside_a.csv", HEADER6, [row6(t) for t in minutes("2026-08-05 12:00", 3)]).run()
        for name in VARIABLES:
            for suffix in ("", "_status", "_flags", "_n_obs", "_n_interp", "_coverage"):
                self.assertIn(f"{name}{suffix}", result.five_min.columns)
        self.assertIn("wind_dir_r", result.five_min.columns)
        self.assertIn("sun_elevation_deg", result.five_min.columns)


class DatasetVersionTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.fx.file("outside_a.csv", HEADER6, [row6(t) for t in minutes("2026-08-05 12:00", 12)])

    def tearDown(self):
        self.fx.close()

    def test_manifest_and_embedded_version(self):
        import json
        from greenhouse_mpc.ingestion.versioning import file_sha256, read_parquet_version
        result = self.fx.run(write=True)
        out = self.fx.config.output_dir
        manifest = json.loads((out / "dataset_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["dataset_id"], result.version["dataset_id"])
        self.assertEqual(result.summary["dataset_version"]["dataset_id"], manifest["dataset_id"])
        self.assertEqual([i["file"] for i in manifest["inputs"]], ["outside_a.csv"])
        for name, digest in manifest["outputs"].items():                # manifest matches the files
            self.assertEqual(file_sha256(out / name), digest)
        for name in ("parsed_rows.parquet", "outside_1min.parquet", "outside_5min.parquet"):
            self.assertEqual(read_parquet_version(out / name)["dataset_id"], manifest["dataset_id"])
        self.assertIn("libraries", manifest["provenance"])

    def test_id_depends_on_inputs_config_and_version_only(self):
        first = self.fx.run().version
        again = self.fx.run().version
        self.assertEqual(first["dataset_id"], again["dataset_id"])
        moved = Fixture()                                               # same content, other folder
        try:
            moved.file("outside_a.csv", HEADER6, [row6(t) for t in minutes("2026-08-05 12:00", 12)])
            self.assertEqual(moved.run().version["dataset_id"], first["dataset_id"])
        finally:
            moved.close()
        changed_rule = self.fx.run(with_qc(self.fx.config, ("freeze_min_duration_minutes", "ghi"), 90)).version
        self.assertNotEqual(changed_rule["config_sha256"], first["config_sha256"])
        self.assertNotEqual(changed_rule["dataset_id"], first["dataset_id"])
        self.fx.file("outside_b.csv", HEADER6, [row6(t) for t in minutes("2026-08-05 13:00", 3)])
        added = self.fx.run().version
        self.assertNotEqual(added["inputs_sha256"], first["inputs_sha256"])
        self.assertNotEqual(added["dataset_id"], first["dataset_id"])

    def test_reproduce_version_from_listed_inputs(self):
        first = self.fx.run().version
        self.fx.file("outside_b.csv", HEADER6, [row6(t) for t in minutes("2026-08-05 13:00", 3)])
        listed = [self.fx.raw / i["file"] for i in first["inputs"]]
        reproduced = run_outside_pipeline(self.fx.config, paths=listed, write=False).version
        self.assertEqual(reproduced["dataset_id"], first["dataset_id"])


@unittest.skipUnless(any(BASE.raw_dir.glob(BASE.file_glob)), "real outside exports not present")
class RealExportSmokeTest(unittest.TestCase):
    def test_real_exports(self):
        result = run_outside_pipeline(write=False)
        s = result.summary
        self.assertEqual(s["raw_row_count"], s["parsed_row_count"] + s["schema_anomaly_count"])
        self.assertTrue(result.minute["timestamp"].is_monotonic_increasing)
        self.assertTrue(result.five_min["timestamp"].is_monotonic_increasing)
        self.assertEqual(len(result.five_min), len(result.minute["timestamp"].dt.floor("5min").unique()))
        self.assertTrue(result.minute["timestamp"].diff().dropna().eq(pd.Timedelta(minutes=1)).all())


if __name__ == "__main__":
    unittest.main()
