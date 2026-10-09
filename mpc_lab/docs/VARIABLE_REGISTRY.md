# Variable Registry

Generated from `src/greenhouse_mpc/physics/variables.py` (`python -m greenhouse_mpc.physics.variables`). Do not edit by hand.

## STATE

| name | source_symbol | description | unit | bounds | source | required | status |
|---|---|---|---|---|---|---|---|
| `T_air` | T_Air | greenhouse air temperature | degC | — | Vanthoor (2011) Eq. 8.2 | yes | fixed |
| `VP_air` | VP_Air | greenhouse air vapour pressure (dynamic moisture state) | Pa | [0, ∞] | Vanthoor (2011) Eq. 8.10 | yes | fixed |

## CONTROL

| name | source_symbol | description | unit | bounds | source | required | status |
|---|---|---|---|---|---|---|---|
| `u_roof` | U_Roof | roof-vent aperture control | - | [0, 1] | Vanthoor (2011) Eq. 8.65, 8.68 | yes | fixed; field % mapping unresolved (Q-1) |
| `u_shade_screen` | U_ShScr | movable shade-screen control | - | [0, 1] | Vanthoor (2011) Eq. 8.16, 8.17 | yes | fixed; field % mapping unresolved (Q-1) |
| `u_thermal_screen` | U_ThScr | thermal-screen control (field shade screen in its night role) | - | [0, 1] | Vanthoor (2011) Eq. 8.39, 8.41 | no | conditional (hardware-role mapping) |
| `u_diffuse_screen` | U_Diffuse | diffuse-screen state/control | - | [0, 1] | equation baseline §1.2 | yes | no source optical relation (DIFF-OPEN) |

## DISTURBANCE

| name | source_symbol | description | unit | bounds | source | required | status |
|---|---|---|---|---|---|---|---|
| `T_out` | T_Out | outside air temperature | degC | — | Vanthoor (2011) Eq. 8.65 | yes | fixed |
| `VP_out` | VP_Out | outside air vapour pressure | Pa | [0, ∞] | equation baseline §1.3 | yes | fixed |
| `RH_out` | RH (outside) | measured outside relative humidity, converted by PSY-02 | % | [0, 100] | equation baseline §2.2 | yes | measurement absent in current live data |
| `wind_speed` | v_Wind | wind speed | m s-1 | [0, ∞] | Vanthoor (2011) Eq. 8.65, 8.71 | yes | fixed |
| `wind_direction` | theta_Wind | wind direction (stored for future C_w selection only) | deg | [0, 360] | equation baseline §13 | no | no function (WINDDIR-01 unresolved) |
| `solar_radiation` | I_solar | global radiation at the site sensor | W m-2 | [0, ∞] | equation baseline §1.3 | yes | fixed |
| `rain` | rain | rain state | - | — | equation baseline §1.3 | yes | fixed |
| `time` | t | time | s | — | equation baseline §1.3 | yes | fixed |
| `T_mean` | T_bar | mean greenhouse/outdoor air temperature in Eq. 8.65 | degC | — | Vanthoor (2011) Eq. 8.65 | yes | definition to confirm (Q-3) |
| `T_can` | T_Can | canopy temperature | degC | — | equation baseline §1.3 | no | source of value unresolved |
| `I_i` | I_i | inside direct radiation | W m-2 | [0, ∞] | Cabrera et al. (2009) | no | measurement/ray-model input |
| `I_o` | I_o | outside direct radiation | W m-2 | [0, ∞] | Cabrera et al. (2009) | no | measurement/ray-model input |
| `D_i` | D_i | inside diffuse radiation | W m-2 | [0, ∞] | Cabrera et al. (2009) | no | measurement/ray-model input |
| `D_o` | D_o | outside diffuse radiation | W m-2 | [0, ∞] | Cabrera et al. (2009) | no | measurement/ray-model input |

## PARAMETER

| name | source_symbol | description | unit | bounds | source | required | status |
|---|---|---|---|---|---|---|---|
| `A_floor` | A_Flr | greenhouse floor area | m2 | [0, ∞] | Vanthoor (2011) Eq. 8.65 | yes | field_required |
| `A_roof` | A_Roof | maximum roof-vent area | m2 | [0, ∞] | Vanthoor (2011) Eq. 8.65, 8.68 | yes | field_required |
| `h_vent` | h_Vent | vertical dimension of one vent opening | m | [0, ∞] | Vanthoor (2011) Eq. 8.65 | yes | field_required |
| `C_d` | C_d | discharge coefficient | - | [0, ∞] | Vanthoor (2011) Eq. 8.65 | yes | calibration_or_geometry_matched_source |
| `C_w` | C_w | global wind-pressure coefficient | - | [0, ∞] | Vanthoor (2011) Eq. 8.65 | yes | calibration_or_geometry_matched_source |
| `c_leakage` | c_leakage | leakage coefficient | see Q-4 (branch-dependent) | [0, ∞] | Vanthoor (2011) Eq. 8.71 | yes | calibration_required |
| `h_roof` | h_Rf | roof (cover) thickness | m | [0, ∞] | Vanthoor (2011) Eq. 8.19 | no | field_required; conditional |
| `lambda_roof` | lambda_Rf | roof thermal conductivity | W m-1 K-1 | [0, ∞] | Vanthoor (2011) Eq. 8.19 | no | manufacturer_or_calibration |
| `u_shade_perm` | U_ShScrPer | semi-permanent shading-layer state | - | [0, 1] | Vanthoor (2011) Eq. 8.16, 8.17, 8.19 | no | existence on site unconfirmed (Q-2) |
| `h_shade_perm` | h_ShScrPer | semi-permanent shading-layer thickness | m | [0, ∞] | Vanthoor (2011) Eq. 8.19 | no | conditional (Q-2) |
| `lambda_shade_perm` | lambda_ShScrPer | semi-permanent shading-layer conductivity | W m-1 K-1 | [0, ∞] | Vanthoor (2011) Eq. 8.19 | no | conditional (Q-2) |
| `tau_shade` | tau_ShScrPAR (NIR similarly) | shade-screen transmission coefficient (one waveband) | - | [0, 1] | Vanthoor (2011) Eq. 8.16, 8.17 | yes | manufacturer_or_measurement |
| `rho_shade` | rho_ShScrPAR (NIR similarly) | shade-screen reflection coefficient (one waveband) | - | [0, 1] | Vanthoor (2011) Eq. 8.16, 8.17 | yes | manufacturer_or_measurement |
| `tau_shade_perm` | tau_ShScrPerPAR | semi-permanent layer transmission | - | [0, 1] | Vanthoor (2011) Eq. 8.16, 8.17 | no | conditional (Q-2) |
| `rho_shade_perm` | rho_ShScrPerPAR | semi-permanent layer reflection | - | [0, 1] | Vanthoor (2011) Eq. 8.16, 8.17 | no | conditional (Q-2) |
| `tau_thermal_screen_FIR` | tau_ThScrFIR | thermal-screen FIR transmission | - | [0, 1] | Vanthoor (2011) Eq. 8.39 | no | manufacturer_or_measurement_if_used_as_thermal_screen |
| `K_thermal_screen` | K_ThScr | screen-flux coefficient (permeability) | m3 m-2 K-0.66 s-1 | [0, ∞] | Vanthoor (2011) Eq. 8.41 | no | calibration_required_if_activated |
| `tau_bb` | tau_b-b | diffuse-screen direct-to-direct transmittance | - | [0, ∞] | Cabrera et al. (2009) | no | manufacturer_or_measurement |
| `tau_bd` | tau_b-d | diffuse-screen direct-to-diffuse transmittance | - | — | Cabrera et al. (2009) Eq. 7 | no | manufacturer_or_measurement |
| `tau_d` | tau_d | diffuse transmittance (overcast-determined) | - | [0, ∞] | Cabrera et al. (2009) Eq. 6 | no | manufacturer_or_measurement |
| `LAI` | LAI | leaf area index | m2 m-2 | [0, ∞] | Vanthoor (2011) Eq. 8.48 | yes | measurement_or_crop_schedule |
| `r_b` | r_b | canopy boundary-layer resistance | s m-1 | [0, ∞] | Vanthoor (2011) Eq. 8.48 | yes | source_or_calibration |
| `r_s_min` | r_s,min | minimum canopy stomatal resistance | s m-1 | [0, ∞] | Vanthoor (2011) Eq. 8.49 | yes | source_or_calibration |
| `rf_R_can` | rf(R_Can) | stomatal resistance factor for radiation | - | [0, ∞] | Vanthoor (2011) Eq. 8.49-8.50 | yes | Eq. 8.50 not in baseline (Q-6) |
| `rf_CO2_air` | rf(CO2_Air) | stomatal resistance factor for CO2 | - | [0, ∞] | Vanthoor (2011) Eq. 8.49-8.50 | yes | Eq. 8.50 not in baseline (Q-6) |
| `rf_VPD_can_air` | rf(VP_Can - VP_Air) | stomatal resistance factor for vapour pressure difference | - | [0, ∞] | Vanthoor (2011) Eq. 8.49-8.50 | yes | Eq. 8.50 not in baseline (Q-6) |
| `s_MV12` | s_MV12 | switch slope of the smoothed condensation function | Pa-1 | — | Vanthoor (2011) Eq. 8.44 | no | optional; not guessed |
| `cap_air` | cap_Air | heat capacity of greenhouse air per floor area | J K-1 m-2 | [0, ∞] | Vanthoor (2011) Eq. 8.2 | yes | definition not in baseline (Q-8) |
| `cap_VP_air` | cap_VPAir | vapour capacity of greenhouse air per floor area | kg m-2 Pa-1 | [0, ∞] | Vanthoor (2011) Eq. 8.10 | yes | definition not in baseline (Q-8) |
| `HEC_12` | HEC_12 | heat exchange coefficient between objects 1 and 2 | W m-2 K-1 | [0, ∞] | Vanthoor (2011) Eq. 8.40, 8.43 | yes | from its source equation/table or calibration |
| `A_i` | A_i | surface area of object i per floor area | m2 m-2 | [0, ∞] | Vanthoor (2011) Eq. 8.38 | no | surface-pair specific |
| `eps_i` | epsilon_i | FIR emission coefficient of object i | - | [0, 1] | Vanthoor (2011) Eq. 8.38 | no | surface specific |
| `eps_j` | epsilon_j | FIR emission coefficient of object j | - | [0, 1] | Vanthoor (2011) Eq. 8.38 | no | surface specific |
| `F_ij` | F_ij | view factor from i to j | - | [0, 1] | Vanthoor (2011) Eq. 8.38 | no | surface-pair specific |
| `rho_air` | rho_Air | greenhouse air density | kg m-3 | [0, ∞] | Vanthoor (2011) Eq. 8.41, 8.48 | yes | condition-dependent; not defaulted (Q-11) |
| `rho_air_mean` | rho_Air^Mean | mean air density across the screen | kg m-3 | [0, ∞] | Vanthoor (2011) Eq. 8.41 | no | conditional |
| `rho_out` | rho_Out | air density on the other side of the screen (as transcribed) | kg m-3 | [0, ∞] | Vanthoor (2011) Eq. 8.41 | no | conditional (Q-5) |
| `c_p_air` | c_p,Air | specific heat capacity of air | J kg-1 K-1 | [0, ∞] | Vanthoor (2011) Eq. 8.48 | yes | not defaulted (Q-11) |
| `delta_H` | Delta_H | latent heat of evaporation | J kg-1 | [0, ∞] | Vanthoor (2011) Eq. 8.42, 8.48 | yes | not defaulted (Q-11) |
| `gamma` | gamma | psychrometric constant | Pa K-1 | [0, ∞] | Vanthoor (2011) Eq. 8.48 | yes | not defaulted (Q-11) |
| `P_atm` | P_atm | atmospheric pressure | Pa | [0, ∞] | equation baseline PSY-03 | yes | measured_or_configured |

## DERIVED

| name | source_symbol | description | unit | bounds | source | required | status |
|---|---|---|---|---|---|---|---|
| `RH_air` | RH_Air | greenhouse relative humidity (measured input / derived output) | % | [0, ∞] | equation baseline PSY-02 | yes | fixed |
| `X_air` | X_i | greenhouse humidity ratio | kg kg-1 (water per dry air) | [0, ∞] | equation baseline PSY-03 | no | fixed |
| `VPD_air` | VPD_Air | greenhouse vapour pressure deficit | Pa | — | equation baseline PSY-04 | no | fixed |
| `T_dew_air` | T_dew | greenhouse dew-point temperature | degC | — | equation baseline PSY-05 | no | fixed |
| `P_sat` | P_sat(T) | saturation vapour pressure | Pa | [0, ∞] | equation baseline PSY-01 | yes | fixed |
| `e_s_hPa` | e_s(T) | saturation vapour pressure in source unit | hPa | [0, ∞] | equation baseline PSY-01 | no | fixed |
| `VP_can` | VP_Can | saturated vapour pressure at canopy temperature | Pa | [0, ∞] | Vanthoor (2011) Eq. 8.47 | yes | saturation formula to confirm (Q-7) |
| `VEC_can_air` | VEC_CanAir | canopy vapour-exchange coefficient | kg m-2 Pa-1 s-1 | [0, ∞] | Vanthoor (2011) Eq. 8.48 | yes | fixed |
| `r_s` | r_s | canopy stomatal resistance | s m-1 | [0, ∞] | Vanthoor (2011) Eq. 8.49 | yes | fixed / params required |
| `A_roof_U` | A^U_Roof | roof-vent aperture | m2 | [0, ∞] | Vanthoor (2011) Eq. 8.68 | no | fixed |
| `tau_shade_combined` | tau_ShScr_ShScrPerPAR | transmission of shade screen + semi-permanent layer | - | [0, 1] | Vanthoor (2011) Eq. 8.16 | no | fixed |
| `rho_shade_combined` | rho_ShScr_ShScrPerPAR | reflection of shade screen + semi-permanent layer | - | [0, 1] | Vanthoor (2011) Eq. 8.17 | no | fixed |
| `tau_thermal_screen_FIR_U` | tau^U_ThScrFIR | FIR transmission at screen control | - | [0, 1] | Vanthoor (2011) Eq. 8.39 | no | conditional |
| `HEC_cov_in_cov_e` | HEC_Cov,in_Cov,e | lumped cover conduction coefficient | W m-2 K-1 | [0, ∞] | Vanthoor (2011) Eq. 8.19 | no | conditional to layer match |
| `D_star` | D* | direct radiation converted into diffuse | W m-2 | — | Cabrera et al. (2009) Eq. 6 | no | fixed physics |
| `tau_b` | tau_b | total direct transmittance | - | — | Cabrera et al. (2009) Eq. 8 | no | fixed physics |

## FLUX

| name | source_symbol | description | unit | bounds | source | required | status |
|---|---|---|---|---|---|---|---|
| `H_can_air` | H_CanAir | sensible heat canopy -> air | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | active |
| `H_pad_air` | H_PadAir | pad outlet air -> air | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | inactive (not confirmed) |
| `H_mech_air` | H_MechAir | mechanical cooling -> air | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | inactive (not confirmed) |
| `H_pipe_air` | H_PipeAir | heating pipes -> air | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | inactive (Q-9) |
| `H_pas_air` | H_PasAir | passive buffer -> air | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | inactive (not confirmed) |
| `H_blow_air` | H_BlowAir | direct air heater -> air | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | inactive (Q-9) |
| `R_glob_sun_air` | R_Glob_SunAir | global radiation absorbed by construction, released to air | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | active |
| `H_air_flr` | H_AirFlr | air -> floor | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | active |
| `H_air_th_scr` | H_AirThScr | air -> thermal screen | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | inactive (conditional) |
| `H_air_out` | H_AirOut | air -> outside | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | active |
| `H_air_top` | H_AirTop | air -> top compartment | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | inactive (Q-10) |
| `H_air_out_pad` | H_AirOut_Pad | pad/fan air exchange | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | inactive (not confirmed) |
| `L_air_fog` | L_AirFog | latent heat of fog evaporation | W m-2 | — | Vanthoor (2011) Eq. 8.2 | no | inactive (not confirmed) |
| `MV_can_air` | MV_CanAir | transpiration canopy -> air | kg m-2 s-1 | — | Vanthoor (2011) Eq. 8.10 | no | active |
| `MV_pad_air` | MV_PadAir | pad -> air | kg m-2 s-1 | — | Vanthoor (2011) Eq. 8.10 | no | inactive (not confirmed) |
| `MV_fog_air` | MV_FogAir | fog -> air | kg m-2 s-1 | — | Vanthoor (2011) Eq. 8.10 | no | inactive (not confirmed) |
| `MV_blow_air` | MV_BlowAir | direct air heater -> air | kg m-2 s-1 | — | Vanthoor (2011) Eq. 8.10 | no | inactive (not confirmed) |
| `MV_air_th_scr` | MV_AirThScr | air -> thermal screen | kg m-2 s-1 | — | Vanthoor (2011) Eq. 8.10 | no | inactive (conditional) |
| `MV_air_top` | MV_AirTop | air -> top compartment | kg m-2 s-1 | — | Vanthoor (2011) Eq. 8.10 | no | inactive (Q-10) |
| `MV_air_out` | MV_AirOut | air -> outside | kg m-2 s-1 | — | Vanthoor (2011) Eq. 8.10 | no | active |
| `MV_air_out_pad` | MV_AirOut_Pad | pad/fan exchange | kg m-2 s-1 | — | Vanthoor (2011) Eq. 8.10 | no | inactive (not confirmed) |
| `MV_air_mech` | MV_AirMech | air -> mechanical cooling | kg m-2 s-1 | — | Vanthoor (2011) Eq. 8.10 | no | inactive (not confirmed) |
| `f_vent_roof` | f''_VentRoof | roof natural-ventilation air flux | m3 m-2 s-1 | [0, ∞] | Vanthoor (2011) Eq. 8.65 | yes | fixed |
| `f_leakage` | f_leakage | leakage air flux | m3 m-2 s-1 | [0, ∞] | Vanthoor (2011) Eq. 8.71 | yes | calibration required |
| `f_thermal_screen` | f_ThScr | air flux through thermal screen | m3 m-2 s-1 | [0, ∞] | Vanthoor (2011) Eq. 8.41 | no | conditional |
| `FIR_ij` | FIR_ij | long-wave radiation flux i -> j | W m-2 | — | Vanthoor (2011) Eq. 8.38 | no | fixed |
| `L_12` | L_12 | latent heat flux | W m-2 | — | Vanthoor (2011) Eq. 8.42 | no | fixed |

## CONSTANT

| name | source_symbol | description | unit | bounds | source | required | status |
|---|---|---|---|---|---|---|---|
| `SIGMA` | sigma | Stefan-Boltzmann constant 5.670374419e-8 | W m-2 K-4 | — | CODATA 2018 | yes | universal |
| `R_GAS` | R | universal gas constant 8.314462618 | J mol-1 K-1 | — | SI 2019 | yes | universal |
| `M_WATER` | M_Water | molar mass of water 18.01528e-3 | kg mol-1 | — | IUPAC | yes | universal |
| `G` | g | standard gravity 9.80665 | m s-2 | — | defined value | yes | universal |
| `KELVIN_OFFSET` | 273.15 | degC -> K offset | K | — | Vanthoor (2011) (T + 273.15) | yes | universal |
| `CONDENSATION_FACTOR` | 6.4e-9 | Eq. 8.43 conversion factor | kg K J-1 Pa-1 | — | Vanthoor (2011) Eq. 8.43 | yes | source literal |

## Equation-local generic symbols

| python | source symbol | unit |
|---|---|---|
| `T_1` | T_1 | degC |
| `T_2` | T_2 | degC |
| `T_i` | T_i | degC |
| `T_j` | T_j | degC |
| `VP_1` | VP_1 | Pa |
| `VP_2` | VP_2 | Pa |
| `MV_12` | MV_12 | kg m-2 s-1 |
| `f_12` | f_12 | m3 m-2 s-1 |
| `tau_1` | tau_1 | - |
| `tau_2` | tau_2 | - |
| `rho_1` | rho_1 | - |
| `rho_2` | rho_2 | - |
| `g` | g | m s-2 |
| `T_degC` | T | degC |
| `RH_percent` | RH | % |
| `VP_Pa` | P_v | Pa |
| `P_atm_Pa` | P_atm | Pa |
| `X_kg_per_kg` | X | kg kg-1 |
| `value_Pa` | - | Pa |
| `value_hPa` | - | hPa |
| `rhs_W_m2` | RHS Eq. 8.2 | W m-2 |
| `rhs_kg_m2_s` | RHS Eq. 8.10 | kg m-2 s-1 |
| `activation` | - | - |
