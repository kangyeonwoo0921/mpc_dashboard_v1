# Architecture — Standalone Greenhouse MPC (Phase 2.1)

Status: **structural specification, no optimizer code yet** (DP §32 Phase 2.1; updated 2026-10-06).
Sources: `markdown/claude_codex_standalone_mpc_design_prompt.md` (DP) for structure and work order,
`markdown/greenhouse_mpc_integrated_design_baseline.md` (BL) for references and control logic.
**Prediction-model equations, states and variable names:** `greenhouse_mpc_final_equation_baseline.md`
(EQ: Vanthoor 2011 Ch. 8 / Cabrera 2009 / psychrometrics). EQ supersedes the BL/DP equation forms.
Implementation of EQ: `src/greenhouse_mpc/physics/`, `EQUATION_INVENTORY.md`, `VARIABLE_NAMING.md`,
`VARIABLE_REGISTRY.md`, `UNIT_AUDIT.md`. Conflicts and open decisions: `SOURCE_RECONCILIATION.md`.

Scope: cherry-tomato greenhouse, **recommendation only**. No PLC write, no actuator command, no
change to Growlink/field controller settings (DP §0, BL §0). Heating, fogging and CO2 are outside the
control scope (BL §0).

---

## 1. Layers

```text
Measured / forecast data            (read-only: Growlink snapshot, weather forecast, mock scenarios)
        │
        ▼
State preprocessing                 (T, RH) → VP (PSY-02); X, VPD, dew point derived; sun position; validation
        │
        ├──────────────────────┐
        ▼                      ▼
Reference Scheduler        Forecast / disturbance trajectory d_k..k+N
(crop · season · time)         │
        │                      │
        └──────────┬───────────┘
                   ▼
Supervisor — pre-optimization        admissible sets, day-phase state, safety gates
                   │
                   ▼
MPC Optimizer  ◄──── Prediction Model  x_{k+1} = f_d(x_k, u_k, d_k)
                   │                    (radiation · screen · ventilation · thermal · moisture)
                   ▼
Supervisor — post-optimization        clip, rate/dwell, safety re-check, override log
                   │
                   ▼
Recommendation Output                 first move + trajectory + diagnostics (dashboard later)
```

Each layer is a separate module with its own tests (DP §1). The physics model knows nothing about
crop targets; the scheduler knows nothing about physics; the optimizer never bypasses the supervisor
(DP §35, BL §0).

Runtime modes (BL §0): `LIVE_REAL` (actual sensor/actuator state) and `VIRTUAL_MPC` (simulation
initialized from the current real state). Every control cycle re-anchors the prediction initial state
on the latest measurement (BL §0, BL §25.2).

---

## 2. Vectors

### 2.1 State `x` (DP §2.1, BL §3)

| Symbol | Name | Unit | Role |
|---|---|---|---|
| `T_air` | greenhouse air temperature (Vanthoor T_Air) | °C | dynamic state, Eq. 8.2 |
| `VP_air` | greenhouse air vapour pressure (Vanthoor VP_Air) | Pa | **dynamic moisture state**, Eq. 8.10 |

`x = [T_air, VP_air]` (EQ §1.1, §25). The moisture state is `VP_air` because Vanthoor's balance
Eq. 8.10 is written in vapour pressure; rewriting it for the humidity ratio would need a
transformation not given in the source (EQ §1.1). This replaces the earlier `Xi_in` state of DP §2.1.

RH, the humidity ratio `X_air` (former `Xi`), VPD and dew point are **derived** psychrometric
variables (PSY-02..05), never states. Sensor RH → `VP_air` in preprocessing (PSY-02); `X_air`
[kg water / kg dry air] is computed from `VP_air` and `P_atm` (PSY-03) where thresholds are given in
g/kg (e.g., the field-guide 8 g/kg).

### 2.2 Control `u` (DP §2.2; C-1)

| Symbol | Actuator | Unit / range | Semantics |
|---|---|---|---|
| `u_vent` | roof vent | % [0, 100] | 0 closed, 100 fully-open **command**. % ≠ angle ≠ effective area ≠ ventilation rate (BL §2.2) |
| `u_diffuse` | diffuse screen | % open [0, 100] | 100 fully retracted (open to light), 0 fully deployed |
| `u_shade` | shade screen (aluminium) | % open [0, 100] | 100 fully retracted, 0 fully deployed |

Screen deployment fraction `f = 1 − u/100` (BL §2.1). One convention everywhere; `opening %` and
`deployment %` are never mixed.

These are the **field/recommendation** quantities. The physics uses Vanthoor's control fractions
`u_roof`, `u_shade_screen`, `u_thermal_screen`, `u_diffuse_screen` ∈ [0, 1] (`VARIABLE_NAMING.md`).
The mapping field % → Vanthoor U is **not defined** in EQ (EQUATION_INVENTORY Q-1) and is not
implemented.

Role summary (detail in `CONTROL_LOGIC.md` §2):

- `u_shade`: **daytime shading + night heat retention**. There is no separate thermal screen;
  literature "thermal screen" logic maps to `u_shade` at night only (DP §8).
- `u_diffuse`: **separate actuator** for light distribution / radiation moderation; following the field
  guide (OD-2) it is also used at night (Dec window, `T_out` < 15 °C) and for daytime humidity retention.
  Can be disabled by
  `enable_diffuse_screen_control: false` without changing the rest of the MPC (DP §12).
- Field mapping of `u_vent` to the two vent channels (left/right) is **OD-1**; default: one common
  command, provisional.

### 2.3 Disturbance `d` (DP §3, BL §3)

| Symbol | Name | Unit | Required | Note |
|---|---|---|---|---|
| `T_out` | outdoor temperature | °C | yes | |
| `VP_out` | outdoor vapour pressure | Pa | yes | from outdoor RH + `T_out` (PSY-02); outdoor RH **not in current live data** (G-2) |
| `I_solar` | global solar radiation at the sensor | W/m² | yes | global shortwave; sensor above the cover outside, S01 rear end (operator report 2026-10-07, provisional) |
| `DNI`, `DHI` | direct / diffuse components | W/m² | optional initially | |
| `v_wind` | wind speed | m/s | yes | |
| `theta_wind` | wind direction | deg, true north clockwise | yes | live value is text (G-3) |
| `rain` | rain state | categorical | yes | live value is text (G-3) |
| `time` | timestamp | timezone-aware | yes | |
| `h_sun`, `a_sun` | solar altitude / azimuth | deg | derived | from timestamp and site |

Forecast trajectories over the horizon use the same fields (BL §23). Without a forecast, a
persistence forecast is a candidate test assumption only (to be labelled `temporary_test_fixture`).

### 2.4 Output `y` (DP §4, BL §3)

| Symbol | Name | Unit | Status |
|---|---|---|---|
| `T_air` | greenhouse air temperature | °C | state |
| `VP_air` | greenhouse air vapour pressure | Pa | state |
| `RH_air` | relative humidity | % | derived, PSY-02 (`T_air`, `VP_air`) |
| `X_air` | humidity ratio | kg water / kg dry air | derived, PSY-03 (`VP_air`, `P_atm`) |
| `VPD_air` | vapour pressure deficit | Pa (kPa in user-facing thresholds) | derived, PSY-04 (air VPD) |
| `T_dew_air` | dew point | °C | derived, PSY-05 |
| `f_vent_roof`, `f_leakage` | air fluxes | m³ m⁻² s⁻¹ | Eq. 8.65, 8.71 |
| `H_air_out`, `MV_air_out` | heat / vapour loss to outside | W m⁻², kg m⁻² s⁻¹ | Eq. 8.40 (HEC: Q-12), Eq. 8.45 |
| radiation inputs (`R_glob_sun_air`, …) | radiative terms of Eq. 8.2 | W m⁻² | from the upstream radiation module (EQ §18) |
| `DLI` | accumulated daily light | mol m⁻² d⁻¹ | **blocked** until conversion basis is defined (C-14, OD-4) |

---

## 3. Reference Scheduler (`scheduler/reference_scheduler.py`)

Separate module; not part of the cost function code (BL §4, DP §6).

**Inputs** (BL-A §17.4): growth stage, season/month, time of day, `T_air`, humidity (`VP_air` and the
derived `RH_air` / `VPD_air` / `X_air`), `T_out`, instantaneous solar, accumulated light; optional
forecast, predicted DLI.

**Output** `ReferenceSchedule` per horizon step (BL §4.6, DP Phase 2.4; C-12):

| Field | Meaning |
|---|---|
| `growth_stage`, `season_mode` | `establishment_vegetative` / `flowering_fruit_set` / `fruit_development_harvest`; Aug / Oct / Dec mode |
| `T_ref_C` | crop climate target at step k — **shape of the instantaneous profile is OD-3** |
| `T_soft_min_C`, `T_soft_max_C` | soft temperature band |
| `T_mean24h_band_C` | 24 h-mean target band (e.g., 18–20, Oct 20–21, winter ≥17–18) |
| `T_vent_threshold_C` | field-guide vent-opening temperature (e.g., December 19 / 26–27 / 16.5 / 16 °C + solar modifiers); used by the baseline rule controller and as context — distinct from `T_ref_C` |
| `VPD_ref_kPa`, `VPD_soft_min_kPa`, `VPD_soft_max_kPa` | 0.8 centre (not a universal optimum), 0.5–1.2 soft band |
| `RH_night_risk_percent` | 90 |
| `Xi_day_min_g_per_kg` | 8 (field guide, daytime absolute humidity lower threshold); compared with the derived `X_air` (PSY-03), not a state |
| `instantaneous_light_ref_W_m2` | 600–700, `measurement_basis: unknown` |
| `DLI_target_mol_m2_d` | 20–30 general-tomato candidate (not a cherry-tomato optimum) |
| `condensation_risk_level` | derived from `T_air`, `VP_air` (RH, dew point) |
| `light_preservation_priority` | from stage/season/accumulated light |
| `vent_heat_loss_penalty_multiplier` | seasonal / condensation-dependent |
| `screen_shading_penalty_multiplier` | seasonal / DLI-dependent |
| `source_status` | provenance of each value |

Values and their statuses: `MODEL_ASSUMPTIONS.md` §4.

---

## 4. Prediction Model (`src/greenhouse_mpc/physics/`)

Equations: EQ only, reproduced without changing their form (`EQUATION_INVENTORY.md`). The physics
is continuous-time; discrete propagation is a separate numerical layer (`src/greenhouse_mpc/dynamics/`,
`TIME_DISCRETIZATION.md`: Radau default, RK4 option, ZOH controls, ZOH/linear disturbances).

```text
measurement (T, RH) ──PSY-02──▶ VP_air          derived: X_air (PSY-03), VPD_air (PSY-04), T_dew (PSY-05)

state       x = [T_air, VP_air]
control     u_roof, u_shade_screen (u_thermal_screen at night, conditional), u_diffuse_screen
disturbance T_out, VP_out, wind_speed, wind_direction (stored only), solar_radiation, rain, t

u_roof ──Eq. 8.65 (+ 8.68)──▶ f_vent_roof          C_w(θ) UNRESOLVED: no wind-direction function
wind   ──Eq. 8.71──────────▶ f_leakage             c_leakage calibration required (Q-4)
air flux ──Eq. 8.45──▶ MV_air_out                   air flux ──(HEC: Q-12)──Eq. 8.40──▶ H_air_out
Eq. 8.49 (+ 8.50 missing) ─▶ r_s ─Eq. 8.48─▶ VEC_can_air ─Eq. 8.47─▶ MV_can_air
Eq. 8.43/8.44 condensation, Eq. 8.42 latent heat, Eq. 8.38 FIR, Eq. 8.40 sensible heat
u_shade_screen ──Eq. 8.14–8.17──▶ shade-screen optics (material τ/ρ: manufacturer or measurement)
Cabrera Eq. 6–8 ──▶ diffuse-material optics; u_diffuse_screen → optics UNRESOLVED (DIFF-OPEN)
Eq. 8.39 / 8.41 thermal-screen FIR / airflow, Eq. 8.19 cover conduction: CONDITIONAL
                              │
heat fluxes   ──▶ Eq. 8.2   cap_Air   · dT_air/dt  = Σ gains − Σ losses     [W m⁻²]
vapour fluxes ──▶ Eq. 8.10  cap_VPAir · dVP_air/dt = Σ gains − Σ losses     [kg m⁻² s⁻¹]
```

- **Full source balances, site activation by configuration.** Eq. 8.2 and 8.10 keep every source
  term; devices not present/confirmed are declared `inactive` in `config/model_components.yaml`
  (EQ §0 rule 2). Active at present: `H_can_air`, `R_glob_sun_air`, `H_air_flr`, `H_air_out`;
  `MV_can_air`, `MV_air_out`.
- **Radiation**: no full ray tracing inside optimizer iterations. The dashboard ray model is an
  **upstream radiation-input module** (EQ §18); `mpc_lab` does not import it, and an adapter (data
  interface only) is a later step. No invented optical law for partial diffuse-screen opening.
- **Screen transmittance**: no generic transmittance enters the physics (EQ §14). Material τ/ρ stay
  `null` until manufacturer or measured data exist; the earlier operator-reported 0.25 / 0.80 are kept
  only as unverified metadata (`config/greenhouse.yaml` → `unverified_reference_values`).
- **Physics vs role**: screen physics applies whenever a screen is deployed. "Shade by day, insulate by
  night" is a control role; using Vanthoor's thermal-screen equations for the shade screen is a
  hardware-role mapping, activated only with the material's thermal properties (EQ §15).
- **Not yet defined**: discretization (DISC-01), cap_Air / cap_VPAir (Q-8), Eq. 8.50 (Q-6), field %
  → U mapping (Q-1). Open questions Q-1..Q-13: `EQUATION_INVENTORY.md`.

---

## 5. Supervisor ↔ MPC boundary (`control/supervisor.py`, `control/mpc.py`)

Priority (fixed; BL §5, BL-B §3, DP §9; C-11):

```text
1 safety → 2 temperature protection → 3 condensation / extreme humidity → 4 useful light
→ 5 heat-loss reduction → 6 actuator movement reduction
```

| Responsibility | Supervisor | MPC |
|---|---|---|
| Hard safety overrides (rain, wind, actuator fault, communication fault, manual override) | **owns**; values `field_required` (BL §16.4, DP §25) | never overrides |
| Missing critical sensor | **gate**: no optimization, `recommendation_unavailable` (DP §25) | not run |
| Input bounds [0, 100] | defines admissible set | optimizes inside |
| Rate limits / minimum dwell | defines and enforces (values `null` until known) | movement penalties only |
| Day-phase state machine (NIGHT_INSULATION … SAFETY_OVERRIDE) | selects state, restricts admissible actions (BL §6) | optimizes within the restriction |
| Screen role mapping (shade by day / insulation by night) | enforces | sees the restricted set |
| Temperature / VPD / RH / light targets | — | soft costs and soft constraints |
| Vent-vs-shade trade-off, light vs heat loss | — | objective terms |
| Final clip, dwell re-check, override logging | **post-filter** on the optimizer result | — |

The state machine "limits admissible MPC actions; it does not replace MPC" (BL §6). The baseline rule
controller (`control/baseline_rules.py`) uses the same supervisor and serves as sanity baseline,
comparison target and fallback; it is **not** the final controller (DP §30).

---

## 6. Optimizer (`control/mpc.py`, `control/objective.py`, `control/constraints.py`, `solver/`)

- Decision variables: `u_vent`, `u_diffuse`, `u_shade` over the control horizon (held after it).
- Objective (DP §5, BL §15; weights configurable, no final values):

  `J = w_T Σ(T−T_ref)² + w_H Σ band_penalty(VPD/RH) + w_L Σ light_loss + w_Q Σ Q_vent_proxy
     + w_v Σ(Δu_vent)² + w_d Σ(Δu_diffuse)² + w_s Σ(Δu_shade)²`

  plus the optional daily term `w_DLI · max(0, DLI_target − DLI_pred)²` once DLI is defined (BL §15.3).
  Each component is exposed separately in diagnostics (DP Phase 2.8).
- Soft constraints: winter `T_air` minimum, VPD band (derived `VPD_air`), night RH risk (derived `RH_air`) (BL §16.3, DP §24).
- Solver behind `class MPCSolver: solve(...)`; first candidate `scipy.optimize.minimize`; CasADi only
  with a concrete benefit (DP §26).
- Horizons: sampling 5 min, prediction 60 min, control 20 min — **provisional engineering
  candidates**, configurable, not literature values (DP §23, BL §17, BL-D).

Optimizer code is **not** written in this phase.

---

## 7. Recommendation Output

`MPCRecommendation` (BL §23 extended to three inputs; DP Phase 2.9):

```yaml
MPCRecommendation:
  timestamp:
  mode: recommendation_only
  status: ok | recommendation_unavailable | degraded
  recommendation:            # first move after supervisor post-filter
    roof_vent_percent:
    diffuse_screen_open_percent:
    shade_screen_open_percent:
  trajectory:
    roof_vent_percent: []
    diffuse_screen_open_percent: []
    shade_screen_open_percent: []
  predicted:
    Tin_C: []
    RH_percent: []
    VPD_kPa: []
    effective_radiation_W_m2: []
    Q_vent_W: []
  diagnostics:
    objective_total:
    objective_temperature:
    objective_humidity:
    objective_light:
    objective_heat_loss:
    objective_movement:
  supervisor:
    day_phase_state:
    active_constraints: []
    overrides_applied: []
  source_status:             # provenance summary of parameters used
  confidence:
```

HTTP form for the dashboard (2026-10-09): `GET /api/mpc/recommendation/`, currently a MOCK in
`digital_twin/mpc_mock.py`; field names there follow `VARIABLE_NAMING.md` (`T_air_C`,
`RH_air_percent`, `VPD_air_kPa`, `radiation_crop_W_m2`, `Q_vent_W_m2`) instead of `Tin_C` etc.
Contract: `markdown/frontend_api_contract.md` §3.4.

A `ValidationRecord` (BL §22.2, extended to three inputs) is stored per cycle in passive/shadow modes.

---

## 8. Folder plan (DP §27)

```text
mpc_lab/
  README.md  pyproject.toml  requirements.txt          (Phase 2.2)
  docs/      PROTECTED_PATHS.md  SOURCE_RECONCILIATION.md  ARCHITECTURE.md
             CONTROL_LOGIC.md  MODEL_ASSUMPTIONS.md  greenhouse_mpc_final_equation_baseline.md
             EQUATION_INVENTORY.md  VARIABLE_NAMING.md  VARIABLE_REGISTRY.md  UNIT_AUDIT.md
             VALIDATION_PLAN.md (later)
  config/    crop_reference.yaml  controller.yaml  greenhouse.yaml  actuators.yaml  safety.yaml
             model_components.yaml
  src/greenhouse_mpc/
    types.py  provenance.py  config_loader.py
    physics/  variables.py  constants.py  structures.py  psychrometrics.py  heat_transfer.py
              moisture_transfer.py  ventilation.py  crop_transpiration.py  shade_screen.py
              diffuse_optics.py  balances.py
    (later)   discretization (DISC-01), radiation adapter (EQ §18)
    scheduler/reference_scheduler.py
    control/  objective.py  constraints.py  supervisor.py  baseline_rules.py  mpc.py
    solver/   scipy_solver.py
    simulation/ scenario.py  runner.py
    validation/ metrics.py
  scripts/   run_demo.py  run_scenario.py  compare_baseline_vs_mpc.py
  tests/     (DP §27, §31)
```

Phase status: 2.0, 2.1, 2.2 done; prediction-model equation functions done (`physics/`, tests).
Not started: discretization, scheduler, supervisor, optimizer. See `README.md`.
