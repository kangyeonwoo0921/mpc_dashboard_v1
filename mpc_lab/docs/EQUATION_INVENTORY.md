# Equation Inventory

Source of truth: `docs/greenhouse_mpc_final_equation_baseline.md` (baseline). Equations are reproduced
without changing their functional form. Code: `src/greenhouse_mpc/physics/`. Units: `UNIT_AUDIT.md`.
Open questions Q-n: listed at the end.

| equation_id | source | equation_no | purpose | inputs | outputs | parameters | units (out) | implementation_status |
|---|---|---|---|---|---|---|---|---|
| PSY-01 | Magnus (baseline §2.1) | — | saturation vapour pressure | T [degC] | e_s [hPa], P_sat [Pa] | none | hPa / Pa | implemented: `psychrometrics.saturation_vapour_pressure_hPa`, `saturation_vapour_pressure` |
| PSY-02 | RH definition (§2.2, §2.5) | — | RH ↔ vapour pressure | RH [%], T [degC] / VP [Pa], T | VP [Pa] / RH [%] | none | Pa / % | implemented: `rh_to_vp`, `vp_to_rh` |
| PSY-03 | psychrometric relation (§2.3, §2.4) | — | VP ↔ humidity ratio | VP [Pa], P_atm [Pa] / X, P_atm | X [kg kg-1] / VP [Pa] | P_atm (measured or configured) | kg kg-1 / Pa | implemented: `vp_to_humidity_ratio`, `humidity_ratio_to_vp` |
| PSY-04 | VP definition (§2.6) | — | VPD | T [degC], VP [Pa] | VPD [Pa] | none | Pa | implemented: `vpd` |
| PSY-05 | inverse of PSY-01 (§2.7) | — | dew point | VP [Pa] | T_dew [degC] | none | degC | implemented: `dew_point` |
| TEMP-01 | Vanthoor 2011 | Eq. 8.2 | air temperature balance | 13 heat fluxes [W m-2], cap_Air | RHS [W m-2]; dT_Air/dt [K s-1] | cap_Air (Q-8), component activation | W m-2 | implemented wrapper: `balances.eq_8_2_temperature_rhs`, `eq_8_2_dT_air_dt` |
| HUM-01 | Vanthoor 2011 | Eq. 8.10 | air vapour-pressure balance | 9 vapour fluxes [kg m-2 s-1], cap_VPAir | RHS [kg m-2 s-1]; dVP_Air/dt [Pa s-1] | cap_VPAir (Q-8), component activation | kg m-2 s-1 | implemented wrapper: `balances.eq_8_10_vapour_rhs`, `eq_8_10_dVP_air_dt` |
| SHADE-01 | Vanthoor 2011 (EN 410) | Eq. 8.14 | double-layer transmission | tau_1, rho_1, tau_2, rho_2 | tau_12 | material coefficients | - | implemented: `shade_screen.eq_8_14_double_layer_tau` |
| SHADE-01 | Vanthoor 2011 (EN 410) | Eq. 8.15 | double-layer reflection | tau_1, rho_1, rho_2 | rho_12 | material coefficients | - | implemented: `eq_8_15_double_layer_rho` |
| SHADE-02 | Vanthoor 2011 | Eq. 8.16 | movable shade + semi-permanent layer transmission | U_ShScr, U_ShScrPer | tau | tau/rho of both layers (manufacturer/measurement) | - | implemented: `eq_8_16_shade_screen_tau` (Q-1, Q-2) |
| SHADE-02 | Vanthoor 2011 | Eq. 8.17 | same, reflection | U_ShScr, U_ShScrPer | rho | as Eq. 8.16 | - | implemented: `eq_8_17_shade_screen_rho` |
| COVER-01 | Vanthoor 2011 | Eq. 8.19 | lumped cover conduction coefficient | U_ShScrPer | HEC_Cov,in_Cov,e | h_Rf, lambda_Rf, h_ShScrPer, lambda_ShScrPer | W m-2 K-1 | implemented: `heat_transfer.eq_8_19_cover_conduction_hec`; **CONDITIONAL TO LAYER MATCH** |
| FIR-01 | Vanthoor 2011 | Eq. 8.38 | long-wave exchange | T_i, T_j | FIR_ij | A_i, eps_i, eps_j, F_ij | W m-2 | implemented: `eq_8_38_fir_flux` |
| THERMAL-01 | Vanthoor 2011 | Eq. 8.39 | thermal-screen FIR transmission | U_ThScr | tau^U_ThScrFIR | tau_ThScrFIR | - | implemented: `shade_screen.eq_8_39_thermal_screen_fir_tau`; **CONDITIONAL** |
| HEAT-01 | Vanthoor 2011 | Eq. 8.40 | convective/conductive flux | T_1, T_2 | H_12 | HEC_12 | W m-2 | implemented: `eq_8_40_sensible_heat_flux` |
| THERMAL-02 | Vanthoor 2011 | Eq. 8.41 | airflow through thermal screen | U_ThScr, T_Air, T_Out, rho's | f_ThScr | K_ThScr | m3 m-2 s-1 (stated; see unit audit) | implemented: `eq_8_41_thermal_screen_airflow`; **CONDITIONAL** (Q-5) |
| LAT-01 | Vanthoor 2011 | Eq. 8.42 | latent heat | MV_12 | L_12 | Delta_H | W m-2 | implemented: `eq_8_42_latent_heat_flux` |
| COND-01 | Vanthoor 2011 | Eq. 8.43 | condensation (switch) | VP_1, VP_2 | MV_12 | HEC_12 | kg m-2 s-1 | implemented: `moisture_transfer.eq_8_43_condensation_flux` |
| COND-02 | Vanthoor 2011 | Eq. 8.44 | condensation (smooth) | VP_1, VP_2 | MV_12 | HEC_12, s_MV12 (not guessed) | kg m-2 s-1 | implemented: `eq_8_44_condensation_flux_smooth`; **OPTIONAL** |
| MV-01 | Vanthoor 2011 | Eq. 8.45 | vapour carried by air flux | f_12, VP_1, T_1, VP_2, T_2 | MV_12 | none (M_Water, R universal) | kg m-2 s-1 | implemented: `eq_8_45_airflow_vapour_flux` |
| CROP-01 | Vanthoor 2011 | Eq. 8.47 | canopy transpiration | VP_Can, VP_Air | MV_CanAir | VEC_CanAir | kg m-2 s-1 | implemented: `crop_transpiration.eq_8_47_transpiration` (Q-7) |
| CROP-02 | Vanthoor 2011 / Stanghellini | Eq. 8.48 | vapour-exchange coefficient | rho_Air, LAI, r_s | VEC_CanAir | c_p,Air, Delta_H, gamma, r_b, LAI | kg m-2 Pa-1 s-1 | implemented: `eq_8_48_vec_can_air` (Q-11) |
| CROP-03 | Vanthoor 2011 | Eq. 8.49 | stomatal resistance structure | rf(R_Can), rf(CO2), rf(VP_Can−VP_Air) | r_s | r_s,min | s m-1 | implemented: `eq_8_49_stomatal_resistance`; **PARAMS REQUIRED** |
| CROP-03 | Vanthoor 2011 | Eq. 8.50 | resistance-factor functions | R_Can, CO2_Air, VPD | rf values | — | - | **NOT IMPLEMENTED**: functions not reproduced in the baseline (Q-6) |
| VENT-01 | Vanthoor 2011 / Boulard & Baille 1995 | Eq. 8.65 | roof natural ventilation | U_Roof, T_Air, T_Out, T_bar, v_Wind | f''_VentRoof | A_Roof, A_Flr, h_Vent, C_d, C_w | m3 m-2 s-1 | implemented: `ventilation.eq_8_65_roof_ventilation` (Q-1, Q-3) |
| VENT-02 | Vanthoor 2011 | Eq. 8.68 | roof aperture | U_Roof | A^U_Roof | A_Roof | m2 | implemented: `eq_8_68_roof_aperture` |
| LEAK-01 | Vanthoor 2011 | Eq. 8.71 | leakage | v_Wind | f_leakage | c_leakage (calibration required) | m3 m-2 s-1 | implemented as transcribed: `eq_8_71_leakage`; **FIXED / CALIBRATION REQUIRED** (Q-4) |
| WINDDIR-01 | literature evidence | — | wind-direction dependency | — | — | C_w table (cited) | - | **UNRESOLVED FUNCTION**: data container `WindPressureCoefficientTable` only, no function |
| DIFF-01 | Cabrera et al. 2009 | definition | direct-to-direct transmittance | I_i, I_o | tau_b-b | — | - | implemented: `diffuse_optics.direct_to_direct_transmittance` |
| DIFF-02 | Cabrera et al. 2009 | Eq. 6 | direct converted to diffuse | D_i, D_o | D* | tau_d | W m-2 | implemented: `direct_converted_to_diffuse` |
| DIFF-02 | Cabrera et al. 2009 | Eq. 7 | direct-to-diffuse transmittance | D_i, D_o, I_o | tau_b-d | tau_d | - | implemented: `direct_to_diffuse_transmittance` |
| DIFF-03 | Cabrera et al. 2009 | Eq. 8 | total direct transmittance | tau_b-b, tau_b-d | tau_b | — | - | implemented: `total_direct_transmittance` |
| DIFF-OPEN | not secured | — | partial diffuse-screen opening → optics | — | — | — | - | **DO NOT INVENT**: not implemented |
| DISC-01 | numerical decision (not literature) | — | 5-min discrete propagation | x_k, u_k (ZOH), d(t) | x_{k+1} | rtol, atol, rk4 substeps (null) | °C, Pa | implemented as numerical layer: `dynamics/` (Radau default, RK4 option); see `TIME_DISCRETIZATION.md` |

Not in the required list but present in the baseline: Cabrera ρ = D_i/D_o (§17.5) — definition only,
fitted power law excluded; not implemented. Radiation adapter (§18, §23) — not part of this step.

## Equation dependencies

```text
(T, RH) ─PSY-02─▶ VP ─PSY-03─▶ X ;  VP ─PSY-04─▶ VPD ;  VP ─PSY-05─▶ T_dew ;  PSY-01 under all
U_Roof ─8.68─▶ A^U_Roof
U_Roof, T_Air, T_Out, T_bar, v_Wind ─8.65─▶ f_VentRoof ┐
v_Wind ─8.71─▶ f_leakage ───────────────────────────────┴▶ air fluxes f_12
f_12 ─8.45─▶ MV_AirOut ────────────────────────────────────────────────┐
HEC_12 ─8.40─▶ H_12 (H_CanAir, H_AirFlr, H_AirOut*)                   │
8.50 (missing) ─▶ rf ─8.49─▶ r_s ─8.48─▶ VEC_CanAir ─8.47─▶ MV_CanAir ─┤
8.43 / 8.44 ─▶ condensation MV_12 ─8.42─▶ L_12                         │
8.14–8.17 ─▶ shade optics ─▶ (radiation inputs, adapter later)          │
Cabrera 6–8 ─▶ diffuse optics (no opening law)                         │
8.39, 8.41 (conditional) ─▶ thermal-screen FIR / airflow               │
8.19 (conditional) ─▶ cover HEC                                        │
heat fluxes ──────────────────▶ Eq. 8.2  ◀─ cap_Air                    │
vapour fluxes ◀────────────────────────────────────────────────────────┘ ─▶ Eq. 8.10 ◀─ cap_VPAir
```

`*` How H_AirOut is formed from the ventilation air flux (which HEC expression) is not given in the
baseline (Q-12).

## Open questions (literature interpretation only)

| ID | Question |
|---|---|
| Q-1 | Mapping from field controls (roof vent %, screen opening % with 100 = retracted) to Vanthoor U_Roof, U_ShScr, U_ThScr ∈ [0, 1] is not defined in the baseline. Is U_Roof the fraction of maximum aperture area (Eq. 8.68), so that a vent % → aperture relation is needed from the field? |
| Q-2 | Eq. 8.16/8.17/8.19 include a semi-permanent shading layer. The site has none confirmed. Is setting U_ShScrPer = 0 the intended "not instantiated" state, or should a single-layer form be used (which the baseline does not give)? |
| Q-3 | Eq. 8.65: definition of T_bar ("mean greenhouse/outdoor air temperature") is not written out. Also, the radicand becomes negative when T_Air < T_Out and wind is low; the baseline does not state how Vanthoor handles that. Code currently raises an error. |
| Q-4 | Eq. 8.71 as transcribed: `c_leakage` for v < 0.25, `c_leakage·v` for v ≥ 0.25. The two branches need different units for c_leakage and jump at 0.25 m s-1. Please check against the thesis (e.g., whether the first branch is `0.25·c_leakage`). Implemented exactly as transcribed. |
| Q-5 | Eq. 8.41 in the baseline uses T_Out and ρ_Out. In Vanthoor the thermal-screen flux is between the main compartment and the compartment above the screen; please confirm the variables. The second term's dimensions also need checking (unit audit). |
| Q-6 | Eq. 8.50 (resistance factors rf(R_Can), rf(CO2_Air), rf(VP_Can − VP_Air)) is referenced but not reproduced. Needed before MV_CanAir can be computed. Also the CO2 input is not in the current disturbance list. |
| Q-7 | VP_Can (saturated vapour pressure at canopy temperature): should PSY-01 Magnus be used, or Vanthoor's own saturation formula? And where does T_Can come from (measured / modelled / assumed)? |
| Q-8 | cap_Air (Eq. 8.2) and cap_VPAir (Eq. 8.10) definitions are not given in the baseline. |
| Q-9 | The site has a boiler (present in live data). Which Eq. 8.2/8.10 term represents it (H_PipeAir or H_BlowAir), or is it out of scope? Currently inactive. |
| Q-10 | Vanthoor's top compartment (H_AirTop, MV_AirTop) exists above a thermal screen. If the shade screen is activated as thermal screen at night, does the model need the top-compartment states (T_Top, VP_Top), which are not in x = [T_Air, VP_Air]? |
| Q-11 | ρ_Air, c_p,Air, ΔH, γ: Vanthoor uses fixed values in its parameter tables, but they are not in the baseline. Supply values (with source) or rules. |
| Q-12 | How H_AirOut (and other HEC_12 for Eq. 8.40) are built from the air flux is not given in the baseline. |
| Q-13 | Eq. 8.45 constants: code uses M_Water = 18.01528e-3 kg mol-1, R = 8.314462618 J mol-1 K-1 (universal). Vanthoor's tables use 18 kg kmol-1 and 8.314e3 J kmol-1 K-1 (ratio differs by ~0.1 %). Similarly g = 9.80665 vs 9.81. Confirm which to use. |
