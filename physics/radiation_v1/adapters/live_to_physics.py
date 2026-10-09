"""LIVE normalized DTO -> v1 weather/actuator contract (spec section 14).

Only the existing provisional mapping is used: environment.solar_w_m2 is the outside
sensor and is passed as GHI (sensor type/units/installation unverified). DNI and DHI
are not measured, so they stay None. Missing values are never turned into zero.
"""


def weather_from_live(snapshot):
    environment = (snapshot or {}).get("environment") or {}
    return {"ghi_W_m2": environment.get("solar_w_m2"), "dni_W_m2": None, "dhi_W_m2": None,
            "source": (snapshot or {}).get("source"), "ghi_mapping": "provisional: solar_w_m2 sensor, unverified"}


def actuators_from_live(snapshot):
    actuators = (snapshot or {}).get("actuators") or {}
    return {
        "roof_vent_left_percent": actuators.get("roof_vent_left_pct"),
        "roof_vent_right_percent": actuators.get("roof_vent_right_pct"),
        "shade_screen_1_opening_percent": actuators.get("shade_screen_1_pct"),
        "shade_screen_2_opening_percent": actuators.get("shade_screen_2_pct"),
    }
