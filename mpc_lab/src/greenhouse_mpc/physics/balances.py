"""Top-level climate-state balances, Vanthoor (2011) Eq. 8.2 (TEMP-01) and Eq. 8.10 (HUM-01).

The full source term list is kept. Terms for devices not present/confirmed at the site are not
deleted from the equation: they are declared inactive in ``config/model_components.yaml`` and the
wrapper refuses a value for an inactive term and requires a value for an active term.
Each flux is computed elsewhere by its own source function and passed in by keyword.
No time discretization is performed here (DISC-01 is an implementation decision for later).
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from ._validation import MissingParameterError, PhysicsInputError, number, positive

# Eq. 8.2: cap_Air dT_Air/dt = gains - losses   [W m-2]
TEMPERATURE_GAIN_TERMS = ("H_can_air", "H_pad_air", "H_mech_air", "H_pipe_air", "H_pas_air",
                          "H_blow_air", "R_glob_sun_air")
TEMPERATURE_LOSS_TERMS = ("H_air_flr", "H_air_th_scr", "H_air_out", "H_air_top", "H_air_out_pad",
                          "L_air_fog")

# Eq. 8.10: cap_VPAir dVP_Air/dt = gains - losses   [kg m-2 s-1]
MOISTURE_GAIN_TERMS = ("MV_can_air", "MV_pad_air", "MV_fog_air", "MV_blow_air")
MOISTURE_LOSS_TERMS = ("MV_air_th_scr", "MV_air_top", "MV_air_out", "MV_air_out_pad", "MV_air_mech")

ALL_TERMS = TEMPERATURE_GAIN_TERMS + TEMPERATURE_LOSS_TERMS + MOISTURE_GAIN_TERMS + MOISTURE_LOSS_TERMS
COMPONENTS_FILE = Path(__file__).resolve().parents[3] / "config" / "model_components.yaml"
ACTIVATION_STATES = frozenset({"active", "inactive"})


@dataclass(frozen=True)
class ComponentActivation:
    """Which source terms of Eq. 8.2 / 8.10 are instantiated for this site."""
    active: frozenset

    def __post_init__(self):
        unknown = set(self.active) - set(ALL_TERMS)
        if unknown:
            raise PhysicsInputError(f"unknown balance terms {sorted(unknown)}")


def load_component_activation(path=COMPONENTS_FILE):
    with Path(path).open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    terms = {**raw["temperature_balance_eq_8_2"], **raw["moisture_balance_eq_8_10"]}
    missing = set(ALL_TERMS) - set(terms)
    if missing:
        raise PhysicsInputError(f"model_components.yaml must declare every term; missing {sorted(missing)}")
    for name, entry in terms.items():
        if entry.get("state") not in ACTIVATION_STATES or not entry.get("reason"):
            raise PhysicsInputError(f"{name}: state must be active/inactive and a reason is required")
    return ComponentActivation(frozenset(name for name, entry in terms.items() if entry["state"] == "active"))


def _sum_active(values, gains, losses, activation):
    total = 0.0
    for sign, names in ((1.0, gains), (-1.0, losses)):
        for name in names:
            value = values[name]
            if name in activation.active:
                if value is None:
                    raise MissingParameterError(f"{name} is active but no flux was supplied")
                total += sign * number(name, value)
            elif value is not None:
                raise PhysicsInputError(f"{name} is inactive for this site; a value must not be supplied")
    return total


def eq_8_2_temperature_rhs(activation, *,
                           H_can_air=None, H_pad_air=None, H_mech_air=None, H_pipe_air=None,
                           H_pas_air=None, H_blow_air=None, R_glob_sun_air=None,
                           H_air_flr=None, H_air_th_scr=None, H_air_out=None, H_air_top=None,
                           H_air_out_pad=None, L_air_fog=None):
    """TEMP-01. Right-hand side of the greenhouse-air temperature balance.

    Source: Vanthoor (2011), Eq. 8.2
    Equation: cap_Air dT_Air/dt = H_CanAir + H_PadAir + H_MechAir + H_PipeAir + H_PasAir + H_BlowAir
                                  + R_Glob_SunAir - H_AirFlr - H_AirThScr - H_AirOut - H_AirTop
                                  - H_AirOut_Pad - L_AirFog
    Inputs: every flux [W m-2]; inactive terms must be None, active terms must be given
    Output: RHS [W m-2]
    """
    values = dict(H_can_air=H_can_air, H_pad_air=H_pad_air, H_mech_air=H_mech_air, H_pipe_air=H_pipe_air,
                  H_pas_air=H_pas_air, H_blow_air=H_blow_air, R_glob_sun_air=R_glob_sun_air,
                  H_air_flr=H_air_flr, H_air_th_scr=H_air_th_scr, H_air_out=H_air_out, H_air_top=H_air_top,
                  H_air_out_pad=H_air_out_pad, L_air_fog=L_air_fog)
    return _sum_active(values, TEMPERATURE_GAIN_TERMS, TEMPERATURE_LOSS_TERMS, activation)


def eq_8_2_dT_air_dt(rhs_W_m2, cap_air):
    """Eq. 8.2 solved for the derivative: dT_Air/dt = RHS / cap_Air.

    Inputs: rhs_W_m2 [W m-2], cap_air [J K-1 m-2] (definition not given in the baseline; Q-8)
    Output: dT_air/dt [K s-1]
    """
    return number("rhs_W_m2", rhs_W_m2) / positive("cap_air", cap_air)


def eq_8_10_vapour_rhs(activation, *,
                       MV_can_air=None, MV_pad_air=None, MV_fog_air=None, MV_blow_air=None,
                       MV_air_th_scr=None, MV_air_top=None, MV_air_out=None, MV_air_out_pad=None,
                       MV_air_mech=None):
    """HUM-01. Right-hand side of the greenhouse-air vapour-pressure balance.

    Source: Vanthoor (2011), Eq. 8.10
    Equation: cap_VPAir dVP_Air/dt = MV_CanAir + MV_PadAir + MV_FogAir + MV_BlowAir - MV_AirThScr
                                     - MV_AirTop - MV_AirOut - MV_AirOut_Pad - MV_AirMech
    Inputs: every flux [kg m-2 s-1]; inactive terms must be None, active terms must be given
    Output: RHS [kg m-2 s-1]
    """
    values = dict(MV_can_air=MV_can_air, MV_pad_air=MV_pad_air, MV_fog_air=MV_fog_air,
                  MV_blow_air=MV_blow_air, MV_air_th_scr=MV_air_th_scr, MV_air_top=MV_air_top,
                  MV_air_out=MV_air_out, MV_air_out_pad=MV_air_out_pad, MV_air_mech=MV_air_mech)
    return _sum_active(values, MOISTURE_GAIN_TERMS, MOISTURE_LOSS_TERMS, activation)


def eq_8_10_dVP_air_dt(rhs_kg_m2_s, cap_VP_air):
    """Eq. 8.10 solved for the derivative: dVP_Air/dt = RHS / cap_VPAir.

    Inputs: rhs_kg_m2_s [kg m-2 s-1], cap_VP_air [kg m-2 Pa-1] (definition not given in the baseline; Q-8)
    Output: dVP_air/dt [Pa s-1]
    """
    return number("rhs_kg_m2_s", rhs_kg_m2_s) / positive("cap_VP_air", cap_VP_air)
