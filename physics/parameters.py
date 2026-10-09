"""Physical configuration only. Rendering config/materials are never loaded."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .validation import PhysicsValidationError, angle, number, require

SOURCE_TYPES = {"measured", "manufacturer_spec", "drawing", "paper", "estimated",
                "operator_reported", "temporary_test_fixture", "unknown"}


@dataclass(frozen=True)
class PhysicalParameter:
    value: float | None = None
    unit: str = "fraction"
    verified: bool = False
    source: str | None = None
    source_type: str = "unknown"
    notes: str | None = None

    def __post_init__(self):
        number(self.value, "parameter.value")
        require(type(self.verified) is bool, "parameter.verified", self.verified, "boolean")
        require(isinstance(self.unit, str) and bool(self.unit), "parameter.unit", self.unit, "unit string")
        require(self.source_type in SOURCE_TYPES, "parameter.source_type", self.source_type, str(SOURCE_TYPES))
        for name in ("source", "notes"):
            value = getattr(self, name)
            require(value is None or isinstance(value, str), f"parameter.{name}", value, "string or null")
        require(not self.verified or (self.value is not None and bool(self.source)
                and self.source_type != "unknown"), "parameter.verified", self.verified,
                "verified value with source and source_type")


@dataclass(frozen=True)
class Orientation:
    greenhouse_long_axis_azimuth_deg: float | None = None
    verified: bool = False
    source: str | None = None
    source_type: str = "unknown"

    def __post_init__(self):
        angle(self.greenhouse_long_axis_azimuth_deg, "site.orientation.greenhouse_long_axis_azimuth_deg")
        PhysicalParameter(self.greenhouse_long_axis_azimuth_deg, "deg", self.verified,
                          self.source, self.source_type)


@dataclass(frozen=True)
class SiteConfig:
    site_id: str = "greenhouse_01"
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    elevation_m: float | None = None
    timezone: str = "Asia/Seoul"
    orientation: Orientation = field(default_factory=Orientation)
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        require(isinstance(self.site_id, str) and bool(self.site_id), "site.site_id", self.site_id, "nonempty string")
        number(self.latitude_deg, "site.latitude_deg", -90, 90)
        number(self.longitude_deg, "site.longitude_deg", -180, 180)
        number(self.elevation_m, "site.elevation_m")
        require(isinstance(self.orientation, Orientation), "site.orientation", self.orientation, "Orientation")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            raise PhysicsValidationError(f"site.timezone: invalid {self.timezone!r}; expected IANA timezone") from None
        require(isinstance(self.provenance, dict), "site.provenance", self.provenance, "mapping")
        for name, info in self.provenance.items():
            require(name in ("latitude_deg", "longitude_deg", "elevation_m"),
                    "site.provenance", name, "site coordinate field")
            require(isinstance(info, dict), f"site.provenance.{name}", info, "provenance object")
            _construct(PhysicalParameter, dict(info, value=getattr(self, name),
                       unit="m" if name == "elevation_m" else "deg"), f"site.provenance.{name}")


@dataclass(frozen=True)
class RoofCoverOptics:
    solar_transmittance_direct: PhysicalParameter = field(default_factory=PhysicalParameter)
    solar_transmittance_diffuse: PhysicalParameter = field(default_factory=PhysicalParameter)


@dataclass(frozen=True)
class ScreenOptics:
    solar_transmittance_deployed: PhysicalParameter = field(default_factory=PhysicalParameter)


@dataclass(frozen=True)
class OpticalConfig:
    schema_version: int = 1
    roof_cover: RoofCoverOptics = field(default_factory=RoofCoverOptics)
    shade_screen_1: ScreenOptics = field(default_factory=ScreenOptics)
    shade_screen_2: ScreenOptics = field(default_factory=ScreenOptics)

    def __post_init__(self):
        require(type(self.schema_version) is int and self.schema_version == 1,
                "optics.schema_version", self.schema_version, "1")
        for path, parameter in self.items():
            require(isinstance(parameter, PhysicalParameter), path, parameter, "PhysicalParameter")
            require(parameter.unit == "fraction", path + ".unit", parameter.unit, "fraction")
            number(parameter.value, path + ".value", 0, 1)

    def items(self):
        for group in ("roof_cover", "shade_screen_1", "shade_screen_2"):
            value = getattr(self, group)
            expected = RoofCoverOptics if group == "roof_cover" else ScreenOptics
            require(isinstance(value, expected), group, value, expected.__name__)
            for name in value.__dataclass_fields__:
                yield f"optical.{group}.{name}", getattr(value, name)


def _construct(cls, values, path):
    require(isinstance(values, dict), path, values, "object")
    try:
        return cls(**values)
    except TypeError as error:
        raise PhysicsValidationError(f"{path}: invalid fields: {error}") from error


def parse_site_config(data):
    if isinstance(data, SiteConfig):
        return data
    require(isinstance(data, dict), "site", data, "object")
    values = dict(data)
    values["orientation"] = _construct(Orientation, values.get("orientation", {}), "site.orientation")
    return _construct(SiteConfig, values, "site")


def parse_optical_config(data):
    if isinstance(data, OpticalConfig):
        return data
    require(isinstance(data, dict), "optical", data, "object")
    values = dict(data)
    for group, cls in (("roof_cover", RoofCoverOptics), ("shade_screen_1", ScreenOptics),
                       ("shade_screen_2", ScreenOptics)):
        raw = values.get(group, {})
        require(isinstance(raw, dict), group, raw, "object")
        values[group] = _construct(cls, {key: _construct(PhysicalParameter, val, f"{group}.{key}")
                                        for key, val in raw.items()}, group)
    return _construct(OpticalConfig, values, "optical")


def validate_radiation_config(data):
    """Validate configuration, never run the configured future methods."""
    expected = {"schema_version", "grid", "direct_radiation", "diffuse_radiation", "reflections", "canopy_attenuation"}
    require(isinstance(data, dict) and set(data) == expected, "radiation_model", data, str(expected))
    require(type(data["schema_version"]) is int and data["schema_version"] == 1,
            "radiation_model.schema_version", data["schema_version"], "1")
    grid = data["grid"]
    require(isinstance(grid, dict) and set(grid) == {"cell_size_m", "reference_height_m"}, "grid", grid, "cell_size_m/reference_height_m")
    number(grid["cell_size_m"], "grid.cell_size_m", 0, nullable=False)
    require(grid["cell_size_m"] > 0, "grid.cell_size_m", grid["cell_size_m"], "> 0")
    number(grid["reference_height_m"], "grid.reference_height_m", 0)
    for name, method in (("direct_radiation", "ray_cast"), ("diffuse_radiation", "isotropic_initial"),
                         ("reflections", None), ("canopy_attenuation", None)):
        item = data[name]
        require(isinstance(item, dict) and set(item) == ({"enabled", "method"} if method else {"enabled"}), name, item, "model options")
        require(type(item["enabled"]) is bool, name + ".enabled", item["enabled"], "boolean")
        if method:
            require(item["method"] == method, name + ".method", item["method"], method)
        else:
            require(item["enabled"] is False, name + ".enabled", item["enabled"], "false in Phase 1.9")


def load_physics_config(directory=None):
    directory = Path(directory) if directory else Path(__file__).resolve().parents[1] / "config" / "physics"
    def read(name):
        return json.loads((directory / name).read_text(encoding="utf-8"))
    site = parse_site_config(read("site.json"))
    optics = parse_optical_config(read("optical_properties.json"))
    radiation = read("radiation_model.json")
    validate_radiation_config(radiation)
    return site, optics, radiation
