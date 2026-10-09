"""Vapour-flux equations from Vanthoor (2011), Chapter 8.

Eq. 8.43 (COND-01), Eq. 8.44 (COND-02, optional), Eq. 8.45 (MV-01).
"""

import math

from ._validation import celsius, non_negative, number
from .constants import KELVIN_OFFSET, M_WATER, R_GAS

# Eq. 8.43 conversion factor as printed in the original thesis (baseline §8.1: 6.4e-9, not 4.6e-9).
# Unit: [kg m-2 s-1] / ([W m-2 K-1] [Pa]) = kg K J-1 Pa-1.
CONDENSATION_FACTOR = 6.4e-9


def eq_8_43_condensation_flux(HEC_12, VP_1, VP_2):
    """COND-01. Condensation vapour flux (switching form).

    Source: Vanthoor (2011), Eq. 8.43
    Source symbols: MV_12, HEC_12, VP_1, VP_2
    Equation: MV_12 = 0 if VP_1 < VP_2;  6.4e-9 HEC_12 (VP_1 - VP_2) if VP_1 > VP_2
    Inputs: HEC_12 [W m-2 K-1] >= 0, VP_1 [Pa] air vapour pressure at location 1,
            VP_2 [Pa] saturated vapour pressure of object 2 at its temperature
    Output: MV_12 [kg m-2 s-1] >= 0
    Note: at VP_1 == VP_2 both branches give 0, so 0 is returned.
    """
    HEC_12 = non_negative("HEC_12", HEC_12)
    VP_1, VP_2 = non_negative("VP_1", VP_1), non_negative("VP_2", VP_2)
    if VP_1 <= VP_2:
        return 0.0
    return CONDENSATION_FACTOR * HEC_12 * (VP_1 - VP_2)


def eq_8_44_condensation_flux_smooth(HEC_12, VP_1, VP_2, s_MV12):
    """COND-02 (OPTIONAL). Differentiable condensation flux.

    Source: Vanthoor (2011), Eq. 8.44
    Source symbols: MV_12, s_MV12, HEC_12, VP_1, VP_2
    Equation: MV_12 = 1 / (1 + exp(s_MV12 (VP_1 - VP_2))) * 6.4e-9 HEC_12 (VP_1 - VP_2)
    Inputs: as Eq. 8.43, plus s_MV12 [Pa-1] switch slope. s_MV12 is not guessed (baseline §8.1):
            None raises MissingParameterError.
    Output: MV_12 [kg m-2 s-1]
    """
    HEC_12 = non_negative("HEC_12", HEC_12)
    VP_1, VP_2 = non_negative("VP_1", VP_1), non_negative("VP_2", VP_2)
    s = number("s_MV12", s_MV12)
    exponent = s * (VP_1 - VP_2)
    switch = 0.0 if exponent > 700 else 1.0 / (1.0 + math.exp(exponent))   # exp overflow guard only
    return switch * CONDENSATION_FACTOR * HEC_12 * (VP_1 - VP_2)


def eq_8_45_airflow_vapour_flux(f_12, VP_1, T_1, VP_2, T_2):
    """MV-01. Vapour flux carried by an air flux.

    Source: Vanthoor (2011), Eq. 8.45
    Source symbols: MV_12, M_Water, R, f_12, VP_1, T_1, VP_2, T_2
    Equation: MV_12 = M_Water / R * f_12 * (VP_1 / (T_1 + 273.15) - VP_2 / (T_2 + 273.15))
    Inputs: f_12 [m3 m-2 s-1] >= 0, VP_1, VP_2 [Pa], T_1, T_2 [degC]
    Output: MV_12 [kg m-2 s-1], positive from 1 to 2
    Constants: M_Water [kg mol-1], R [J mol-1 K-1] (universal; constants.py)
    """
    f_12 = non_negative("f_12", f_12)
    VP_1, VP_2 = non_negative("VP_1", VP_1), non_negative("VP_2", VP_2)
    T_1, T_2 = celsius("T_1", T_1), celsius("T_2", T_2)
    return M_WATER / R_GAS * f_12 * (VP_1 / (T_1 + KELVIN_OFFSET) - VP_2 / (T_2 + KELVIN_OFFSET))
