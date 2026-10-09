"""Canopy transpiration from Vanthoor (2011) / Stanghellini (1987).

Eq. 8.47 (CROP-01), Eq. 8.48 (CROP-02), Eq. 8.49 (CROP-03 structure).
Eq. 8.50 (resistance-factor functions rf(.)) is NOT reproduced in the equation baseline, so it is
NOT implemented: the three rf values are inputs to Eq. 8.49 (open question Q-6).
"""

from ._validation import non_negative, positive


def eq_8_47_transpiration(VEC_can_air, VP_can, VP_air):
    """CROP-01. Canopy transpiration vapour flux.

    Source: Vanthoor (2011), Eq. 8.47
    Source symbols: MV_CanAir, VEC_CanAir, VP_Can, VP_Air
    Equation: MV_CanAir = VEC_CanAir (VP_Can - VP_Air)
    Inputs: VEC_can_air [kg m-2 Pa-1 s-1] >= 0, VP_can [Pa] saturated vapour pressure at canopy
            temperature (supplied by caller; see Q-7), VP_air [Pa]
    Output: MV_can_air [kg m-2 s-1]
    """
    VEC = non_negative("VEC_can_air", VEC_can_air)
    return VEC * (non_negative("VP_can", VP_can) - non_negative("VP_air", VP_air))


def eq_8_48_vec_can_air(rho_air, c_p_air, LAI, delta_H, gamma, r_b, r_s):
    """CROP-02. Canopy vapour-exchange coefficient.

    Source: Vanthoor (2011), Eq. 8.48 (Stanghellini 1987)
    Source symbols: VEC_CanAir, rho_Air, c_p,Air, LAI, Delta_H, gamma, r_b, r_s
    Equation: VEC_CanAir = 2 rho_Air c_p,Air LAI / (Delta_H gamma (r_b + r_s))
    Inputs: rho_air [kg m-3], c_p_air [J kg-1 K-1], LAI [m2 leaf m-2 floor], delta_H [J kg-1],
            gamma [Pa K-1], r_b [s m-1], r_s [s m-1]
    Output: VEC_can_air [kg m-2 Pa-1 s-1]
    Field-specific: LAI (measurement or crop schedule), r_b (source or calibration), r_s (Eq. 8.49)
    """
    rho_air, c_p_air = positive("rho_air", rho_air), positive("c_p_air", c_p_air)
    LAI = non_negative("LAI", LAI)
    delta_H, gamma = positive("delta_H", delta_H), positive("gamma", gamma)
    r_b, r_s = non_negative("r_b", r_b), non_negative("r_s", r_s)
    resistance = positive("r_b + r_s", r_b + r_s)
    return 2.0 * rho_air * c_p_air * LAI / (delta_H * gamma * resistance)


def eq_8_49_stomatal_resistance(r_s_min, rf_R_can, rf_CO2_air, rf_VPD_can_air):
    """CROP-03 (FIXED / PARAMS REQUIRED). Stomatal resistance structure.

    Source: Vanthoor (2011), Eq. 8.49
    Source symbols: r_s, r_s,min, rf(R_Can), rf(CO2_Air), rf(VP_Can - VP_Air)
    Equation: r_s = r_s,min * rf(R_Can) * rf(CO2_Air) * rf(VP_Can - VP_Air)
    Inputs: r_s_min [s m-1]; rf_* [-] values of the Eq. 8.50 factor functions, evaluated elsewhere
            (Eq. 8.50 not implemented here; see module docstring)
    Output: r_s [s m-1]
    """
    return (non_negative("r_s_min", r_s_min) * non_negative("rf_R_can", rf_R_can)
            * non_negative("rf_CO2_air", rf_CO2_air) * non_negative("rf_VPD_can_air", rf_VPD_can_air))
