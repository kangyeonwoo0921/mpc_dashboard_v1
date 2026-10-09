"""Shade-screen optics and thermal-screen equations from Vanthoor (2011), Chapter 8.

Eq. 8.14-8.15 (SHADE-01), Eq. 8.16-8.17 (SHADE-02), Eq. 8.39 (THERMAL-01, CONDITIONAL),
Eq. 8.41 (THERMAL-02, CONDITIONAL).

The control arguments are Vanthoor's screen controls U in [0, 1]. How the field "opening %"
(100 = retracted) maps to U is not defined in the baseline (open question Q-1); no mapping is
implemented here. Material coefficients are never defaulted (baseline §14.4, §21).
"""

import math

from ._validation import PhysicsInputError, celsius, fraction, non_negative, positive
from .constants import G


def _layers_denominator(rho_1, rho_2):
    denominator = 1.0 - rho_1 * rho_2
    if denominator <= 0:
        raise PhysicsInputError("1 - rho_1 rho_2 must be > 0")
    return denominator


def eq_8_14_double_layer_tau(tau_1, rho_1, tau_2, rho_2):
    """SHADE-01. Transmission of two layers (EN 410 double layer).

    Source: Vanthoor (2011), Eq. 8.14
    Equation: tau_12 = tau_1 tau_2 / (1 - rho_1 rho_2)
    Inputs: tau_1, rho_1, tau_2, rho_2 [-] in [0, 1]
    Output: tau_12 [-]
    """
    tau_1, rho_1 = fraction("tau_1", tau_1), fraction("rho_1", rho_1)
    tau_2, rho_2 = fraction("tau_2", tau_2), fraction("rho_2", rho_2)
    return tau_1 * tau_2 / _layers_denominator(rho_1, rho_2)


def eq_8_15_double_layer_rho(tau_1, rho_1, rho_2):
    """SHADE-01. Reflection of two layers (EN 410 double layer).

    Source: Vanthoor (2011), Eq. 8.15
    Equation: rho_12 = rho_1 + tau_1^2 rho_2 / (1 - rho_1 rho_2)
    Inputs: tau_1, rho_1, rho_2 [-] in [0, 1]
    Output: rho_12 [-]
    """
    tau_1, rho_1, rho_2 = fraction("tau_1", tau_1), fraction("rho_1", rho_1), fraction("rho_2", rho_2)
    return rho_1 + tau_1 ** 2 * rho_2 / _layers_denominator(rho_1, rho_2)


def _shade_terms(u_shade_screen, tau_shade, rho_shade, u_shade_perm, tau_shade_perm, rho_shade_perm):
    u_shade_screen, u_perm = fraction("u_shade_screen", u_shade_screen), fraction("u_shade_perm", u_shade_perm)
    tau_shade, rho_shade = fraction("tau_shade", tau_shade), fraction("rho_shade", rho_shade)
    tau_perm, rho_perm = fraction("tau_shade_perm", tau_shade_perm), fraction("rho_shade_perm", rho_shade_perm)
    movable = 1.0 - u_shade_screen * (1.0 - tau_shade)
    permanent = 1.0 - u_perm * (1.0 - tau_perm)
    denominator = _layers_denominator(u_shade_screen * rho_shade, u_perm * rho_perm)
    return u_shade_screen, rho_shade, u_perm, rho_perm, movable, permanent, denominator


def eq_8_16_shade_screen_tau(u_shade_screen, tau_shade, rho_shade, u_shade_perm, tau_shade_perm, rho_shade_perm):
    """SHADE-02. Transmission of movable shade screen + semi-permanent shading layer (PAR form).

    Source: Vanthoor (2011), Eq. 8.16 ("NIR calculated similarly")
    Source symbols: tau_ShScr_ShScrPerPAR, U_ShScr, tau_ShScrPAR, rho_ShScrPAR,
                    U_ShScrPer, tau_ShScrPerPAR, rho_ShScrPerPAR
    Equation: tau = (1 - U_ShScr (1 - tau_ShScr)) (1 - U_ShScrPer (1 - tau_ShScrPer))
                    / (1 - U_ShScr rho_ShScr U_ShScrPer rho_ShScrPer)
    Inputs: u_shade_screen, u_shade_perm [-] controls in [0, 1]; tau_*, rho_* [-] material coefficients
            in [0, 1] for one waveband (manufacturer or measurement only)
    Output: tau [-]
    Open question Q-2: the site has no confirmed semi-permanent shading layer.
    """
    _, _, _, _, movable, permanent, denominator = _shade_terms(
        u_shade_screen, tau_shade, rho_shade, u_shade_perm, tau_shade_perm, rho_shade_perm)
    return movable * permanent / denominator


def eq_8_17_shade_screen_rho(u_shade_screen, tau_shade, rho_shade, u_shade_perm, tau_shade_perm, rho_shade_perm):
    """SHADE-02. Reflection of movable shade screen + semi-permanent shading layer (PAR form).

    Source: Vanthoor (2011), Eq. 8.17
    Equation: rho = U_ShScr rho_ShScr
                    + (1 - U_ShScr (1 - tau_ShScr))^2 U_ShScrPer rho_ShScrPer
                      / (1 - U_ShScr rho_ShScr U_ShScrPer rho_ShScrPer)
    Inputs/Output: as Eq. 8.16; output rho [-]
    """
    u_shade_screen, rho_shade, u_perm, rho_perm, movable, _, denominator = _shade_terms(
        u_shade_screen, tau_shade, rho_shade, u_shade_perm, tau_shade_perm, rho_shade_perm)
    return u_shade_screen * rho_shade + movable ** 2 * u_perm * rho_perm / denominator


def eq_8_39_thermal_screen_fir_tau(u_thermal_screen, tau_thermal_screen_FIR):
    """THERMAL-01 (CONDITIONAL). FIR transmission of a thermal screen.

    Source: Vanthoor (2011), Eq. 8.39
    Source symbols: tau^U_ThScrFIR, U_ThScr, tau_ThScrFIR
    Equation: tau^U = 1 - U_ThScr (1 - tau_ThScrFIR)
    Inputs: u_thermal_screen [-] in [0, 1], tau_thermal_screen_FIR [-] in [0, 1]
    Output: tau^U [-]
    Activation: only when the field shade screen is confirmed as a thermal screen and its FIR
        property is known (baseline §15). Applying it to the shade screen is a hardware-role mapping.
    """
    u = fraction("u_thermal_screen", u_thermal_screen)
    return 1.0 - u * (1.0 - fraction("tau_thermal_screen_FIR", tau_thermal_screen_FIR))


def eq_8_41_thermal_screen_airflow(u_thermal_screen, K_thermal_screen, T_air, T_out,
                                   rho_air_mean, rho_air, rho_out, g=G):
    """THERMAL-02 (CONDITIONAL). Airflow through a thermal screen, as written in baseline §15.2.

    Source: Vanthoor (2011), Eq. 8.41 as transcribed in the equation baseline
    Source symbols: f_ThScr, U_ThScr, K_ThScr, T_Air, T_Out, rho^Mean_Air, rho_Air, rho_Out, g
    Equation: f = U K |T_Air - T_Out|^0.66
                  + (1 - U) / rho_mean * [0.5 rho_mean (1 - U) g |rho_Air - rho_Out|]^0.5
    Inputs: u_thermal_screen [-], K_thermal_screen [m3 m-2 K-0.66 s-1] (calibration_required),
            T_air, T_out [degC], rho_air_mean, rho_air, rho_out [kg m-3], g [m s-2]
    Output: f_ThScr [m3 m-2 s-1] (stated in the baseline; see unit audit Q-5)
    Open question Q-5: the baseline uses T_Out / rho_Out; the variables on the other side of the
        screen must be confirmed against the thesis before activation.
    """
    u = fraction("u_thermal_screen", u_thermal_screen)
    K = non_negative("K_thermal_screen", K_thermal_screen)
    T_air, T_out = celsius("T_air", T_air), celsius("T_out", T_out)
    rho_mean = positive("rho_air_mean", rho_air_mean)
    rho_air, rho_out, g = positive("rho_air", rho_air), positive("rho_out", rho_out), positive("g", g)
    return (u * K * abs(T_air - T_out) ** 0.66
            + (1.0 - u) / rho_mean * math.sqrt(0.5 * rho_mean * (1.0 - u) * g * abs(rho_air - rho_out)))
