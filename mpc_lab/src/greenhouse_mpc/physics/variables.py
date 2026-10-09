"""Canonical variable registry (task Step 2). Single source of truth for names, units and sources.

Run ``python -m greenhouse_mpc.physics.variables`` to print docs/VARIABLE_REGISTRY.md.
"""

from dataclasses import dataclass

CATEGORIES = ("STATE", "CONTROL", "DISTURBANCE", "PARAMETER", "DERIVED", "FLUX", "CONSTANT")
V = "Vanthoor (2011)"
BL = "equation baseline"


@dataclass(frozen=True)
class Variable:
    name: str
    source_symbol: str
    category: str
    description: str
    unit: str
    bounds: tuple | None
    source: str
    required: bool
    status: str

    def __post_init__(self):
        if self.category not in CATEGORIES:
            raise ValueError(f"{self.name}: bad category {self.category}")
        if not self.unit:
            raise ValueError(f"{self.name}: unit must not be empty")


def _v(name, symbol, category, description, unit, bounds, source, required, status):
    return Variable(name, symbol, category, description, unit, bounds, source, required, status)


REGISTRY = (
    # --- STATE ---------------------------------------------------------------------------------
    _v("T_air", "T_Air", "STATE", "greenhouse air temperature", "degC", None, f"{V} Eq. 8.2", True, "fixed"),
    _v("VP_air", "VP_Air", "STATE", "greenhouse air vapour pressure (dynamic moisture state)", "Pa", (0, None), f"{V} Eq. 8.10", True, "fixed"),
    # --- CONTROL -------------------------------------------------------------------------------
    _v("u_roof", "U_Roof", "CONTROL", "roof-vent aperture control", "-", (0, 1), f"{V} Eq. 8.65, 8.68", True, "fixed; field % mapping unresolved (Q-1)"),
    _v("u_shade_screen", "U_ShScr", "CONTROL", "movable shade-screen control", "-", (0, 1), f"{V} Eq. 8.16, 8.17", True, "fixed; field % mapping unresolved (Q-1)"),
    _v("u_thermal_screen", "U_ThScr", "CONTROL", "thermal-screen control (field shade screen in its night role)", "-", (0, 1), f"{V} Eq. 8.39, 8.41", False, "conditional (hardware-role mapping)"),
    _v("u_diffuse_screen", "U_Diffuse", "CONTROL", "diffuse-screen state/control", "-", (0, 1), f"{BL} §1.2", True, "no source optical relation (DIFF-OPEN)"),
    # --- DISTURBANCE ---------------------------------------------------------------------------
    _v("T_out", "T_Out", "DISTURBANCE", "outside air temperature", "degC", None, f"{V} Eq. 8.65", True, "fixed"),
    _v("VP_out", "VP_Out", "DISTURBANCE", "outside air vapour pressure", "Pa", (0, None), f"{BL} §1.3", True, "fixed"),
    _v("RH_out", "RH (outside)", "DISTURBANCE", "measured outside relative humidity, converted by PSY-02", "%", (0, 100), f"{BL} §2.2", True, "measurement absent in current live data"),
    _v("wind_speed", "v_Wind", "DISTURBANCE", "wind speed", "m s-1", (0, None), f"{V} Eq. 8.65, 8.71", True, "fixed"),
    _v("wind_direction", "theta_Wind", "DISTURBANCE", "wind direction (stored for future C_w selection only)", "deg", (0, 360), f"{BL} §13", False, "no function (WINDDIR-01 unresolved)"),
    _v("solar_radiation", "I_solar", "DISTURBANCE", "global radiation at the site sensor", "W m-2", (0, None), f"{BL} §1.3", True, "fixed"),
    _v("rain", "rain", "DISTURBANCE", "rain state", "-", None, f"{BL} §1.3", True, "fixed"),
    _v("time", "t", "DISTURBANCE", "time", "s", None, f"{BL} §1.3", True, "fixed"),
    _v("T_mean", "T_bar", "DISTURBANCE", "mean greenhouse/outdoor air temperature in Eq. 8.65", "degC", None, f"{V} Eq. 8.65", True, "definition to confirm (Q-3)"),
    _v("T_can", "T_Can", "DISTURBANCE", "canopy temperature", "degC", None, f"{BL} §1.3", False, "source of value unresolved"),
    # --- PARAMETER (field-specific; never defaulted) -------------------------------------------
    _v("A_floor", "A_Flr", "PARAMETER", "greenhouse floor area", "m2", (0, None), f"{V} Eq. 8.65", True, "field_required"),
    _v("A_roof", "A_Roof", "PARAMETER", "maximum roof-vent area", "m2", (0, None), f"{V} Eq. 8.65, 8.68", True, "field_required"),
    _v("h_vent", "h_Vent", "PARAMETER", "vertical dimension of one vent opening", "m", (0, None), f"{V} Eq. 8.65", True, "field_required"),
    _v("C_d", "C_d", "PARAMETER", "discharge coefficient", "-", (0, None), f"{V} Eq. 8.65", True, "calibration_or_geometry_matched_source"),
    _v("C_w", "C_w", "PARAMETER", "global wind-pressure coefficient", "-", (0, None), f"{V} Eq. 8.65", True, "calibration_or_geometry_matched_source"),
    _v("c_leakage", "c_leakage", "PARAMETER", "leakage coefficient", "see Q-4 (branch-dependent)", (0, None), f"{V} Eq. 8.71", True, "calibration_required"),
    _v("h_roof", "h_Rf", "PARAMETER", "roof (cover) thickness", "m", (0, None), f"{V} Eq. 8.19", False, "field_required; conditional"),
    _v("lambda_roof", "lambda_Rf", "PARAMETER", "roof thermal conductivity", "W m-1 K-1", (0, None), f"{V} Eq. 8.19", False, "manufacturer_or_calibration"),
    _v("u_shade_perm", "U_ShScrPer", "PARAMETER", "semi-permanent shading-layer state", "-", (0, 1), f"{V} Eq. 8.16, 8.17, 8.19", False, "existence on site unconfirmed (Q-2)"),
    _v("h_shade_perm", "h_ShScrPer", "PARAMETER", "semi-permanent shading-layer thickness", "m", (0, None), f"{V} Eq. 8.19", False, "conditional (Q-2)"),
    _v("lambda_shade_perm", "lambda_ShScrPer", "PARAMETER", "semi-permanent shading-layer conductivity", "W m-1 K-1", (0, None), f"{V} Eq. 8.19", False, "conditional (Q-2)"),
    _v("tau_shade", "tau_ShScrPAR (NIR similarly)", "PARAMETER", "shade-screen transmission coefficient (one waveband)", "-", (0, 1), f"{V} Eq. 8.16, 8.17", True, "manufacturer_or_measurement"),
    _v("rho_shade", "rho_ShScrPAR (NIR similarly)", "PARAMETER", "shade-screen reflection coefficient (one waveband)", "-", (0, 1), f"{V} Eq. 8.16, 8.17", True, "manufacturer_or_measurement"),
    _v("tau_shade_perm", "tau_ShScrPerPAR", "PARAMETER", "semi-permanent layer transmission", "-", (0, 1), f"{V} Eq. 8.16, 8.17", False, "conditional (Q-2)"),
    _v("rho_shade_perm", "rho_ShScrPerPAR", "PARAMETER", "semi-permanent layer reflection", "-", (0, 1), f"{V} Eq. 8.16, 8.17", False, "conditional (Q-2)"),
    _v("tau_thermal_screen_FIR", "tau_ThScrFIR", "PARAMETER", "thermal-screen FIR transmission", "-", (0, 1), f"{V} Eq. 8.39", False, "manufacturer_or_measurement_if_used_as_thermal_screen"),
    _v("K_thermal_screen", "K_ThScr", "PARAMETER", "screen-flux coefficient (permeability)", "m3 m-2 K-0.66 s-1", (0, None), f"{V} Eq. 8.41", False, "calibration_required_if_activated"),
    _v("tau_bb", "tau_b-b", "PARAMETER", "diffuse-screen direct-to-direct transmittance", "-", (0, None), "Cabrera et al. (2009)", False, "manufacturer_or_measurement"),
    _v("tau_bd", "tau_b-d", "PARAMETER", "diffuse-screen direct-to-diffuse transmittance", "-", None, "Cabrera et al. (2009) Eq. 7", False, "manufacturer_or_measurement"),
    _v("tau_d", "tau_d", "PARAMETER", "diffuse transmittance (overcast-determined)", "-", (0, None), "Cabrera et al. (2009) Eq. 6", False, "manufacturer_or_measurement"),
    _v("LAI", "LAI", "PARAMETER", "leaf area index", "m2 m-2", (0, None), f"{V} Eq. 8.48", True, "measurement_or_crop_schedule"),
    _v("r_b", "r_b", "PARAMETER", "canopy boundary-layer resistance", "s m-1", (0, None), f"{V} Eq. 8.48", True, "source_or_calibration"),
    _v("r_s_min", "r_s,min", "PARAMETER", "minimum canopy stomatal resistance", "s m-1", (0, None), f"{V} Eq. 8.49", True, "source_or_calibration"),
    _v("rf_R_can", "rf(R_Can)", "PARAMETER", "stomatal resistance factor for radiation", "-", (0, None), f"{V} Eq. 8.49-8.50", True, "Eq. 8.50 not in baseline (Q-6)"),
    _v("rf_CO2_air", "rf(CO2_Air)", "PARAMETER", "stomatal resistance factor for CO2", "-", (0, None), f"{V} Eq. 8.49-8.50", True, "Eq. 8.50 not in baseline (Q-6)"),
    _v("rf_VPD_can_air", "rf(VP_Can - VP_Air)", "PARAMETER", "stomatal resistance factor for vapour pressure difference", "-", (0, None), f"{V} Eq. 8.49-8.50", True, "Eq. 8.50 not in baseline (Q-6)"),
    _v("s_MV12", "s_MV12", "PARAMETER", "switch slope of the smoothed condensation function", "Pa-1", None, f"{V} Eq. 8.44", False, "optional; not guessed"),
    _v("cap_air", "cap_Air", "PARAMETER", "heat capacity of greenhouse air per floor area", "J K-1 m-2", (0, None), f"{V} Eq. 8.2", True, "definition not in baseline (Q-8)"),
    _v("cap_VP_air", "cap_VPAir", "PARAMETER", "vapour capacity of greenhouse air per floor area", "kg m-2 Pa-1", (0, None), f"{V} Eq. 8.10", True, "definition not in baseline (Q-8)"),
    _v("HEC_12", "HEC_12", "PARAMETER", "heat exchange coefficient between objects 1 and 2", "W m-2 K-1", (0, None), f"{V} Eq. 8.40, 8.43", True, "from its source equation/table or calibration"),
    _v("A_i", "A_i", "PARAMETER", "surface area of object i per floor area", "m2 m-2", (0, None), f"{V} Eq. 8.38", False, "surface-pair specific"),
    _v("eps_i", "epsilon_i", "PARAMETER", "FIR emission coefficient of object i", "-", (0, 1), f"{V} Eq. 8.38", False, "surface specific"),
    _v("eps_j", "epsilon_j", "PARAMETER", "FIR emission coefficient of object j", "-", (0, 1), f"{V} Eq. 8.38", False, "surface specific"),
    _v("F_ij", "F_ij", "PARAMETER", "view factor from i to j", "-", (0, 1), f"{V} Eq. 8.38", False, "surface-pair specific"),
    _v("rho_air", "rho_Air", "PARAMETER", "greenhouse air density", "kg m-3", (0, None), f"{V} Eq. 8.41, 8.48", True, "condition-dependent; not defaulted (Q-11)"),
    _v("rho_air_mean", "rho_Air^Mean", "PARAMETER", "mean air density across the screen", "kg m-3", (0, None), f"{V} Eq. 8.41", False, "conditional"),
    _v("rho_out", "rho_Out", "PARAMETER", "air density on the other side of the screen (as transcribed)", "kg m-3", (0, None), f"{V} Eq. 8.41", False, "conditional (Q-5)"),
    _v("c_p_air", "c_p,Air", "PARAMETER", "specific heat capacity of air", "J kg-1 K-1", (0, None), f"{V} Eq. 8.48", True, "not defaulted (Q-11)"),
    _v("delta_H", "Delta_H", "PARAMETER", "latent heat of evaporation", "J kg-1", (0, None), f"{V} Eq. 8.42, 8.48", True, "not defaulted (Q-11)"),
    _v("gamma", "gamma", "PARAMETER", "psychrometric constant", "Pa K-1", (0, None), f"{V} Eq. 8.48", True, "not defaulted (Q-11)"),
    _v("P_atm", "P_atm", "PARAMETER", "atmospheric pressure", "Pa", (0, None), f"{BL} PSY-03", True, "measured_or_configured"),
    # --- DERIVED -------------------------------------------------------------------------------
    _v("RH_air", "RH_Air", "DERIVED", "greenhouse relative humidity (measured input / derived output)", "%", (0, None), f"{BL} PSY-02", True, "fixed"),
    _v("X_air", "X_i", "DERIVED", "greenhouse humidity ratio", "kg kg-1 (water per dry air)", (0, None), f"{BL} PSY-03", False, "fixed"),
    _v("VPD_air", "VPD_Air", "DERIVED", "greenhouse vapour pressure deficit", "Pa", None, f"{BL} PSY-04", False, "fixed"),
    _v("T_dew_air", "T_dew", "DERIVED", "greenhouse dew-point temperature", "degC", None, f"{BL} PSY-05", False, "fixed"),
    _v("P_sat", "P_sat(T)", "DERIVED", "saturation vapour pressure", "Pa", (0, None), f"{BL} PSY-01", True, "fixed"),
    _v("e_s_hPa", "e_s(T)", "DERIVED", "saturation vapour pressure in source unit", "hPa", (0, None), f"{BL} PSY-01", False, "fixed"),
    _v("VP_can", "VP_Can", "DERIVED", "saturated vapour pressure at canopy temperature", "Pa", (0, None), f"{V} Eq. 8.47", True, "saturation formula to confirm (Q-7)"),
    _v("VEC_can_air", "VEC_CanAir", "DERIVED", "canopy vapour-exchange coefficient", "kg m-2 Pa-1 s-1", (0, None), f"{V} Eq. 8.48", True, "fixed"),
    _v("r_s", "r_s", "DERIVED", "canopy stomatal resistance", "s m-1", (0, None), f"{V} Eq. 8.49", True, "fixed / params required"),
    _v("A_roof_U", "A^U_Roof", "DERIVED", "roof-vent aperture", "m2", (0, None), f"{V} Eq. 8.68", False, "fixed"),
    _v("tau_shade_combined", "tau_ShScr_ShScrPerPAR", "DERIVED", "transmission of shade screen + semi-permanent layer", "-", (0, 1), f"{V} Eq. 8.16", False, "fixed"),
    _v("rho_shade_combined", "rho_ShScr_ShScrPerPAR", "DERIVED", "reflection of shade screen + semi-permanent layer", "-", (0, 1), f"{V} Eq. 8.17", False, "fixed"),
    _v("tau_thermal_screen_FIR_U", "tau^U_ThScrFIR", "DERIVED", "FIR transmission at screen control", "-", (0, 1), f"{V} Eq. 8.39", False, "conditional"),
    _v("HEC_cov_in_cov_e", "HEC_Cov,in_Cov,e", "DERIVED", "lumped cover conduction coefficient", "W m-2 K-1", (0, None), f"{V} Eq. 8.19", False, "conditional to layer match"),
    _v("D_star", "D*", "DERIVED", "direct radiation converted into diffuse", "W m-2", None, "Cabrera et al. (2009) Eq. 6", False, "fixed physics"),
    _v("tau_b", "tau_b", "DERIVED", "total direct transmittance", "-", None, "Cabrera et al. (2009) Eq. 8", False, "fixed physics"),
    _v("I_i", "I_i", "DISTURBANCE", "inside direct radiation", "W m-2", (0, None), "Cabrera et al. (2009)", False, "measurement/ray-model input"),
    _v("I_o", "I_o", "DISTURBANCE", "outside direct radiation", "W m-2", (0, None), "Cabrera et al. (2009)", False, "measurement/ray-model input"),
    _v("D_i", "D_i", "DISTURBANCE", "inside diffuse radiation", "W m-2", (0, None), "Cabrera et al. (2009)", False, "measurement/ray-model input"),
    _v("D_o", "D_o", "DISTURBANCE", "outside diffuse radiation", "W m-2", (0, None), "Cabrera et al. (2009)", False, "measurement/ray-model input"),
    # --- FLUX ----------------------------------------------------------------------------------
    *[_v(n, s, "FLUX", d, "W m-2", None, f"{V} Eq. 8.2", False, st) for n, s, d, st in (
        ("H_can_air", "H_CanAir", "sensible heat canopy -> air", "active"),
        ("H_pad_air", "H_PadAir", "pad outlet air -> air", "inactive (not confirmed)"),
        ("H_mech_air", "H_MechAir", "mechanical cooling -> air", "inactive (not confirmed)"),
        ("H_pipe_air", "H_PipeAir", "heating pipes -> air", "inactive (Q-9)"),
        ("H_pas_air", "H_PasAir", "passive buffer -> air", "inactive (not confirmed)"),
        ("H_blow_air", "H_BlowAir", "direct air heater -> air", "inactive (Q-9)"),
        ("R_glob_sun_air", "R_Glob_SunAir", "global radiation absorbed by construction, released to air", "active"),
        ("H_air_flr", "H_AirFlr", "air -> floor", "active"),
        ("H_air_th_scr", "H_AirThScr", "air -> thermal screen", "inactive (conditional)"),
        ("H_air_out", "H_AirOut", "air -> outside", "active"),
        ("H_air_top", "H_AirTop", "air -> top compartment", "inactive (Q-10)"),
        ("H_air_out_pad", "H_AirOut_Pad", "pad/fan air exchange", "inactive (not confirmed)"),
        ("L_air_fog", "L_AirFog", "latent heat of fog evaporation", "inactive (not confirmed)"),
    )],
    *[_v(n, s, "FLUX", d, "kg m-2 s-1", None, f"{V} Eq. 8.10", False, st) for n, s, d, st in (
        ("MV_can_air", "MV_CanAir", "transpiration canopy -> air", "active"),
        ("MV_pad_air", "MV_PadAir", "pad -> air", "inactive (not confirmed)"),
        ("MV_fog_air", "MV_FogAir", "fog -> air", "inactive (not confirmed)"),
        ("MV_blow_air", "MV_BlowAir", "direct air heater -> air", "inactive (not confirmed)"),
        ("MV_air_th_scr", "MV_AirThScr", "air -> thermal screen", "inactive (conditional)"),
        ("MV_air_top", "MV_AirTop", "air -> top compartment", "inactive (Q-10)"),
        ("MV_air_out", "MV_AirOut", "air -> outside", "active"),
        ("MV_air_out_pad", "MV_AirOut_Pad", "pad/fan exchange", "inactive (not confirmed)"),
        ("MV_air_mech", "MV_AirMech", "air -> mechanical cooling", "inactive (not confirmed)"),
    )],
    _v("f_vent_roof", "f''_VentRoof", "FLUX", "roof natural-ventilation air flux", "m3 m-2 s-1", (0, None), f"{V} Eq. 8.65", True, "fixed"),
    _v("f_leakage", "f_leakage", "FLUX", "leakage air flux", "m3 m-2 s-1", (0, None), f"{V} Eq. 8.71", True, "calibration required"),
    _v("f_thermal_screen", "f_ThScr", "FLUX", "air flux through thermal screen", "m3 m-2 s-1", (0, None), f"{V} Eq. 8.41", False, "conditional"),
    _v("FIR_ij", "FIR_ij", "FLUX", "long-wave radiation flux i -> j", "W m-2", None, f"{V} Eq. 8.38", False, "fixed"),
    _v("L_12", "L_12", "FLUX", "latent heat flux", "W m-2", None, f"{V} Eq. 8.42", False, "fixed"),
    # --- CONSTANT ------------------------------------------------------------------------------
    _v("SIGMA", "sigma", "CONSTANT", "Stefan-Boltzmann constant 5.670374419e-8", "W m-2 K-4", None, "CODATA 2018", True, "universal"),
    _v("R_GAS", "R", "CONSTANT", "universal gas constant 8.314462618", "J mol-1 K-1", None, "SI 2019", True, "universal"),
    _v("M_WATER", "M_Water", "CONSTANT", "molar mass of water 18.01528e-3", "kg mol-1", None, "IUPAC", True, "universal"),
    _v("G", "g", "CONSTANT", "standard gravity 9.80665", "m s-2", None, "defined value", True, "universal"),
    _v("KELVIN_OFFSET", "273.15", "CONSTANT", "degC -> K offset", "K", None, f"{V} (T + 273.15)", True, "universal"),
    _v("CONDENSATION_FACTOR", "6.4e-9", "CONSTANT", "Eq. 8.43 conversion factor", "kg K J-1 Pa-1", None, f"{V} Eq. 8.43", True, "source literal"),
)

# Equation-local generic symbols (function arguments for "object 1 -> object 2" equations).
GENERIC_SYMBOLS = {
    "T_1": ("T_1", "degC"), "T_2": ("T_2", "degC"), "T_i": ("T_i", "degC"), "T_j": ("T_j", "degC"),
    "VP_1": ("VP_1", "Pa"), "VP_2": ("VP_2", "Pa"), "MV_12": ("MV_12", "kg m-2 s-1"),
    "f_12": ("f_12", "m3 m-2 s-1"), "tau_1": ("tau_1", "-"), "tau_2": ("tau_2", "-"),
    "rho_1": ("rho_1", "-"), "rho_2": ("rho_2", "-"), "g": ("g", "m s-2"),
    "T_degC": ("T", "degC"), "RH_percent": ("RH", "%"), "VP_Pa": ("P_v", "Pa"),
    "P_atm_Pa": ("P_atm", "Pa"), "X_kg_per_kg": ("X", "kg kg-1"), "value_Pa": ("-", "Pa"),
    "value_hPa": ("-", "hPa"), "rhs_W_m2": ("RHS Eq. 8.2", "W m-2"),
    "rhs_kg_m2_s": ("RHS Eq. 8.10", "kg m-2 s-1"), "activation": ("-", "-"),
}

BY_NAME = {v.name: v for v in REGISTRY}
if len(BY_NAME) != len(REGISTRY):
    raise RuntimeError("duplicate names in variable registry")


def as_markdown():
    lines = ["# Variable Registry", "",
             "Generated from `src/greenhouse_mpc/physics/variables.py` "
             "(`python -m greenhouse_mpc.physics.variables`). Do not edit by hand.", ""]
    for category in CATEGORIES:
        lines += [f"## {category}", "",
                  "| name | source_symbol | description | unit | bounds | source | required | status |",
                  "|---|---|---|---|---|---|---|---|"]
        for v in REGISTRY:
            if v.category == category:
                bounds = "—" if v.bounds is None else f"[{v.bounds[0]}, {'∞' if v.bounds[1] is None else v.bounds[1]}]"
                lines.append(f"| `{v.name}` | {v.source_symbol} | {v.description} | {v.unit} | {bounds} | "
                             f"{v.source} | {'yes' if v.required else 'no'} | {v.status} |")
        lines.append("")
    lines += ["## Equation-local generic symbols", "", "| python | source symbol | unit |", "|---|---|---|"]
    lines += [f"| `{k}` | {s} | {u} |" for k, (s, u) in GENERIC_SYMBOLS.items()]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(as_markdown(), end="")
