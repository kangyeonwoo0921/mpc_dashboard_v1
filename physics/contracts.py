"""Version 1 JSON-serializable contracts, independent of Django and rendering."""

import math
from dataclasses import asdict, dataclass, field

from .parameters import OpticalConfig, SiteConfig
from .validation import angle, number, opening_to_deployment, require, timestamp


class JsonContract:
    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Weather(JsonContract):
    outdoor_temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    global_horizontal_irradiance_w_m2: float | None = None
    direct_normal_irradiance_w_m2: float | None = None
    diffuse_horizontal_irradiance_w_m2: float | None = None
    wind_speed_m_s: float | None = None
    wind_direction_deg: float | None = None

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            lower = 0 if name.endswith(("_w_m2", "_m_s", "_pct")) else None
            number(value, f"weather.{name}", lower, 100 if name.endswith("_pct") else None)
        angle(self.wind_direction_deg, "weather.wind_direction_deg")


@dataclass(frozen=True)
class GreenhouseState(JsonContract):
    indoor_temperature_c: float | None = None
    indoor_relative_humidity_pct: float | None = None

    def __post_init__(self):
        number(self.indoor_temperature_c, "greenhouse_state.indoor_temperature_c")
        number(self.indoor_relative_humidity_pct, "greenhouse_state.indoor_relative_humidity_pct", 0, 100)


@dataclass(frozen=True)
class Actuators(JsonContract):
    roof_vent_left_pct: float | None = None
    roof_vent_right_pct: float | None = None
    shade_screen_1_pct: float | None = None
    shade_screen_2_pct: float | None = None
    shade_screen_1_deployment_fraction: float | None = field(init=False)
    shade_screen_2_deployment_fraction: float | None = field(init=False)

    def __post_init__(self):
        for name in ("roof_vent_left_pct", "roof_vent_right_pct", "shade_screen_1_pct", "shade_screen_2_pct"):
            number(getattr(self, name), f"actuators.{name}", 0, 100)
        for index in (1, 2):
            object.__setattr__(self, f"shade_screen_{index}_deployment_fraction",
                               opening_to_deployment(getattr(self, f"shade_screen_{index}_pct")))


@dataclass(frozen=True)
class InputProvenance(JsonContract):
    source: str | None = None
    connected: bool | None = None
    provisional_mappings: tuple[str, ...] = ()

    def __post_init__(self):
        require(self.source is None or isinstance(self.source, str), "source", self.source, "string or null")
        require(self.connected is None or type(self.connected) is bool, "connected", self.connected, "boolean or null")


@dataclass(frozen=True)
class InputQuality(JsonContract):
    status: str
    statuses: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    unverified_inputs: tuple[str, ...]


@dataclass(frozen=True)
class PhysicsInput(JsonContract):
    timestamp: str
    site: SiteConfig = field(default_factory=SiteConfig)
    weather: Weather = field(default_factory=Weather)
    greenhouse_state: GreenhouseState = field(default_factory=GreenhouseState)
    actuators: Actuators = field(default_factory=Actuators)
    optical_parameters: OpticalConfig = field(default_factory=OpticalConfig)
    provenance: InputProvenance = field(default_factory=InputProvenance)
    schema_version: int = field(default=1, init=False)
    quality: InputQuality = field(init=False)

    def __post_init__(self):
        timestamp(self.timestamp)
        for name, cls in (("site", SiteConfig), ("weather", Weather), ("greenhouse_state", GreenhouseState),
                          ("actuators", Actuators), ("optical_parameters", OpticalConfig), ("provenance", InputProvenance)):
            require(isinstance(getattr(self, name), cls), name, getattr(self, name), cls.__name__)
        object.__setattr__(self, "quality", assess_input(self))


def assess_input(data):
    """Concurrent quality conditions; status is the highest-priority condition.

    Missing optional measurements are listed but don't by themselves prevent a
    future solar calculation. No calculation is performed even if fully supplied.
    """
    missing, unverified, statuses = [], [], []
    for group in ("weather", "greenhouse_state", "actuators"):
        for name, value in asdict(getattr(data, group)).items():
            if value is None:
                missing.append(f"{group}.{name}")
    required_site = ("latitude_deg", "longitude_deg")
    for name in (*required_site, "elevation_m"):
        if getattr(data.site, name) is None:
            missing.append(f"site.{name}")
        if not data.site.provenance.get(name, {}).get("verified", False):
            unverified.append(f"site.{name}")
    orientation = data.site.orientation
    if orientation.greenhouse_long_axis_azimuth_deg is None:
        missing.append("site.orientation.greenhouse_long_axis_azimuth_deg")
    if not orientation.verified:
        unverified.append("site.orientation.greenhouse_long_axis_azimuth_deg")
    if (data.weather.global_horizontal_irradiance_w_m2 is None
            or any(getattr(data.site, name) is None for name in required_site)
            or orientation.greenhouse_long_axis_azimuth_deg is None):
        statuses.append("missing_input")
    for path, parameter in data.optical_parameters.items():
        if parameter.value is None:
            missing.append(path)
        if not parameter.verified:
            unverified.append(path)
    if any(parameter.value is None for _, parameter in data.optical_parameters.items()):
        statuses.append("parameter_missing")
    if data.weather.global_horizontal_irradiance_w_m2 is not None and (
            data.weather.direct_normal_irradiance_w_m2 is None or data.weather.diffuse_horizontal_irradiance_w_m2 is None):
        statuses.append("decomposition_required")
    unverified.extend(data.provenance.provisional_mappings)
    if data.provenance.source and data.provenance.source.startswith("mock"):
        unverified.append("provenance.mock_data")
    if data.provenance.connected is False:
        statuses.append("disconnected")
    if unverified:
        statuses.append("unverified")
    if not statuses:
        statuses.append("not_computed")
    return InputQuality(statuses[0], tuple(statuses), tuple(missing), tuple(unverified))


@dataclass(frozen=True)
class DirectionPhysics(JsonContract):
    x: float | None = None
    y: float | None = None
    z: float | None = None

    def __post_init__(self):
        values = (self.x, self.y, self.z)
        if all(value is None for value in values):
            return
        for name, value in zip(("x", "y", "z"), values):
            number(value, f"sun.direction_physics.{name}", nullable=False)
        require(math.isclose(math.hypot(*values), 1, abs_tol=1e-9), "sun.direction_physics", values, "unit vector")


@dataclass(frozen=True)
class Sun(JsonContract):
    altitude_deg: float | None = None
    azimuth_deg: float | None = None
    zenith_deg: float | None = None
    direction_physics: DirectionPhysics = field(default_factory=DirectionPhysics)

    def __post_init__(self):
        number(self.altitude_deg, "sun.altitude_deg", -90, 90)
        angle(self.azimuth_deg, "sun.azimuth_deg")
        number(self.zenith_deg, "sun.zenith_deg", 0, 180)
        require(isinstance(self.direction_physics, DirectionPhysics), "sun.direction_physics", self.direction_physics, "DirectionPhysics")
        if self.altitude_deg is not None and self.zenith_deg is not None:
            require(math.isclose(self.altitude_deg + self.zenith_deg, 90, abs_tol=1e-9),
                    "sun.zenith_deg", self.zenith_deg, "90 - altitude_deg")


@dataclass(frozen=True)
class SolarOutput(JsonContract):
    sun: Sun = field(default_factory=Sun)

    def __post_init__(self):
        require(isinstance(self.sun, Sun), "sun", self.sun, "Sun")


@dataclass(frozen=True)
class RadiationGrid(JsonContract):
    cell_size_m: float = 1.0
    rows: int | None = None
    cols: int | None = None
    values_w_m2: list = field(default_factory=list)
    # Reserved for Phase 2.0 binary output: row-major, 1 sunlit / 0 shaded.
    sunlit_mask: list = field(default_factory=list)

    def __post_init__(self):
        number(self.cell_size_m, "grid.cell_size_m", 0, nullable=False)
        require(self.cell_size_m > 0, "grid.cell_size_m", self.cell_size_m, "> 0")
        for name in ("rows", "cols"):
            value = getattr(self, name)
            require(value is None or (type(value) is int and value > 0), f"grid.{name}", value, "positive integer or null")
        require((self.rows is None) == (self.cols is None), "grid", (self.rows, self.cols), "both dimensions present or both null")
        for name in ("values_w_m2", "sunlit_mask"):
            values = getattr(self, name)
            require(isinstance(values, list), f"grid.{name}", values, "row-major flat array")
            require(not values or (self.rows is not None and len(values) == self.rows * self.cols),
                    f"grid.{name}", len(values), "rows * cols elements when populated")
            for index, value in enumerate(values):
                path = f"grid.{name}[{index}]"
                if name == "sunlit_mask":
                    require(value is None or (type(value) is int and value in (0, 1)), path, value, "0 / 1 / null")
                else:
                    number(value, path, 0)


@dataclass(frozen=True)
class Radiation(JsonContract):
    mean_inside_irradiance_w_m2: float | None = None
    direct_mean_w_m2: float | None = None
    diffuse_mean_w_m2: float | None = None
    grid: RadiationGrid = field(default_factory=RadiationGrid)

    def __post_init__(self):
        for name in ("mean_inside_irradiance_w_m2", "direct_mean_w_m2", "diffuse_mean_w_m2"):
            number(getattr(self, name), f"radiation.{name}", 0)
        require(isinstance(self.grid, RadiationGrid), "radiation.grid", self.grid, "RadiationGrid")


@dataclass(frozen=True)
class OutputQuality(JsonContract):
    status: str = "not_computed"
    missing_inputs: list[str] = field(default_factory=list)

    def __post_init__(self):
        require(self.status in {"not_computed", "missing_input", "parameter_missing", "decomposition_required", "unverified", "computed"},
                "quality.status", self.status, "supported output quality status")
        require(isinstance(self.missing_inputs, list) and all(isinstance(item, str) for item in self.missing_inputs),
                "quality.missing_inputs", self.missing_inputs, "field-path array")


@dataclass(frozen=True)
class RadiationOutput(JsonContract):
    timestamp: str
    sun: Sun = field(default_factory=Sun)
    radiation: Radiation = field(default_factory=Radiation)
    quality: OutputQuality = field(default_factory=OutputQuality)
    schema_version: int = field(default=1, init=False)

    def __post_init__(self):
        timestamp(self.timestamp)
        for name, cls in (("sun", Sun), ("radiation", Radiation), ("quality", OutputQuality)):
            require(isinstance(getattr(self, name), cls), name, getattr(self, name), cls.__name__)
