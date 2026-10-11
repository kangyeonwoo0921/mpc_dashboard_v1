"""Outside data contract (config/outside_data.yaml) and site location (config/greenhouse.yaml)."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from ..config_loader import CONFIG_DIR, load_config_file
from ..paths import data_dir_overridden, processed_dir
from ..provenance import Parameter, ProvenanceError, parse_parameters

MPC_LAB_DIR = CONFIG_DIR.parent
VARIABLES = ("ghi", "t_out", "rh_out", "wind_speed", "wind_dir", "solar_energy_cumulative")
AGGREGATIONS = frozenset({"mean", "circular_mean", "last"})
CONTRACT_FIELDS = ("raw_name", "unit", "dtype", "category", "aggregation_5min", "validity_rule",
                   "missing_policy", "source", "physics_name")


@dataclass(frozen=True)
class Site:
    latitude_deg: float
    longitude_deg: float
    elevation_m: float


@dataclass(frozen=True)
class OutsideConfig:
    raw_dir: Path
    output_dir: Path
    file_glob: str
    encoding: str
    timestamp_format: str
    timezone: ZoneInfo
    layouts: dict            # name -> tuple of canonical field names
    known_headers: tuple
    variables: dict          # canonical name -> contract dict
    qc: dict                 # parsed provenance tree
    site: Site | None        # None -> daylight checks unresolved and skipped

    def qc_value(self, *path):
        node = self.qc
        for key in path:
            node = node[key]
        if not isinstance(node, Parameter):
            raise ProvenanceError(f"qc.{'.'.join(path)} is not a parameter record")
        return node.value

    def unresolved(self):
        """Paths of QC parameters without a value (rules switched off)."""
        out = []

        def walk(node, path):
            if isinstance(node, Parameter):
                if node.value is None:
                    out.append(path)
            elif isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{path}.{key}" if path else key)
        walk(self.qc, "qc")
        return sorted(out)


def config_fingerprint(config):
    """sha256 of everything in the config that can change the processed data.

    Uses the effective (loaded) values, so in-memory overrides are captured; file locations
    (raw_dir, output_dir) are excluded so the same data processed elsewhere keeps its identity."""
    def plain(node):
        if isinstance(node, Parameter):
            return {"value": node.value, "status": node.status}
        if isinstance(node, dict):
            return {key: plain(value) for key, value in node.items()}
        return node
    content = {"file_glob": config.file_glob, "encoding": config.encoding,
               "timestamp_format": config.timestamp_format, "timezone": str(config.timezone),
               "layouts": {k: list(v) for k, v in config.layouts.items()},
               "known_headers": [list(h) for h in config.known_headers],
               "variables": config.variables, "qc": plain(config.qc),
               "site": None if config.site is None else vars(config.site)}
    text = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _site(greenhouse_tree):
    site = greenhouse_tree.get("site", {})
    try:
        values = [site[key].value for key in ("latitude", "longitude", "elevation")]
    except KeyError:
        return None
    return None if any(v is None for v in values) else Site(*map(float, values))


def load_outside_config(path=None, config_dir=CONFIG_DIR, base_dir=MPC_LAB_DIR):
    path = Path(path) if path else Path(config_dir) / "outside_data.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    variables = raw["variables"]
    if set(variables) != set(VARIABLES):
        raise ProvenanceError(f"outside_data.yaml variables must be exactly {VARIABLES}")
    for name, spec in variables.items():
        missing = set(CONTRACT_FIELDS) - set(spec)
        if missing:
            raise ProvenanceError(f"variables.{name}: missing contract fields {sorted(missing)}")
        if spec["aggregation_5min"] not in AGGREGATIONS:
            raise ProvenanceError(f"variables.{name}.aggregation_5min must be one of {sorted(AGGREGATIONS)}")
    layouts = {name: tuple(fields) for name, fields in raw["layouts"].items()}
    for name, fields in layouts.items():
        if fields[0] != "timestamp" or "wind_dir" not in fields or not set(fields[1:]) <= set(VARIABLES):
            raise ProvenanceError(f"layouts.{name}: must start with timestamp, contain wind_dir and use canonical names")
    source = raw["source"]
    base = Path(base_dir)
    return OutsideConfig(
        raw_dir=base / source["raw_dir"],
        output_dir=(processed_dir() / Path(source["output_dir"]).name if data_dir_overridden()
                    else base / source["output_dir"]),
        file_glob=source["file_glob"], encoding=source["encoding"],
        timestamp_format=source["timestamp_format"], timezone=ZoneInfo(source["timezone"]),
        layouts=layouts, known_headers=tuple(tuple(h) for h in raw.get("known_headers", [])),
        variables=variables, qc=parse_parameters(raw["qc"], "qc"),
        site=_site(load_config_file("greenhouse", config_dir)),
    )
