# Unit Audit

Dimensional check of every implemented equation, as transcribed in
`greenhouse_mpc_final_equation_baseline.md`. Fluxes are per m² greenhouse floor. Temperature
differences in degC equal differences in K. `J = W s = Pa m³`.

Result legend: ✅ consistent · ⚠️ inconsistent or needs source check (equation NOT changed).

| Eq. | Expression (units substituted) | Result | Expected | Check |
|---|---|---|---|---|
| PSY-01 | 6.112 [hPa] · exp(dimensionless) | hPa; ×100 → Pa | Pa | ✅ (17.67T/(T+243.5) dimensionless with T in degC) |
| PSY-02 | RH [%]/100 · P_sat [Pa] | Pa | Pa | ✅ |
| PSY-03 | 0.622 · Pa / (Pa − Pa) | dimensionless = kg water / kg dry air | kg kg-1 | ✅ (0.622 = M_water/M_dry air; X is not kg m-3) |
| PSY-03 inv | X · Pa / (0.622 + X) | Pa | Pa | ✅ |
| PSY-04 | Pa − Pa | Pa | Pa | ✅ |
| PSY-05 | ln(hPa/hPa); 243.5 [degC] · γ / (17.67 − γ) | degC | degC | ✅ (VP converted Pa→hPa explicitly by `pa_to_hpa`) |
| 8.2 | cap_Air [J K-1 m-2] · dT/dt [K s-1] = Σ fluxes [W m-2] | W m-2 | W m-2 | ✅ every term in the wrapper is W m-2; R_Glob_SunAir from an upstream radiation module must be per m² floor |
| 8.10 | cap_VPAir [kg m-2 Pa-1] · dVP/dt [Pa s-1] = Σ MV [kg m-2 s-1] | kg m-2 s-1 | kg m-2 s-1 | ✅ (unit of cap_VPAir implied by the balance; definition Q-8) |
| 8.14 | (- · -)/(1 − - · -) | - | - | ✅ |
| 8.15 | - + -²·-/(1 − -·-) | - | - | ✅ |
| 8.16 / 8.17 | U, τ, ρ all dimensionless | - | - | ✅ |
| 8.19 | 1 / (m / (W m-1 K-1) + - · m / (W m-1 K-1)) = 1 / (m² K W-1) | W m-2 K-1 | W m-2 K-1 | ✅ |
| 8.38 | m² m-2 · - · - · - · W m-2 K-4 · K⁴ | W m-2 | W m-2 | ✅ (T + 273.15 → K inside) |
| 8.39 | 1 − - · (1 − -) | - | - | ✅ |
| 8.40 | W m-2 K-1 · K | W m-2 | W m-2 | ✅ |
| 8.41 term 1 | U [-] · K_ThScr · K^0.66 | m3 m-2 s-1 if K_ThScr is m3 m-2 K-0.66 s-1 | m3 m-2 s-1 | ✅ (K_ThScr unit defined so) |
| 8.41 term 2 | (1/[kg m-3]) · ([kg m-3] · [m s-2] · [kg m-3])^0.5 = (1/[kg m-3]) · kg m-3 · m^0.5 s-1 | **m^0.5 s-1** | m3 m-2 s-1 = m s-1 | ⚠️ a length^0.5 is missing as transcribed; check against thesis (Q-5). Equation not changed; submodel is CONDITIONAL/inactive |
| 8.42 | J kg-1 · kg m-2 s-1 | W m-2 | W m-2 | ✅ |
| 8.43 | 6.4e-9 [kg K J-1 Pa-1] · W m-2 K-1 · Pa | kg m-2 s-1 | kg m-2 s-1 | ✅ only if 6.4e-9 carries unit kg K J-1 Pa-1 (Vanthoor's conversion factor; recorded in registry) |
| 8.44 | 1/(1 + exp(Pa-1 · Pa)) · (as 8.43) | kg m-2 s-1 | kg m-2 s-1 | ✅ (s_MV12 [Pa-1]) |
| 8.45 | kg mol-1 / (J mol-1 K-1) · m3 m-2 s-1 · Pa K-1 = kg K J-1 · m s-1 · Pa K-1 = kg m s-1 · (Pa/J) | kg m-2 s-1 | kg m-2 s-1 | ✅ (Pa/J = m-3) |
| 8.47 | kg m-2 Pa-1 s-1 · Pa | kg m-2 s-1 | kg m-2 s-1 | ✅ |
| 8.48 | (kg m-3 · J kg-1 K-1 · -) / (J kg-1 · Pa K-1 · s m-1) | kg m-2 Pa-1 s-1 | kg m-2 Pa-1 s-1 | ✅ |
| 8.49 | s m-1 · - · - · - | s m-1 | s m-1 | ✅ (rf dimensionless) |
| 8.65 | (- · m² · -)/(m²) · √(m s-2 · m · K/K + - · m² s-2) | m s-1 | m3 m-2 s-1 | ✅ (h_Vent in m, T_bar + 273.15 in K) |
| 8.68 | - · m² | m² | m² | ✅ |
| 8.71 branch v < 0.25 | c_leakage | unit of c_leakage | m3 m-2 s-1 | ⚠️ requires c_leakage in m3 m-2 s-1 |
| 8.71 branch v ≥ 0.25 | c_leakage · m s-1 | — | m3 m-2 s-1 | ⚠️ requires c_leakage dimensionless → the two branches disagree, and f jumps at v = 0.25 (Q-4). Implemented as transcribed |
| Cabrera def. | W m-2 / W m-2 | - | - | ✅ |
| Cabrera 6 | W m-2 − - · W m-2 | W m-2 | W m-2 | ✅ |
| Cabrera 7 | W m-2 / W m-2 | - | - | ✅ |
| Cabrera 8 | - + - | - | - | ✅ |

## Checks requested in the task

| Item | Status |
|---|---|
| Eq. 8.2 RHS → W m-2 | ✅ |
| Eq. 8.10 RHS → kg m-2 s-1 | ✅ |
| Eq. 8.45 → kg m-2 s-1 | ✅ |
| Eq. 8.65 → m3 m-2 s-1 | ✅ |
| saturation vapour pressure → Pa | ✅ (`saturation_vapour_pressure`; hPa only in the `_hPa` variant) |
| VP → Pa | ✅ (all `VP_*` names) |
| humidity ratio → kg water / kg dry air | ✅ (`X_air`; never kg m-3) |
| radiation → W m-2 | ✅ (all radiation names) |

## Findings to resolve before activation

1. Eq. 8.71 branch units / discontinuity (Q-4) — affects `f_leakage`, which feeds H_AirOut and MV_AirOut.
2. Eq. 8.41 second term dimension (Q-5) — submodel currently inactive.
3. Eq. 8.43 conversion factor 6.4e-9 is a dimensional constant (kg K J-1 Pa-1); it is used exactly as printed.
