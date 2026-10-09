"""Ventilation equations from Vanthoor (2011), Chapter 8.

Eq. 8.65 (VENT-01), Eq. 8.68 (VENT-02), Eq. 8.71 (LEAK-01).

Wind direction (WINDDIR-01) is UNRESOLVED: no C_w(theta) function exists here. C_w enters Eq. 8.65
as a plain number. ``WindPressureCoefficientTable`` only holds a cited table for future selection;
it deliberately has no interpolation or correction method (baseline §13.3).
"""

import math
from dataclasses import dataclass

from ._validation import PhysicsInputError, celsius, fraction, non_negative, positive
from .constants import G, KELVIN_OFFSET


def eq_8_65_roof_ventilation(u_roof, A_roof, C_d, A_floor, h_vent, T_air, T_out, T_mean, C_w, wind_speed, g=G):
    """VENT-01. Roof natural ventilation (wind + buoyancy).

    Source: Vanthoor (2011), Eq. 8.65, based on Boulard & Baille (1995)
    Source symbols: f''_VentRoof, U_Roof, A_Roof, C_d, A_Flr, g, h_Vent, T_Air, T_Out, T_bar, C_w, v_Wind
    Equation: f = U_Roof A_Roof C_d / (2 A_Flr)
                  * sqrt( g h_Vent / 2 * (T_Air - T_Out) / (T_bar + 273.15) + C_w v_Wind^2 )
    Inputs: u_roof [-] in [0, 1] (Vanthoor aperture control, NOT the field %), A_roof [m2] maximum
            roof-vent area, C_d [-], A_floor [m2], h_vent [m], T_air, T_out, T_mean [degC],
            C_w [-], wind_speed [m s-1], g [m s-2]
    Output: f''_VentRoof [m3 m-2 s-1]
    Field-specific: A_roof, A_floor, h_vent (field_required); C_d, C_w (calibration or
        geometry-matched source). Wind-direction correction is NOT implemented.
    Domain: if the radicand is negative (T_air < T_out with low wind) the square root is undefined;
        PhysicsInputError is raised instead of altering the equation (open question Q-3).
    """
    u_roof = fraction("u_roof", u_roof)
    A_roof, C_d = non_negative("A_roof", A_roof), non_negative("C_d", C_d)
    A_floor, h_vent = positive("A_floor", A_floor), non_negative("h_vent", h_vent)
    T_air, T_out, T_mean = celsius("T_air", T_air), celsius("T_out", T_out), celsius("T_mean", T_mean)
    C_w, wind_speed, g = non_negative("C_w", C_w), non_negative("wind_speed", wind_speed), positive("g", g)
    radicand = g * h_vent / 2.0 * (T_air - T_out) / (T_mean + KELVIN_OFFSET) + C_w * wind_speed ** 2
    if radicand < 0:
        raise PhysicsInputError(f"Eq. 8.65 radicand is negative ({radicand}); equation undefined for these inputs")
    return u_roof * A_roof * C_d / (2.0 * A_floor) * math.sqrt(radicand)


def eq_8_68_roof_aperture(u_roof, A_roof):
    """VENT-02. Roof-vent aperture.

    Source: Vanthoor (2011), Eq. 8.68
    Source symbols: A^U_Roof, U_Roof, A_Roof
    Equation: A^U_Roof = U_Roof A_Roof
    Inputs: u_roof [-] in [0, 1], A_roof [m2]
    Output: A_roof_U [m2]
    """
    return fraction("u_roof", u_roof) * non_negative("A_roof", A_roof)


def eq_8_71_leakage(c_leakage, wind_speed):
    """LEAK-01 (CALIBRATION REQUIRED). Wind-dependent leakage, transcribed as in baseline §12.1.

    Source: Vanthoor (2011), Eq. 8.71 as written in the equation baseline
    Source symbols: f_leakage, c_leakage, v_Wind
    Equation: f_leakage = c_leakage                 if v_Wind < 0.25
                          c_leakage * v_Wind        if v_Wind >= 0.25
    Inputs: c_leakage (greenhouse-type dependent; calibration_required, never copied),
            wind_speed [m s-1]
    Output: f_leakage [m3 m-2 s-1]
    Open question Q-4: as transcribed, the two branches imply different units for c_leakage and a
        jump at 0.25 m s-1. The transcription is reproduced unchanged pending a check of the thesis.
    """
    c_leakage = non_negative("c_leakage", c_leakage)
    wind_speed = non_negative("wind_speed", wind_speed)
    if wind_speed < 0.25:
        return c_leakage
    return c_leakage * wind_speed


@dataclass(frozen=True)
class WindPressureCoefficientTable:
    """Placeholder for a cited C_w(wind direction) table (WINDDIR-01, UNRESOLVED).

    Data container only. No interpolation or correction function is provided; selecting a C_w
    value from this table for Eq. 8.65 is a future, separately approved step.
    """
    source: str                      # citation of the wind-pressure/ventilation study
    geometry: str                    # geometry the table was measured for
    angle_definition: str            # e.g. angle reference and sign convention of the source
    angles_deg: tuple
    C_w_values: tuple

    def __post_init__(self):
        if not self.source or not self.geometry or not self.angle_definition:
            raise PhysicsInputError("source, geometry and angle_definition are required for a C_w table")
        if len(self.angles_deg) != len(self.C_w_values) or not self.angles_deg:
            raise PhysicsInputError("angles_deg and C_w_values must be non-empty and equal length")
