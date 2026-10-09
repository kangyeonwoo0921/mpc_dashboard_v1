"""Diffusive-material optics from Cabrera et al. (2009), baseline §17.

DIFF-01 (tau_b-b definition), DIFF-02 (Eq. 6-7), DIFF-03 (Eq. 8).

These describe a highly diffusing cover film, not a movable screen. The relation
u_diffuse_screen -> (tau_bb, tau_bd, tau_d) for partial opening is UNRESOLVED (DIFF-OPEN): there is
no function here that takes the screen opening, and no interpolation between open/closed states.
Cabrera's fitted power-law coefficients (baseline §17.5) are not used.
"""

from ._validation import PhysicsInputError, non_negative, number, positive


def direct_to_direct_transmittance(I_i, I_o):
    """DIFF-01. Direct-to-direct transmittance (Cabrera definition).

    Source: Cabrera et al. (2009), definition of tau_b-b
    Equation: tau_b-b = I_i / I_o
    Inputs: I_i [W m-2] inside direct radiation, I_o [W m-2] outside direct radiation (> 0)
    Output: tau_bb [-]
    """
    return non_negative("I_i", I_i) / positive("I_o", I_o)


def direct_converted_to_diffuse(D_i, tau_d, D_o):
    """DIFF-02. Direct radiation converted into diffuse radiation.

    Source: Cabrera et al. (2009), Eq. 6
    Equation: D* = D_i - tau_d D_o
    Inputs: D_i [W m-2] total inside diffuse, tau_d [-] diffuse transmittance (overcast-determined),
            D_o [W m-2] outside diffuse
    Output: D_star [W m-2]. Not clipped.
    """
    tau_d = number("tau_d", tau_d)
    if tau_d < 0:
        raise PhysicsInputError("tau_d must be >= 0")
    return non_negative("D_i", D_i) - tau_d * non_negative("D_o", D_o)


def direct_to_diffuse_transmittance(D_i, tau_d, D_o, I_o):
    """DIFF-02. Direct-to-diffuse transmittance.

    Source: Cabrera et al. (2009), Eq. 7
    Equation: tau_b-d = D* / I_o = (D_i - tau_d D_o) / I_o
    Inputs: as Eq. 6, plus I_o [W m-2] (> 0)
    Output: tau_bd [-]
    """
    return direct_converted_to_diffuse(D_i, tau_d, D_o) / positive("I_o", I_o)


def total_direct_transmittance(tau_bb, tau_bd):
    """DIFF-03. Total direct transmittance.

    Source: Cabrera et al. (2009), Eq. 8
    Equation: tau_b = tau_b-b + tau_b-d
    Inputs: tau_bb, tau_bd [-]
    Output: tau_b [-]
    """
    return non_negative("tau_bb", tau_bb) + number("tau_bd", tau_bd)
