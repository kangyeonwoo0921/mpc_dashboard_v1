"""Psychrometric conversion block, equation baseline §2 (PSY-01 .. PSY-05).

Units are explicit in every function name or docstring. hPa <-> Pa conversion is done only by
``hpa_to_pa`` / ``pa_to_hpa``; no function converts silently.
"""

import math

from ._validation import PhysicsInputError, celsius, non_negative, number, positive


def hpa_to_pa(value_hPa):
    """Unit conversion only: [hPa] -> [Pa] (baseline §2.1 "multiplication by 100")."""
    return 100.0 * number("value_hPa", value_hPa)


def pa_to_hpa(value_Pa):
    """Unit conversion only: [Pa] -> [hPa]."""
    return number("value_Pa", value_Pa) / 100.0


def saturation_vapour_pressure_hPa(T_degC):
    """PSY-01. Magnus-type saturation vapour pressure, baseline §2.1.

    Source: previously selected Magnus relation (baseline §2.1, registry PSY-01)
    Source symbol: e_s(T)
    Equation: e_s = 6.112 exp(17.67 T / (T + 243.5))
    Input: T_degC [degC]
    Output: e_s [hPa]
    Field-specific parameters: none
    """
    T = celsius("T_degC", T_degC)
    if T + 243.5 == 0:
        raise PhysicsInputError("T_degC = -243.5 makes the Magnus denominator zero")
    return 6.112 * math.exp(17.67 * T / (T + 243.5))


def saturation_vapour_pressure(T_degC):
    """PSY-01 in Pa, baseline §2.1: P_sat = 100 * e_s(T).

    Source symbol: P_sat(T)
    Input: T_degC [degC]
    Output: P_sat [Pa]
    """
    return hpa_to_pa(saturation_vapour_pressure_hPa(T_degC))


def rh_to_vp(RH_percent, T_degC):
    """PSY-02. Relative humidity -> actual vapour pressure, baseline §2.2.

    Equation: P_v = RH / 100 * P_sat(T)
    Inputs: RH_percent [%] in [0, 100], T_degC [degC]
    Output: P_v [Pa]
    """
    RH = number("RH_percent", RH_percent)
    if not 0.0 <= RH <= 100.0:
        raise PhysicsInputError(f"RH_percent must be in [0, 100], got {RH}")
    return RH / 100.0 * saturation_vapour_pressure(T_degC)


def vp_to_rh(VP_Pa, T_degC):
    """PSY-02 (definition), baseline §2.5: RH = 100 * P_v / P_sat(T).

    Inputs: VP_Pa [Pa], T_degC [degC]
    Output: RH [%]. Not clipped: a value above 100 is returned as computed.
    """
    VP = non_negative("VP_Pa", VP_Pa)
    return 100.0 * VP / saturation_vapour_pressure(T_degC)


def vp_to_humidity_ratio(VP_Pa, P_atm_Pa):
    """PSY-03. Vapour pressure -> humidity ratio, baseline §2.3.

    Equation: X = 0.622 * P_v / (P_atm - P_v)
    Inputs: VP_Pa [Pa], P_atm_Pa [Pa] (no fixed value: measured or configured, baseline §2.3)
    Output: X [kg water / kg dry air]
    """
    VP = non_negative("VP_Pa", VP_Pa)
    P_atm = positive("P_atm_Pa", P_atm_Pa)
    if VP >= P_atm:
        raise PhysicsInputError(f"VP_Pa ({VP}) must be below P_atm_Pa ({P_atm})")
    return 0.622 * VP / (P_atm - VP)


def humidity_ratio_to_vp(X_kg_per_kg, P_atm_Pa):
    """PSY-03 inverse, baseline §2.4: P_v = X * P_atm / (0.622 + X).

    Inputs: X_kg_per_kg [kg water / kg dry air], P_atm_Pa [Pa]
    Output: P_v [Pa]
    """
    X = non_negative("X_kg_per_kg", X_kg_per_kg)
    P_atm = positive("P_atm_Pa", P_atm_Pa)
    return X * P_atm / (0.622 + X)


def vpd(T_degC, VP_Pa):
    """PSY-04. Vapour pressure deficit, baseline §2.6: VPD = P_sat(T) - P_v.

    Inputs: T_degC [degC], VP_Pa [Pa]
    Output: VPD [Pa]. Not clipped (negative when supersaturated).
    """
    return saturation_vapour_pressure(T_degC) - non_negative("VP_Pa", VP_Pa)


def dew_point(VP_Pa):
    """PSY-05. Dew point by algebraic inversion of PSY-01, baseline §2.7.

    Equation: gamma = ln(e / 6.112) with e in hPa;  T_dew = 243.5 gamma / (17.67 - gamma)
    Input: VP_Pa [Pa] (converted to hPa explicitly by pa_to_hpa)
    Output: T_dew [degC]
    """
    e_hPa = pa_to_hpa(positive("VP_Pa", VP_Pa))
    gamma = math.log(e_hPa / 6.112)
    if gamma >= 17.67:
        raise PhysicsInputError("vapour pressure outside the invertible range of PSY-01")
    return 243.5 * gamma / (17.67 - gamma)
