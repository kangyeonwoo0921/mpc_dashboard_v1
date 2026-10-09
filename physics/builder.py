"""The only normalized LIVE -> physics adapter. No I/O or raw-key translation."""

from copy import deepcopy
from datetime import datetime

from .contracts import Actuators, GreenhouseState, InputProvenance, PhysicsInput, Weather
from .parameters import parse_optical_config, parse_site_config
from .validation import require


def build_physics_input(live_snapshot, site_config, optical_config, timestamp=None):
    require(isinstance(live_snapshot, dict), "live_snapshot", live_snapshot, "normalized DTO object")
    environment = live_snapshot.get("environment", {})
    actuators = live_snapshot.get("actuators", {})
    for name, value in (("environment", environment), ("actuators", actuators)):
        require(isinstance(value, dict), name, value, "normalized DTO object")
    stamp = live_snapshot.get("timestamp") if timestamp is None else timestamp
    if isinstance(stamp, datetime):
        stamp = stamp.isoformat()
    mappings = ["actuators.roof_vent_left_pct", "actuators.roof_vent_right_pct",
                "actuators.shade_screen_1_pct", "actuators.shade_screen_2_pct"]
    if environment.get("solar_w_m2") is not None:
        mappings.append("weather.global_horizontal_irradiance_w_m2")
    return PhysicsInput(
        timestamp=stamp,
        site=deepcopy(parse_site_config(site_config)),
        optical_parameters=deepcopy(parse_optical_config(optical_config)),
        weather=Weather(
            outdoor_temperature_c=environment.get("outdoor_temperature_c"),
            # Existing DTO has no outdoor RH, DNI, DHI or numeric wind bearing.
            global_horizontal_irradiance_w_m2=environment.get("solar_w_m2"),
            wind_speed_m_s=environment.get("wind_speed_m_s"),
        ),
        greenhouse_state=GreenhouseState(
            indoor_temperature_c=environment.get("indoor_temperature_c"),
            indoor_relative_humidity_pct=environment.get("indoor_rh_pct"),
        ),
        actuators=Actuators(**{name: actuators.get(name) for name in (
            "roof_vent_left_pct", "roof_vent_right_pct", "shade_screen_1_pct", "shade_screen_2_pct")}),
        provenance=InputProvenance(live_snapshot.get("source"), live_snapshot.get("connected"), tuple(mappings)),
    )
