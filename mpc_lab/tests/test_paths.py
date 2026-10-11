"""GREENHOUSE_DATA_DIR / GREENHOUSE_SHARED_DIR move generated data; defaults stay under mpc_lab/data."""

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from greenhouse_mpc import paths
from greenhouse_mpc.ingestion.outside_schema import load_outside_config

MPC_LAB = Path(__file__).resolve().parents[1]


class PathTests(unittest.TestCase):
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GREENHOUSE_DATA_DIR", None)
            os.environ.pop("GREENHOUSE_SHARED_DIR", None)
            self.assertEqual(paths.processed_dir(), MPC_LAB / "data" / "processed")
            self.assertIsNone(paths.shared_dir())
            self.assertEqual(load_outside_config().output_dir, MPC_LAB / "data" / "processed" / "outside")

    def test_overrides_move_outputs_but_not_raw_exports(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as shared:
            with patch.dict(os.environ, {"GREENHOUSE_DATA_DIR": data, "GREENHOUSE_SHARED_DIR": shared}):
                config = load_outside_config()
                self.assertEqual(config.output_dir, Path(data) / "processed" / "outside")
                self.assertEqual(config.raw_dir, MPC_LAB / "data" / "ouside_data")
                modules = {name: importlib.reload(importlib.import_module(f"greenhouse_mpc.{name}"))
                           for name in ("solar.clearsky_pipeline", "solar.clearsky_index_pipeline",
                                        "forecast.operation", "forecast.live_runner")}
                self.assertEqual(modules["solar.clearsky_pipeline"].OUTPUT_DIR, Path(data) / "processed" / "clearsky")
                self.assertEqual(modules["solar.clearsky_index_pipeline"].OUTPUT_DIR, Path(data) / "processed" / "clear_sky_index")
                ops = modules["forecast.operation"].OperationPaths.default()
                self.assertEqual(ops.models, Path(data) / "processed" / "forecast_models")
                self.assertEqual(ops.state, MPC_LAB / "records" / "forecast_operation_state.json")   # records stay
                self.assertEqual(modules["forecast.live_runner"].LATEST_FILE, Path(shared) / "latest_forecast.json")
        for name in ("solar.clearsky_pipeline", "solar.clearsky_index_pipeline", "forecast.operation", "forecast.live_runner"):
            importlib.reload(importlib.import_module(f"greenhouse_mpc.{name}"))          # restore defaults


if __name__ == "__main__":
    unittest.main()
