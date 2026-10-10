"""config/ghi_forecast.yaml with provenance records."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from ..config_loader import CONFIG_DIR
from ..provenance import Parameter, ProvenanceError, parse_parameters

REFERENCES = ("persistence", "climatology", "convex_combination")
SUN_GEOMETRY = ("sun_elevation_issue", "sun_elevation_target", "sun_azimuth_target")
SPLIT_DATES = ("first_test_start", "development_end", "checkpoint_end", "final_end")


def _plain(node):
    if isinstance(node, Parameter):
        return {"value": node.value, "status": node.status}
    return {k: _plain(v) for k, v in node.items()} if isinstance(node, dict) else node


@dataclass(frozen=True)
class ForecastConfig:
    tree: dict

    def value(self, dotted):
        node = self.tree
        for key in dotted.split("."):
            node = node[key]
        if not isinstance(node, Parameter):
            raise ProvenanceError(f"{dotted} is not a parameter record")
        return node.value

    def section(self, dotted):
        node = self.tree
        for key in dotted.split("."):
            node = node[key]
        return {k: v.value for k, v in node.items()}

    def date(self, key):
        return pd.Timestamp(self.value(f"split.{key}")).date()

    def fingerprint(self, *sections):
        """sha256 over the whole config, or over the named top-level sections only."""
        tree = self.tree if not sections else {k: self.tree[k] for k in sections}
        return hashlib.sha256(json.dumps(_plain(tree), sort_keys=True).encode("utf-8")).hexdigest()


def load_forecast_config(path=None, config_dir=CONFIG_DIR):
    path = Path(path) if path else Path(config_dir) / "ghi_forecast.yaml"
    config = ForecastConfig(parse_parameters(yaml.safe_load(path.read_text(encoding="utf-8")), "ghi_forecast"))
    if config.value("time_step_min") != 5:
        raise ProvenanceError("only the 5-min kc table is implemented")
    steps = config.value("horizon_steps")
    if not steps or any(not isinstance(h, int) or h < 1 for h in steps):
        raise ProvenanceError("horizon_steps must be positive integers")
    if config.value("reference") not in REFERENCES:
        raise ProvenanceError(f"reference must be one of {REFERENCES}")
    if "split" in config.tree:
        dates = [config.date(k) for k in SPLIT_DATES]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ProvenanceError(f"split dates must increase: {SPLIT_DATES}")
        if config.value("split.scheme") != "expanding_weekly":
            raise ProvenanceError("only split.scheme = expanding_weekly is implemented")
    if "features" in config.tree:
        unknown = set(config.value("features.sun_geometry")) - set(SUN_GEOMETRY)
        if unknown:
            raise ProvenanceError(f"unknown sun_geometry features {sorted(unknown)}")
        if config.value("model.strategy") != "direct_per_horizon":
            raise ProvenanceError("only model.strategy = direct_per_horizon is implemented")
    return config
