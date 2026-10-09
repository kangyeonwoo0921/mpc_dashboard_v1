"""Typed runtime structures (DP Phase 2.2; ARCHITECTURE.md §2, §3, §6, §7).

Conventions:
- Missing measurements are ``None`` (never 0). Invalid values raise ``InputValidationError``.
- Screen percentages are always **opening** %: 100 = fully retracted (open to light), 0 = fully deployed.
- Humidity ratio ``Xi`` is kg water per kg dry air.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime

RAIN_STATES = frozenset({"dry", "wet"})
RECOMMENDATION_STATUSES = frozenset({"ok", "recommendation_unavailable", "degraded"})
GROWTH_STAGES = frozenset({"establishment_vegetative", "flowering_fruit_set", "fruit_development_harvest"})
SEASON_MODES = frozenset({"august", "october", "december"})


class InputValidationError(ValueError):
    """Value present but physically or semantically invalid."""


def _aware(timestamp, name):
    if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
        raise InputValidationError(f"{name}: timezone-aware datetime required")


def _number(value, name, low=None, high=None, *, high_open=False):
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputValidationError(f"{name}: finite number or None required, got {value!r}")
    if low is not None and value < low:
        raise InputValidationError(f"{name}: {value} below {low}")
    if high is not None and (value >= high if high_open else value > high):
        raise InputValidationError(f"{name}: {value} above {'or equal to ' if high_open else ''}{high}")


def _percent(value, name):
    _number(value, name, 0.0, 100.0)


@dataclass(frozen=True)
class GreenhouseState:
    """Measured indoor state. ``Xi_in`` is filled by preprocessing (psychrometrics, Phase 2.3)."""
    timestamp: datetime
    T_in_C: float | None
    RH_in_percent: float | None
    Xi_in: float | None = None

    def __post_init__(self):
        _aware(self.timestamp, "GreenhouseState.timestamp")
        _number(self.T_in_C, "T_in_C", -40.0, 70.0)
        _percent(self.RH_in_percent, "RH_in_percent")
        _number(self.Xi_in, "Xi_in", 0.0, 0.2)

    def missing_critical(self):
        return [name for name in ("T_in_C", "RH_in_percent") if getattr(self, name) is None]


@dataclass(frozen=True)
class WeatherInput:
    """Disturbance vector d (DP §3). ``solar_global_W_m2`` is global shortwave at the sensor;
    Field report 2026-10-07: the sensor is mounted above the cover outside (provisional)."""
    timestamp: datetime
    T_out_C: float | None
    RH_out_percent: float | None            # required for Xi_out; absent in current live data (G-2)
    solar_global_W_m2: float | None
    wind_speed_m_s: float | None
    wind_direction_deg: float | None        # true north, clockwise
    rain_state: str | None                  # "dry" | "wet" | None (missing)
    DNI_W_m2: float | None = None           # optional initially
    DHI_W_m2: float | None = None
    Xi_out: float | None = None             # filled by preprocessing

    REQUIRED = ("T_out_C", "RH_out_percent", "solar_global_W_m2", "wind_speed_m_s",
                "wind_direction_deg", "rain_state")

    def __post_init__(self):
        _aware(self.timestamp, "WeatherInput.timestamp")
        _number(self.T_out_C, "T_out_C", -50.0, 60.0)
        _percent(self.RH_out_percent, "RH_out_percent")
        for name in ("solar_global_W_m2", "DNI_W_m2", "DHI_W_m2"):
            _number(getattr(self, name), name, 0.0, 1500.0)
        _number(self.wind_speed_m_s, "wind_speed_m_s", 0.0, 80.0)
        _number(self.wind_direction_deg, "wind_direction_deg", 0.0, 360.0, high_open=True)
        _number(self.Xi_out, "Xi_out", 0.0, 0.2)
        if self.rain_state is not None and self.rain_state not in RAIN_STATES:
            raise InputValidationError(f"rain_state: {self.rain_state!r} not in {sorted(RAIN_STATES)} or None")

    def missing_critical(self):
        return [name for name in self.REQUIRED if getattr(self, name) is None]


@dataclass(frozen=True)
class ActuatorState:
    """Control vector u (DP §2.2). ``roof_vent_percent`` is the common command for both vent
    channels (OD-1); the raw channels are kept for diagnostics."""
    roof_vent_percent: float | None
    diffuse_screen_open_percent: float | None
    shade_screen_open_percent: float | None
    roof_vent_left_percent: float | None = None
    roof_vent_right_percent: float | None = None

    def __post_init__(self):
        for name in ("roof_vent_percent", "diffuse_screen_open_percent", "shade_screen_open_percent",
                     "roof_vent_left_percent", "roof_vent_right_percent"):
            _percent(getattr(self, name), name)

    @property
    def diffuse_deployment_fraction(self):
        return None if self.diffuse_screen_open_percent is None else 1 - self.diffuse_screen_open_percent / 100

    @property
    def shade_deployment_fraction(self):
        return None if self.shade_screen_open_percent is None else 1 - self.shade_screen_open_percent / 100

    def as_vector(self):
        return (self.roof_vent_percent, self.diffuse_screen_open_percent, self.shade_screen_open_percent)

    def missing_critical(self):
        return [name for name in ("roof_vent_percent", "diffuse_screen_open_percent", "shade_screen_open_percent")
                if getattr(self, name) is None]


@dataclass(frozen=True)
class ReferenceSchedule:
    """Scheduler output for one step (BL §4.6, ARCHITECTURE.md §3). Unknown fields stay None."""
    timestamp: datetime
    growth_stage: str
    season_mode: str
    T_ref_C: float | None = None                     # instantaneous profile shape is OD-3 (unknown)
    T_soft_min_C: float | None = None
    T_soft_max_C: float | None = None
    T_mean24h_band_C: tuple[float, float] | None = None
    T_vent_threshold_C: float | None = None          # field-guide vent-opening temperature (C-12)
    VPD_ref_kPa: float | None = None
    VPD_soft_min_kPa: float | None = None
    VPD_soft_max_kPa: float | None = None
    RH_night_risk_percent: float | None = None
    Xi_day_min_g_per_kg: float | None = None
    instantaneous_light_ref_W_m2: tuple[float, float] | None = None
    DLI_target_mol_m2_d: tuple[float, float] | None = None
    condensation_risk_level: str | None = None
    light_preservation_priority: str | None = None
    vent_heat_loss_penalty_multiplier: float | None = None
    screen_shading_penalty_multiplier: float | None = None
    source_status: dict = field(default_factory=dict)

    def __post_init__(self):
        _aware(self.timestamp, "ReferenceSchedule.timestamp")
        if self.growth_stage not in GROWTH_STAGES:
            raise InputValidationError(f"growth_stage {self.growth_stage!r} not in {sorted(GROWTH_STAGES)}")
        if self.season_mode not in SEASON_MODES:
            raise InputValidationError(f"season_mode {self.season_mode!r} not in {sorted(SEASON_MODES)}")
        for low, high, name in ((self.T_soft_min_C, self.T_soft_max_C, "T_soft"),
                                (self.VPD_soft_min_kPa, self.VPD_soft_max_kPa, "VPD_soft")):
            if low is not None and high is not None and low > high:
                raise InputValidationError(f"{name}: min {low} > max {high}")
        for name in ("vent_heat_loss_penalty_multiplier", "screen_shading_penalty_multiplier"):
            _number(getattr(self, name), name, 0.0)


MOVE_WEIGHTS = ("w_v", "w_d", "w_s")
TRACKING_WEIGHTS = ("w_T", "w_H", "w_L", "w_Q", "w_DLI")


@dataclass(frozen=True)
class MPCConfig:
    """Controller configuration (DP §5, §23, §26). Weights may be None until chosen (no final values)."""
    sampling_minutes: float
    prediction_horizon_minutes: float
    control_horizon_minutes: float
    weights: dict
    enable_diffuse_screen_control: bool = True
    solver: dict = field(default_factory=dict)

    def __post_init__(self):
        for name in ("sampling_minutes", "prediction_horizon_minutes", "control_horizon_minutes"):
            value = getattr(self, name)
            _number(value, name, 0.0)
            if value is None or value <= 0:
                raise InputValidationError(f"{name}: positive value required")
        if self.control_horizon_minutes > self.prediction_horizon_minutes:
            raise InputValidationError("control horizon must not exceed prediction horizon")
        for name in ("prediction_horizon_minutes", "control_horizon_minutes"):
            steps = getattr(self, name) / self.sampling_minutes
            if abs(steps - round(steps)) > 1e-9:
                raise InputValidationError(f"{name} must be a whole number of sampling steps")
        unknown = set(self.weights) - set(MOVE_WEIGHTS) - set(TRACKING_WEIGHTS)
        if unknown:
            raise InputValidationError(f"unknown weights {sorted(unknown)}")
        for name, value in self.weights.items():
            _number(value, f"weights.{name}", 0.0)

    @property
    def prediction_steps(self):
        return round(self.prediction_horizon_minutes / self.sampling_minutes)

    @property
    def control_steps(self):
        return round(self.control_horizon_minutes / self.sampling_minutes)

    def weights_ready(self):
        """True only when every weight has a value; the optimizer must not run otherwise."""
        return all(self.weights.get(name) is not None for name in (*TRACKING_WEIGHTS, *MOVE_WEIGHTS))


@dataclass(frozen=True)
class MPCRecommendation:
    """Recommendation output (ARCHITECTURE.md §7). ``recommendation`` is None unless status is ok/degraded."""
    timestamp: datetime
    status: str
    recommendation: ActuatorState | None = None
    trajectory: tuple = ()                           # ActuatorState per control step
    predicted: dict = field(default_factory=dict)    # Tin_C, RH_percent, VPD_kPa, effective_radiation_W_m2, Q_vent_W
    diagnostics: dict = field(default_factory=dict)  # objective components
    day_phase_state: str | None = None
    active_constraints: tuple = ()
    overrides_applied: tuple = ()
    reasons: tuple = ()                              # why unavailable/degraded
    source_status: dict = field(default_factory=dict)
    mode: str = "recommendation_only"

    def __post_init__(self):
        _aware(self.timestamp, "MPCRecommendation.timestamp")
        if self.status not in RECOMMENDATION_STATUSES:
            raise InputValidationError(f"status {self.status!r} not in {sorted(RECOMMENDATION_STATUSES)}")
        if self.mode != "recommendation_only":
            raise InputValidationError("mode must be recommendation_only (no actuator commands)")
        if self.status == "recommendation_unavailable" and self.recommendation is not None:
            raise InputValidationError("an unavailable recommendation must not carry actuator values")
        if self.status == "recommendation_unavailable" and not self.reasons:
            raise InputValidationError("an unavailable recommendation must state its reasons")
