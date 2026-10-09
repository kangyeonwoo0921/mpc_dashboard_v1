"""Heat-transfer equations from Vanthoor (2011), Chapter 8.

Eq. 8.38 (FIR-01), Eq. 8.40 (HEAT-01), Eq. 8.42 (LAT-01), Eq. 8.19 (COVER-01, conditional).
"""

from ._validation import celsius, fraction, non_negative, number, positive
from .constants import KELVIN_OFFSET, SIGMA


def eq_8_38_fir_flux(A_i, eps_i, eps_j, F_ij, T_i, T_j):
    """FIR-01. Long-wave (thermal infrared) radiation exchange.

    Source: Vanthoor (2011), Eq. 8.38
    Source symbols: FIR_ij, A_i, epsilon_i, epsilon_j, F_ij, sigma, T_i, T_j
    Equation: FIR_ij = A_i eps_i eps_j F_ij sigma [(T_i + 273.15)^4 - (T_j + 273.15)^4]
    Inputs: A_i [m2 m-2 floor], eps_i, eps_j [-] in [0, 1], F_ij [-] in [0, 1], T_i, T_j [degC]
    Output: FIR_ij [W m-2], positive from i to j
    Field-specific parameters: A_i, eps_i, eps_j, F_ij (surface-pair specific; none guessed)
    Applicability: only if long-wave exchange between the represented surfaces is modelled
    """
    A_i = non_negative("A_i", A_i)
    eps_i, eps_j, F_ij = fraction("eps_i", eps_i), fraction("eps_j", eps_j), fraction("F_ij", F_ij)
    T_i, T_j = celsius("T_i", T_i), celsius("T_j", T_j)
    return A_i * eps_i * eps_j * F_ij * SIGMA * ((T_i + KELVIN_OFFSET) ** 4 - (T_j + KELVIN_OFFSET) ** 4)


def eq_8_40_sensible_heat_flux(HEC_12, T_1, T_2):
    """HEAT-01. Convective/conductive heat flux.

    Source: Vanthoor (2011), Eq. 8.40
    Source symbols: H_12, HEC_12, T_1, T_2
    Equation: H_12 = HEC_12 (T_1 - T_2)
    Inputs: HEC_12 [W m-2 K-1] >= 0, T_1, T_2 [degC] (only the difference is used, so K == degC)
    Output: H_12 [W m-2], positive from 1 to 2
    Field-specific parameters: HEC_12 must come from its source equation/table or calibration
    """
    HEC_12 = non_negative("HEC_12", HEC_12)
    return HEC_12 * (celsius("T_1", T_1) - celsius("T_2", T_2))


def eq_8_42_latent_heat_flux(delta_H, MV_12):
    """LAT-01. Latent heat flux associated with a vapour flux.

    Source: Vanthoor (2011), Eq. 8.42
    Source symbols: L_12, Delta_H, MV_12
    Equation: L_12 = Delta_H * MV_12
    Inputs: delta_H [J kg-1] > 0, MV_12 [kg m-2 s-1]
    Output: L_12 [W m-2]
    """
    return positive("delta_H", delta_H) * number("MV_12", MV_12)


def eq_8_19_cover_conduction_hec(h_roof, lambda_roof, u_shade_perm, h_shade_perm, lambda_shade_perm):
    """COVER-01 (CONDITIONAL TO LAYER MATCH). Lumped cover conduction coefficient.

    Source: Vanthoor (2011), Eq. 8.19
    Source symbols: HEC_Cov,in_Cov,e, h_Rf, lambda_Rf, U_ShScrPer, h_ShScrPer, lambda_ShScrPer
    Equation: HEC = 1 / (h_Rf / lambda_Rf + U_ShScrPer h_ShScrPer / lambda_ShScrPer)
    Inputs: h_roof [m] > 0, lambda_roof [W m-1 K-1] > 0, u_shade_perm [-] in [0, 1],
            h_shade_perm [m] >= 0, lambda_shade_perm [W m-1 K-1] > 0
    Output: HEC_cov_in_cov_e [W m-2 K-1]
    Applicability: only after the site cover is mapped to these layers (baseline §16.1). The
        semi-permanent shading layer must not be copied in if it does not exist on site.
    """
    h_roof, lambda_roof = positive("h_roof", h_roof), positive("lambda_roof", lambda_roof)
    u_perm = fraction("u_shade_perm", u_shade_perm)
    h_perm, lambda_perm = non_negative("h_shade_perm", h_shade_perm), positive("lambda_shade_perm", lambda_shade_perm)
    return 1.0 / (h_roof / lambda_roof + u_perm * h_perm / lambda_perm)
