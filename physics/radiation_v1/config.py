"""Spec-shaped v1 configuration (greenhouse_ray_tracing_implementation_spec.md, section 15).

Values stay ``None`` when unknown; nothing is estimated here.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.config_loader import PROJECT_ROOT

CONFIG_DIR = PROJECT_ROOT / "config/radiation_v1"
PROVENANCE = {"measured", "manufacturer_spec", "drawing", "paper", "estimated", "temporary_test_fixture", "unknown"}


@dataclass(frozen=True)
class SiteConfig:
    latitude_deg: float | None
    longitude_deg: float | None
    elevation_m: float | None
    timezone: str
    greenhouse_long_axis_azimuth_deg: float | None
    source: str = "unknown"
    verified: bool = False
    provenance: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OpticalProperties:
    tau_direct: float | None
    tau_diffuse: float | None
    source: str = "unknown"
    provenance: str = "unknown"
    verified: bool = False


@dataclass(frozen=True)
class RadiationConfig:
    grid_resolution_m: float
    crop_reference_height_m: float | None
    crop_reference_height_provenance: str = "unknown"


def _read(name, directory):
    return json.loads((Path(directory) / name).read_text(encoding="utf-8"))


def _fraction(value, path):
    if value is not None and not (isinstance(value, (int, float)) and 0 <= value <= 1):
        raise ValueError(f"{path}: expected a fraction in [0, 1] or null, got {value!r}")
    return value


def _provenance(value, path):
    if value not in PROVENANCE:
        raise ValueError(f"{path}: provenance {value!r} not in {sorted(PROVENANCE)}")
    return value


def load_site(directory=CONFIG_DIR):
    data = _read("site.json", directory)
    for key, value in data.get("provenance", {}).items():
        _provenance(value, f"site.provenance.{key}")
    return SiteConfig(**data)


def load_optics(directory=CONFIG_DIR):
    data = _read("optical.json", directory)
    optics = {}
    for name in ("cover", "shade_screen_1", "shade_screen_2"):
        item = data[name]
        optics[name] = OpticalProperties(
            tau_direct=_fraction(item.get("direct_transmittance"), f"{name}.direct_transmittance"),
            tau_diffuse=_fraction(item.get("diffuse_transmittance"), f"{name}.diffuse_transmittance"),
            source=item.get("source", "unknown"),
            provenance=_provenance(item.get("provenance", "unknown"), f"{name}.provenance"),
            verified=bool(item.get("verified", False)),
        )
    return optics


def load_radiation(directory=CONFIG_DIR):
    data = _read("radiation.json", directory)
    height = data.get("crop_reference_height_m") or {}
    return RadiationConfig(
        grid_resolution_m=data["grid_resolution_m"],
        crop_reference_height_m=height.get("value"),
        crop_reference_height_provenance=_provenance(height.get("provenance", "unknown"), "crop_reference_height_m"),
    )
