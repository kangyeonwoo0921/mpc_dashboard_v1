"""Typed data model for the prediction-model physics (task Step 4).

Field-specific parameters have NO default value other than None. ``missing()`` lists unset
fields; ``require(*names)`` raises MissingParameterError so an equation cannot be evaluated
without its parameters. Present values are range-checked; nothing is clipped or substituted.
Variable names, units and sources: ``variables.py`` / docs/VARIABLE_REGISTRY.md.

Note: ``greenhouse_mpc.types.WeatherInput`` is the measurement/recommendation-layer record (RH based,
Phase 2.2). The ``WeatherInput`` here is the physics-layer disturbance record (VP based).
"""

from dataclasses import dataclass, fields

from . import constants
from ._validation import MissingParameterError, celsius, fraction, non_negative, number, positive


class _Checked:
    _checks = {}   # field name -> validator

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            check = self._checks.get(f.name)
            if value is not None and check is not None:
                check(f.name, value)

    def missing(self):
        return [f.name for f in fields(self) if getattr(self, f.name) is None]

    def require(self, *names):
        absent = [name for name in (names or [f.name for f in fields(self)]) if getattr(self, name) is None]
        if absent:
            raise MissingParameterError(f"{type(self).__name__}: missing {absent}")
        return self


@dataclass(frozen=True)
class ClimateState(_Checked):
    """Dynamic state x = [T_Air, VP_Air] (baseline §1.1). VP_Air, not RH or X, is the moisture state."""
    T_air: float          # [degC] greenhouse air temperature (Vanthoor T_Air)
    VP_air: float         # [Pa] greenhouse air vapour pressure (Vanthoor VP_Air)
    _checks = {"T_air": celsius, "VP_air": non_negative}

    def __post_init__(self):
        number("T_air", self.T_air)
        number("VP_air", self.VP_air)
        super().__post_init__()


@dataclass(frozen=True)
class ControlInput(_Checked):
    """Control u in Vanthoor form: dimensionless control fractions in [0, 1] (baseline §1.2).

    Mapping from field percentages (roof %, screen opening % with 100 = retracted) is NOT defined
    here (open question Q-1). u_diffuse_screen has no source optical relation (DIFF-OPEN).
    """
    u_roof: float | None = None              # [-] Vanthoor U_Roof, Eq. 8.65 / 8.68
    u_shade_screen: float | None = None      # [-] Vanthoor U_ShScr, Eq. 8.16 / 8.17
    u_diffuse_screen: float | None = None    # [-] project control; no source relation (UNRESOLVED)
    _checks = {"u_roof": fraction, "u_shade_screen": fraction, "u_diffuse_screen": fraction}


@dataclass(frozen=True)
class WeatherInput(_Checked):
    """Disturbances d (baseline §1.3)."""
    T_out: float | None = None               # [degC] outside air temperature (Vanthoor T_Out)
    VP_out: float | None = None              # [Pa] outside vapour pressure (Vanthoor VP_Out)
    wind_speed: float | None = None          # [m s-1] (Vanthoor v_Wind)
    wind_direction: float | None = None      # [deg] stored only; no C_w(theta) function (WINDDIR-01)
    solar_radiation: float | None = None     # [W m-2] global radiation at the site sensor (I_solar)
    rain: bool | None = None                 # [-] rain state
    _checks = {"T_out": celsius, "VP_out": non_negative, "wind_speed": non_negative,
               "solar_radiation": non_negative, "wind_direction": number}


@dataclass(frozen=True)
class GreenhouseGeometry(_Checked):
    """Geometry (baseline §21: field_required)."""
    A_floor: float | None = None             # [m2] floor area (Vanthoor A_Flr)
    A_roof: float | None = None              # [m2] maximum roof-vent area (Vanthoor A_Roof)
    h_vent: float | None = None              # [m] vertical dimension of one vent opening (h_Vent)
    _checks = {"A_floor": positive, "A_roof": non_negative, "h_vent": non_negative}


@dataclass(frozen=True)
class VentilationParameters(_Checked):
    """Ventilation coefficients (baseline §21: calibration or geometry-matched source)."""
    C_d: float | None = None                 # [-] discharge coefficient (Eq. 8.65)
    C_w: float | None = None                 # [-] global wind-pressure coefficient (Eq. 8.65)
    c_leakage: float | None = None           # leakage coefficient (Eq. 8.71), calibration_required; unit Q-4
    _checks = {"C_d": non_negative, "C_w": non_negative, "c_leakage": non_negative}


@dataclass(frozen=True)
class CoverParameters(_Checked):
    """Cover layer properties for Eq. 8.19 (CONDITIONAL TO LAYER MATCH)."""
    h_roof: float | None = None              # [m] roof (cover) thickness (h_Rf)
    lambda_roof: float | None = None         # [W m-1 K-1] roof thermal conductivity (lambda_Rf)
    _checks = {"h_roof": positive, "lambda_roof": positive}


@dataclass(frozen=True)
class ShadeScreenParameters(_Checked):
    """Movable shade screen material (baseline §14, §15, §21: manufacturer or measurement)."""
    tau_PAR: float | None = None             # [-] tau_ShScrPAR
    rho_PAR: float | None = None             # [-] rho_ShScrPAR
    tau_NIR: float | None = None             # [-] tau_ShScrNIR
    rho_NIR: float | None = None             # [-] rho_ShScrNIR
    tau_FIR: float | None = None             # [-] tau_ThScrFIR, only if used as thermal screen (Eq. 8.39)
    K_screen: float | None = None            # [m3 m-2 K-0.66 s-1] K_ThScr (Eq. 8.41), calibration_required
    _checks = {"tau_PAR": fraction, "rho_PAR": fraction, "tau_NIR": fraction, "rho_NIR": fraction,
               "tau_FIR": fraction, "K_screen": non_negative}


@dataclass(frozen=True)
class SemiPermanentShadeLayer(_Checked):
    """Semi-permanent shading layer of Eq. 8.16 / 8.17 / 8.19. Existence on site unconfirmed (Q-2)."""
    u_perm: float | None = None              # [-] U_ShScrPer
    tau_PAR: float | None = None             # [-] tau_ShScrPerPAR
    rho_PAR: float | None = None             # [-] rho_ShScrPerPAR
    h_perm: float | None = None              # [m] h_ShScrPer
    lambda_perm: float | None = None         # [W m-1 K-1] lambda_ShScrPer
    _checks = {"u_perm": fraction, "tau_PAR": fraction, "rho_PAR": fraction,
               "h_perm": non_negative, "lambda_perm": positive}


@dataclass(frozen=True)
class DiffuseScreenParameters(_Checked):
    """Diffuse screen optical coefficients (Cabrera-type definitions). Defined only: no relation to
    u_diffuse_screen exists (DIFF-OPEN UNRESOLVED)."""
    tau_bb: float | None = None              # [-] direct-to-direct
    tau_bd: float | None = None              # [-] direct-to-diffuse
    tau_d: float | None = None               # [-] diffuse (overcast-determined)
    _checks = {"tau_bb": non_negative, "tau_bd": number, "tau_d": non_negative}


@dataclass(frozen=True)
class CropParameters(_Checked):
    """Crop parameters for Eq. 8.47-8.49 (baseline §21)."""
    LAI: float | None = None                 # [m2 m-2] leaf area index
    r_b: float | None = None                 # [s m-1] boundary-layer resistance
    r_s_min: float | None = None             # [s m-1] minimum stomatal resistance
    _checks = {"LAI": non_negative, "r_b": non_negative, "r_s_min": non_negative}


@dataclass(frozen=True)
class ThermophysicalProperties(_Checked):
    """Air/water properties used by Eq. 8.41, 8.42, 8.48 and PSY-03. Condition-dependent, so not
    treated as universal constants and not defaulted (open question Q-11)."""
    rho_air: float | None = None             # [kg m-3] greenhouse air density
    c_p_air: float | None = None             # [J kg-1 K-1] specific heat of air
    delta_H: float | None = None             # [J kg-1] latent heat of evaporation
    gamma: float | None = None               # [Pa K-1] psychrometric constant
    P_atm: float | None = None               # [Pa] atmospheric pressure (measured or configured)
    _checks = {"rho_air": positive, "c_p_air": positive, "delta_H": positive, "gamma": positive,
               "P_atm": positive}


@dataclass(frozen=True)
class PhysicalConstants:
    """Universal constants (baseline §0 rule 5); values from ``constants.py``."""
    sigma: float = constants.SIGMA           # [W m-2 K-4]
    R: float = constants.R_GAS               # [J mol-1 K-1]
    M_water: float = constants.M_WATER       # [kg mol-1]
    g: float = constants.G                   # [m s-2]
