# Variable Naming

Applies to `src/greenhouse_mpc/physics/`. The full registry (category, unit, bounds, source, status)
is generated into `VARIABLE_REGISTRY.md` from `physics/variables.py`; this file states the rules and
the source → Python mapping.

## Rules

1. **Quantity prefix, then location.** `T_` temperature, `VP_` vapour pressure, `RH_` relative
   humidity, `X_` humidity ratio, `H_` sensible heat flux, `L_` latent heat flux, `MV_` vapour flux,
   `R_` radiation flux, `f_` air flux, `A_` area, `h_` thickness/height, `tau_` transmission,
   `rho_` reflection **or** density (density only in `rho_air`, `rho_air_mean`, `rho_out`), `u_` control.
2. **Locations in lower snake case** from Vanthoor subscripts: Air → `air`, Out → `out`,
   Can → `can`, Flr → `flr`/`floor`, ThScr → `th_scr` / `thermal_screen`, ShScr → `shade`/`shade_screen`,
   ShScrPer → `shade_perm`, Rf/Roof → `roof`, Top → `top`.
3. **Flux direction follows the source:** `H_can_air` = canopy → air; `H_air_out` = air → outside.
   A positive value means flow in the written direction.
4. **Equation-local generic symbols** keep the source indices: `T_1`, `T_2`, `VP_1`, `HEC_12`,
   `MV_12`, `f_12`, `A_i`, `eps_i`, `F_ij`.
5. **Units are fixed per name** and never converted implicitly. Temperatures in degC (Vanthoor adds
   273.15 inside the equation), vapour pressures in Pa, fluxes per m² floor. hPa appears only in
   `saturation_vapour_pressure_hPa` and the explicit helpers `hpa_to_pa`, `pa_to_hpa`.
   Psychrometric function arguments carry the unit in the name (`T_degC`, `VP_Pa`, `RH_percent`).
6. **Controls are Vanthoor fractions in [0, 1]** (`u_roof`, `u_shade_screen`, `u_thermal_screen`,
   `u_diffuse_screen`). Field percentages are different quantities and are not stored under these names.
7. **The dynamic moisture state is `VP_air`.** `RH_air`, `X_air`, `VPD_air`, `T_dew_air` are derived;
   they are never used as a state.
8. **Equation functions** are named `eq_<chapter>_<number>_<what>` for Vanthoor and descriptively for
   psychrometrics/Cabrera, with the source in the docstring.
9. **Field-specific parameters have no default** other than `None`.

## Source symbol → Python mapping

| Source symbol | Python name | Meaning | Unit |
|---|---|---|---|
| T_Air | `T_air` | greenhouse air temperature | degC |
| VP_Air | `VP_air` | greenhouse air vapour pressure | Pa |
| T_Out | `T_out` | outside air temperature | degC |
| VP_Out | `VP_out` | outside vapour pressure | Pa |
| T_Can | `T_can` | canopy temperature | degC |
| VP_Can | `VP_can` | saturated vapour pressure at canopy temperature | Pa |
| T̄ | `T_mean` | mean greenhouse/outdoor air temperature (Eq. 8.65) | degC |
| v_Wind | `wind_speed` | wind speed | m s-1 |
| θ_Wind | `wind_direction` | wind direction (stored only) | deg |
| I_solar | `solar_radiation` | global radiation at site sensor | W m-2 |
| U_Roof | `u_roof` | roof-vent aperture control | - |
| U_ShScr | `u_shade_screen` | movable shade-screen control | - |
| U_ThScr | `u_thermal_screen` | thermal-screen control | - |
| U_Diffuse | `u_diffuse_screen` | diffuse-screen state | - |
| U_ShScrPer | `u_shade_perm` | semi-permanent shading layer state | - |
| A_Flr | `A_floor` | floor area | m2 |
| A_Roof | `A_roof` | maximum roof-vent area | m2 |
| A^U_Roof | `A_roof_U` | roof-vent aperture | m2 |
| h_Vent | `h_vent` | vertical dimension of one vent opening | m |
| C_d | `C_d` | discharge coefficient | - |
| C_w | `C_w` | global wind-pressure coefficient | - |
| c_leakage | `c_leakage` | leakage coefficient | see Q-4 |
| f''_VentRoof | `f_vent_roof` | roof ventilation air flux | m3 m-2 s-1 |
| f_leakage | `f_leakage` | leakage air flux | m3 m-2 s-1 |
| f_ThScr | `f_thermal_screen` | air flux through thermal screen | m3 m-2 s-1 |
| K_ThScr | `K_thermal_screen` | screen-flux coefficient | m3 m-2 K-0.66 s-1 |
| cap_Air | `cap_air` | air heat capacity per floor area | J K-1 m-2 |
| cap_VPAir | `cap_VP_air` | air vapour capacity per floor area | kg m-2 Pa-1 |
| H_CanAir, H_PadAir, H_MechAir, H_PipeAir, H_PasAir, H_BlowAir | `H_can_air`, `H_pad_air`, `H_mech_air`, `H_pipe_air`, `H_pas_air`, `H_blow_air` | Eq. 8.2 heat gains | W m-2 |
| R_Glob_SunAir | `R_glob_sun_air` | global radiation absorbed by construction → air | W m-2 |
| H_AirFlr, H_AirThScr, H_AirOut, H_AirTop, H_AirOut_Pad | `H_air_flr`, `H_air_th_scr`, `H_air_out`, `H_air_top`, `H_air_out_pad` | Eq. 8.2 heat losses | W m-2 |
| L_AirFog | `L_air_fog` | fog latent heat | W m-2 |
| MV_CanAir, MV_PadAir, MV_FogAir, MV_BlowAir | `MV_can_air`, `MV_pad_air`, `MV_fog_air`, `MV_blow_air` | Eq. 8.10 vapour gains | kg m-2 s-1 |
| MV_AirThScr, MV_AirTop, MV_AirOut, MV_AirOut_Pad, MV_AirMech | `MV_air_th_scr`, `MV_air_top`, `MV_air_out`, `MV_air_out_pad`, `MV_air_mech` | Eq. 8.10 vapour losses | kg m-2 s-1 |
| HEC_12 | `HEC_12` | heat exchange coefficient | W m-2 K-1 |
| FIR_ij | `FIR_ij` | long-wave flux | W m-2 |
| ε_i, ε_j, F_ij, A_i | `eps_i`, `eps_j`, `F_ij`, `A_i` | FIR emission, view factor, area ratio | -, -, -, m2 m-2 |
| L_12, ΔH | `L_12`, `delta_H` | latent heat flux, latent heat | W m-2, J kg-1 |
| s_MV12 | `s_MV12` | condensation switch slope | Pa-1 |
| VEC_CanAir | `VEC_can_air` | canopy vapour-exchange coefficient | kg m-2 Pa-1 s-1 |
| ρ_Air, ρ_Air^Mean, ρ_Out | `rho_air`, `rho_air_mean`, `rho_out` | air densities | kg m-3 |
| c_p,Air | `c_p_air` | specific heat of air | J kg-1 K-1 |
| γ | `gamma` | psychrometric constant | Pa K-1 |
| LAI | `LAI` | leaf area index | m2 m-2 |
| r_b, r_s, r_s,min | `r_b`, `r_s`, `r_s_min` | resistances | s m-1 |
| rf(R_Can), rf(CO2_Air), rf(VP_Can−VP_Air) | `rf_R_can`, `rf_CO2_air`, `rf_VPD_can_air` | resistance factors | - |
| τ_ShScrPAR, ρ_ShScrPAR | `tau_shade`, `rho_shade` | shade-screen optics (per waveband) | - |
| τ_ShScrPerPAR, ρ_ShScrPerPAR | `tau_shade_perm`, `rho_shade_perm` | semi-permanent layer optics | - |
| τ_ThScrFIR | `tau_thermal_screen_FIR` | thermal-screen FIR transmission | - |
| h_Rf, λ_Rf, h_ShScrPer, λ_ShScrPer | `h_roof`, `lambda_roof`, `h_shade_perm`, `lambda_shade_perm` | layer thickness / conductivity | m, W m-1 K-1 |
| HEC_Cov,in_Cov,e | `HEC_cov_in_cov_e` | cover conduction coefficient | W m-2 K-1 |
| τ_b-b, τ_b-d, τ_d, τ_b | `tau_bb`, `tau_bd`, `tau_d`, `tau_b` | Cabrera transmittances | - |
| I_i, I_o, D_i, D_o, D* | `I_i`, `I_o`, `D_i`, `D_o`, `D_star` | Cabrera radiation components | W m-2 |
| e_s(T), P_sat(T) | `e_s_hPa`, `P_sat` | saturation vapour pressure | hPa, Pa |
| P_v | `VP_*` | vapour pressure | Pa |
| P_atm | `P_atm` | atmospheric pressure | Pa |
| X, X_i | `X_air` | humidity ratio | kg water / kg dry air |
| RH, VPD, T_dew | `RH_air`, `VPD_air`, `T_dew_air` | derived humidity outputs | %, Pa, degC |
| σ, R, M_Water, g | `SIGMA`, `R_GAS`, `M_WATER`, `G` | universal constants | see registry |

Structure-field aliases (inside a typed structure the owner already gives the context):
`ShadeScreenParameters.tau_PAR` = `tau_shade` (PAR), `.tau_FIR` = `tau_thermal_screen_FIR`,
`.K_screen` = `K_thermal_screen`; `SemiPermanentShadeLayer.u_perm/tau_PAR/rho_PAR/h_perm/lambda_perm` =
`u_shade_perm/tau_shade_perm/rho_shade_perm/h_shade_perm/lambda_shade_perm`.
