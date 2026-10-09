# Model Assumptions — Equations, Parameters, Unknowns

Updated 2026-10-06. **Equation source of truth:** `greenhouse_mpc_final_equation_baseline.md` (EQ:
Vanthoor 2011 Ch. 8, Cabrera 2009, psychrometrics). The earlier BL/DP-based equation registry
(TEMP_001, HUM_001, VENT_001/002, SCREEN_001–003, RAD_001–003) and its assumptions are **superseded**
and no longer used; see §2.

Rules applied (EQ §0, §22; BL §19–§20, §26–§27; DP §33, §35):

- Source equations are reproduced without changing their functional form; no project rewrites.
- Devices absent from the site are not instantiated; no replacement term, no zero claimed as literature.
- Missing relations are marked UNRESOLVED / FIELD REQUIRED / NOT ACTIVATED, never filled.
- Every parameter has `source_type`, `status`, `verified`, `calibration_required` (C-10).
- `unknown`, `provisional`, `field_required`, `do_not_hardcode` values are not fixed here; `unknown`
  is never replaced by zero.

Status vocabulary: `literature_baseline`, `field_guide_baseline`, `provisional`, `calibrated`,
`field_verified`, `unknown`, `field_required`.

---

## 1. Model-level assumptions

| ID | Assumption | Basis | Status |
|---|---|---|---|
| A-1 | Dynamic states `x = [T_air, VP_air]`: one greenhouse-air temperature [°C] and one vapour pressure [Pa] | EQ §1.1, §25 (Vanthoor Eq. 8.2, 8.10) | fixed |
| A-2 | The humidity ratio `X_air` (former `Xi`) is a **derived** psychrometric variable (PSY-03), not a state; RH, VPD, dew point likewise derived (PSY-02, -04, -05) | EQ §1.1, §2 | fixed |
| A-3 | Model is continuous-time; discretization method not chosen (DISC-01) | EQ §0 rule 7 | open |
| A-4 | Sampling 5 min, prediction 60 min, control 20 min remain controller candidates only, not part of the physics | DP §23 | provisional |
| A-5 | Eq. 8.2 / 8.10 keep every source term; site activation per term in `config/model_components.yaml` | EQ §3–§4, §0 rule 2 | fixed |
| A-6 | Screen physics applies whenever a screen is deployed; day/night role is a control concept. Thermal-screen equations for the shade screen are a hardware-role mapping, conditional on material data | EQ §15 | conditional |
| A-7 | No ray tracing inside the optimizer; the dashboard ray model is an upstream radiation-input module, connected later through a data adapter | EQ §18 | fixed |
| A-8 | Atmospheric pressure `P_atm` is measured or explicitly configured; no fixed value inserted | EQ §2.3 | open |
| A-9 | Wind direction is stored as input only; no C_w(θ) function | EQ §13 | unresolved |
| A-10 | Partial diffuse-screen opening has no optical relation | EQ §17.6 | unresolved |
| A-11 | `u_vent` is one common command for both roof-vent channels (field level) | OD-1 | provisional |
| A-12 | Field % → Vanthoor control fraction U ∈ [0, 1] mapping not defined | EQ (absent), EQUATION_INVENTORY Q-1 | open |

---

## 2. Equation registry

The adopted registry is EQ §20, implemented and tracked in `EQUATION_INVENTORY.md` (inputs, outputs,
parameters, units, status, code location) with the unit check in `UNIT_AUDIT.md`.

| ID | Source | Status |
|---|---|---|
| PSY-01..05 | Magnus / psychrometric definitions (EQ §2) | fixed, implemented |
| TEMP-01 | Vanthoor Eq. 8.2 | fixed, wrapper implemented |
| HUM-01 | Vanthoor Eq. 8.10 | fixed, wrapper implemented |
| HEAT-01, FIR-01, LAT-01 | Eq. 8.40, 8.38, 8.42 | fixed, implemented |
| COND-01 / COND-02 | Eq. 8.43 / 8.44 | fixed / optional, implemented |
| MV-01 | Eq. 8.45 | fixed, implemented |
| CROP-01..03 | Eq. 8.47, 8.48, 8.49 (8.50 missing) | fixed / params required |
| VENT-01, VENT-02 | Eq. 8.65, 8.68 | fixed, implemented |
| LEAK-01 | Eq. 8.71 | fixed / calibration required; transcription to check (Q-4) |
| SHADE-01, SHADE-02 | Eq. 8.14–8.15, 8.16–8.17 | fixed, implemented |
| THERMAL-01, THERMAL-02 | Eq. 8.39, 8.41 | conditional (Q-5) |
| COVER-01 | Eq. 8.19 | conditional to layer match |
| DIFF-01..03 | Cabrera 2009 definitions, Eq. 6–8 | fixed physics, implemented |
| WINDDIR-01 | — | unresolved function |
| DIFF-OPEN | — | do not invent |
| DISC-01 | — | implementation decision later |

Superseded (not used): the former TEMP_001 lumped `C_eff`/`U_eff` balance, HUM_001 humidity-ratio
balance, VENT_001 generalized form with `f_diffuse·f_shade`, SCREEN_001/002 Bailey `U_eff` combination,
SCREEN_003 airflow modifiers, RAD V1 multiplicative surrogate `I_eff = I·τ_diffuse·τ_shade`, and the
`Q_solar = eta_solar·A_floor·I_eff` link. They conflict with EQ §0/§22 (project rewrites, invented
screen interpolation).

---

## 3. Physical parameters (EQ §21; full list in `VARIABLE_REGISTRY.md`)

| Parameter | Used in | Value | Status |
|---|---|---|---|
| `A_floor`, `A_roof`, `h_vent` | Eq. 8.65, 8.68 | null | field_required |
| `C_d`, `C_w` | Eq. 8.65 | null | calibration or geometry-matched source |
| `c_leakage` | Eq. 8.71 | null | calibration required (unit question Q-4) |
| C_w wind-direction table | WINDDIR-01 | null | literature or calibration required |
| `h_roof`, `lambda_roof` (+ semi-permanent layer) | Eq. 8.19 | null | field / manufacturer; conditional |
| shade screen `tau`, `rho` (PAR, NIR) | Eq. 8.16–8.17 | null | manufacturer or measurement |
| shade screen `tau_FIR`, `K_ThScr` | Eq. 8.39, 8.41 | null | only if activated as thermal screen |
| diffuse screen `tau_bb`, `tau_bd`, `tau_d` | Cabrera Eq. 6–8 | null | manufacturer or measurement |
| diffuse partial-opening relation | DIFF-OPEN | — | unresolved |
| `LAI`, `r_b`, `r_s_min`, Eq. 8.50 parameters | Eq. 8.48–8.50 | null | measurement / source / calibration |
| `cap_air`, `cap_VP_air` | Eq. 8.2, 8.10 | null | definition not in EQ (Q-8) |
| `rho_air`, `c_p_air`, `delta_H`, `gamma` | Eq. 8.41, 8.42, 8.48 | null | value and source required (Q-11) |
| `P_atm` | PSY-03 | null | measured or configured (A-8) |
| `HEC_12` per surface pair | Eq. 8.40, 8.43 | null | from source equation/table or calibration (Q-12) |
| `s_MV12` | Eq. 8.44 | null | optional, not guessed |
| actuator speeds, dwell, rate limits | supervisor | null | field_required |
| wind safety limit, rain rule | supervisor | null | field_required |

Universal constants (σ, R, M_water, g) are used directly (EQ §0 rule 5; Q-13 on Vanthoor's rounded
values). Prototype runs may use clearly labelled `temporary_test_fixture` values; none are defined.

---

## 4. Crop / climate references (scheduler inputs)

Priority: field guide → cherry-tomato study → general tomato literature → target-site data
(BL-A §17). Candidate values are not converted into hard constraints automatically (BL-A §16).

| Variable | Value | Source type | Status | Use |
|---|---|---|---|---|
| 24 h mean temperature | 18–20 °C | field_guide_baseline | field_guide_baseline | reference band |
| October pre-winter 24 h mean | 20–21 °C | field_guide_baseline | field_guide_baseline | seasonal mode |
| Winter minimum | 13–14 °C (working 14) | field_guide_baseline | field_guide_baseline | soft constraint / warning (C-3) |
| Winter 24 h mean | ≥ 17–18 °C (working 18) | field_guide_baseline | field_guide_baseline | reference (C-3) |
| December vent-opening temperatures | morning 19 (+≤1 solar), afternoon 26–27 (+≤2 accumulated), early evening 16.5, night 16 (+≤2) °C | field_guide_baseline | field_guide_baseline | `T_vent_threshold`, baseline rule controller (C-12) |
| December heating schedule | day 16 / night 14 °C | field_guide_baseline | context only | heating out of scope |
| Night RH risk | > 90 % | field_guide_baseline | field_guide_baseline | soft constraint |
| Daytime absolute humidity lower threshold | 8 g/kg | field_guide_baseline | field_guide_baseline | reference |
| Spring RH | 65 ± 5 % | cherry_tomato_study (Cupid) | supporting | not a target |
| VPD band / centre | 0.5–1.2 kPa / 0.8 kPa | general_tomato_literature | literature_baseline | soft band; 0.8 not a universal optimum (do_not_hardcode) |
| Instantaneous light | 600–700 W/m² | field_guide_baseline | field_guide_baseline; guide measurement basis unknown, site sensor is global, above the cover outside (2026-10-07) | light reference (C-13) |
| DLI | 20–30 mol m⁻² d⁻¹ | general_tomato_literature | candidate | not a cherry-tomato optimum (do_not_hardcode) |
| Cherry-tomato natural DLI example | 14.5 mol m⁻² d⁻¹ | cherry_tomato_study | context | not an optimum |
| Cumulative light 1600 J | — | field_guide_baseline | **do not use** (unit unverified) | none |
| Night screen closure | ≈ 80 % "when needed" | field_guide_baseline | field_guide_baseline | shade-screen night reference |
| December aluminium screen timing | sunset −1 h → sunrise +0.5 h | field_guide_baseline | fallback / comparison | shade screen (mapping provisional) |
| December diffuse screen timing / Tout < 15 °C | sunset −2 h → sunrise +2 h | field_guide_baseline | field_guide_baseline (OD-2 adopted) | diffuse screen night rule |
| Rain roof vent | ≤ 5 % | field_guide_baseline | reference only (C-4) | baseline comparison |
| FAO delayed opening radiation | 50–150 W/m² | greenhouse_physics_literature | design reference | do_not_hardcode |
| Growth stages | establishment_vegetative / flowering_fruit_set / fruit_development_harvest | BL §4.2 | structure | scheduler |

Instantaneous `T_ref(t)` profile from the 24 h-mean targets: **unknown** (OD-3).

---

## 5. Values already recorded by the dashboard project (read-only, not adopted yet)

The dashboard's `config/radiation_v1/` records operator reports (2026-09-30/10-01). They are not in
EQ and are not manufacturer or measured values. **User decision 2026-10-06:** the screen values
(0.25 / 0.80) are **not used in any physics calculation**; they are kept only as `provisional /
unverified` metadata in `config/greenhouse.yaml` → `unverified_reference_values`. The physics
parameters (`radiation.shade_screen_optics`, `radiation.diffuse_screen_optics`) stay `null` until
manufacturer specifications or field measurements exist.

| Item | Recorded value | Basis | Use in mpc_lab |
|---|---|---|---|
| Cover | single-layer PO film, direct transmittance 0.85 | operator report, basis unstated | metadata; no cover-transmittance term in EQ |
| Shade screen | aluminium, 70 % shading → 0.30 (operator report 2026-10-07; drawing 75 %) | operator report | **unverified metadata only, not used in physics** |
| Diffuse screen | 'Ultra', 10 % shading → 0.90 (operator report 2026-10-07) | operator report | **unverified metadata only, not used in physics** |
| Screen channels | `차광커튼1` → diffuse (10 % 'Ultra'), `차광커튼2` → shade (70 % aluminium) | operator report 2026-10-07 | live mapping |
| Screen semantics | 100 % = open (retracted) | operator report | matches BL §2.1 |
| Vents | left/right independent, 1.2 m leaves; fully open = 110° between ridge post and leaf (2026-10-07, 100–120° reported; supersedes 100 % = 90°) | operator report | OD-1; percent→angle linearity unverified |
| Site | lat 35.837, lon 126.709, elev 3 m, long axis +X at 284° | user lookup / compass | sun position input, provisional |

---

## 6. Data availability (read-only check of `live_data/fixtures/growlink_live_sample.json`)

| Required (DP §3, BL §23) | In current Growlink sample | Note |
|---|---|---|
| `T_air`, indoor RH → `VP_air` (PSY-02) | yes (`실내온도`, `내부습도`) | |
| `T_out` | yes (`외부기온`) | |
| outdoor RH → `VP_out` (PSY-02) | **no** | G-2: blocks live optimization |
| solar global | yes (`일사량`) | global shortwave W/m², above the cover outside (2026-10-07, provisional) |
| DNI / DHI | no | optional initially |
| wind speed | yes (`풍속`) | |
| wind direction | text (`"45° 북동"`) | parse (G-3) |
| rain | text (`강우`) | parse (G-3) |
| roof vent | two channels (`천창 좌(L)`, `천창 우(R)`) | OD-1 |
| shade / diffuse screen | `차광커튼2` (shade), `차광커튼1` (diffuse) | operator report 2026-10-07 |
| uncontrolled devices | side vents ×4, vertical curtains ×4, boiler, fans | A-9 |

No live connection is required in this phase; mock scenarios A–F (DP §29) come in Phase 2.7.

---

## 7. Do-not-hardcode (BL §27, BL-B §11, DP)

VPD 0.8 as universal optimum; DLI 20–30 as cherry-tomato optimum; field-guide 1600 J without unit
verification; FAO 50–150 W/m² as fixed threshold; Campen 2.5 % screen gap; Hahn 15 min persistence;
Jung 30 min horizon; Bailey α/β; Liu empirical formula; rain 5 % as structural limit; generic maximum
wind limit; DP example 2.5 % opening (DP §14).

## 8. Stop items reported

From DP §33 and EQ §21/§24: exact screen optical properties (shade τ/ρ, diffuse τ_bb/τ_bd/τ_d);
screen thermal properties (τ_FIR, K_ThScr) if the shade screen is used as thermal screen; roof-vent
geometry (A_roof, h_vent, A_floor) and the field % → U_Roof mapping; C_d, C_w; leakage coefficient;
cover layer properties; wind safety limit; rain safety rule; actuator speeds. Blocking for live runs:
outdoor RH (G-2). Missing source equations: partial diffuse-screen opening (DIFF-OPEN), wind-direction
function (WINDDIR-01), discretization (DISC-01), Eq. 8.50 resistance factors. Open interpretation
questions: Q-1..Q-13 in `EQUATION_INVENTORY.md`. DLI conversion remains blocked (C-14).
