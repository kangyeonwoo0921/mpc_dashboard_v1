# Claude Code / Codex Prompt — Standalone Greenhouse MPC Module Design & Implementation

## 0. Task Summary

Design and implement a **standalone greenhouse MPC prototype** for a cherry-tomato greenhouse.

The current control scope is:

- **Roof vent**
- **Diffuse screen**
- **Shade screen**
  - The shade screen is also used as the practical **night insulation / heat-retention screen**
  - There is **no separate dedicated thermal screen**

The MPC must be developed **independently from the existing 3D monitoring dashboard**.

### Critical repository rule

**DO NOT modify, refactor, rename, move, delete, or import implementation code into the existing 3D dashboard unless explicitly requested later.**

Create a completely separate working directory for the MPC.

Recommended location:

```text
mpc_lab/
```

or, if the repository already contains a clearly separated research directory:

```text
research/mpc_lab/
```

Use only read-only inspection of the existing project if needed to understand naming conventions or future integration points.

The initial deliverable is **not live greenhouse control**.

The target is:

```text
physics-informed greenhouse prediction
+
crop/season reference scheduler
+
MPC recommendation
+
offline simulation / shadow-mode-ready interface
```

No PLC writes.
No actuator command transmission.
No modification of Growlink or field controller settings.

---

# 1. First Principle — Architecture Before Coding

Before implementing the optimizer, establish and document the control architecture.

The MPC must be divided into the following layers:

```text
Measured / forecast data
        │
        ▼
State preprocessing
        │
        ▼
Reference Scheduler
        │
        ▼
Prediction Model
        │
        ▼
MPC Optimizer
        │
        ▼
Supervisory / Safety Layer
        │
        ▼
Recommendation Output
```

These layers must remain separate.

Do NOT implement one large function containing:
- greenhouse physics,
- crop setpoints,
- actuator rules,
- optimizer logic,
- safety rules.

Each layer must be independently testable and replaceable.

---

# 2. Structural MPC Design

## 2.1 State vector

Use the initial state vector:

```math
x_k =
[
T_in,k,
Xi_in,k
]^T
```

where:

```yaml
Tin:
  meaning: indoor greenhouse air temperature
  unit: degC

Xi_in:
  meaning: indoor humidity ratio / absolute moisture state
  role: dynamic moisture state
```

Do **not** use RH as the primary conserved moisture state.

RH and VPD should be calculated as outputs from:

```text
Tin + Xi_in
```

Reason:

```text
sensor measurement → RH
dynamic mass balance → Xi
evaluation / user output → RH + VPD
```

---

## 2.2 Control vector

There are **three** actuator variables.

```math
u_k =
[
u_vent,k,
u_diffuse,k,
u_shade,k
]^T
```

### 1. Roof vent

```yaml
u_vent:
  unit: percent
  range: [0, 100]
  meaning:
    0: closed
    100: fully_open_command
```

Important:

```text
vent opening %
!=
physical opening angle
!=
effective opening area
!=
ventilation rate
```

Keep those mappings separate.

### 2. Diffuse screen

```yaml
u_diffuse:
  unit: percent_open
  recommended_semantics:
    100: fully_retracted_open_to_light
    0: fully_deployed
```

Primary roles:

```text
light distribution
radiation moderation
possible airflow resistance
```

Do not assume it has the same thermal behavior as the shade screen.

### 3. Shade screen

```yaml
u_shade:
  unit: percent_open
  recommended_semantics:
    100: fully_retracted_open_to_light
    0: fully_deployed
```

Primary roles:

```text
day:
  reduce excessive solar gain / shading

night:
  practical heat-retention / insulation function
```

There is **no separate thermal screen**.

Therefore all literature referring to a thermal screen must be translated carefully:

```text
thermal-screen logic
→ potentially applicable to u_shade at night

NOT automatically applicable to u_diffuse
```

This distinction must be explicit in code comments and configuration.

---

# 3. Disturbance Vector

Initial disturbance vector:

```math
d_k =
[
T_out,
Xi_out,
I_solar,
v_wind,
theta_wind,
rain,
time
]
```

Recommended schema:

```yaml
disturbances:

  Tout_C:
    required: true

  Xi_out:
    required: true

  solar_global_W_m2:
    required: true

  DNI_W_m2:
    required: optional_initially

  DHI_W_m2:
    required: optional_initially

  wind_speed_m_s:
    required: true

  wind_direction_deg:
    required: true

  rain_state:
    required: true

  timestamp:
    required: true

  solar_altitude_deg:
    derived: true

  solar_azimuth_deg:
    derived: true
```

If DNI/DHI are unavailable initially, permit a simplified solar model.

Do not block implementation waiting for full ray-tracing inputs.

---

# 4. Output Vector

Recommended outputs:

```yaml
outputs:

  Tin_C:
  RH_in_percent:
  Xi_in:
  VPD_kPa:

  effective_crop_radiation_W_m2:

  DLI_accumulated_mol_m2_d:

  predicted_ventilation_rate:
    unit: m3_s_or_air_changes
    status: model_dependent

  predicted_heat_loss_W:
  predicted_solar_gain_W:
```

These outputs should support:
- debugging,
- dashboard integration later,
- model calibration,
- objective-function decomposition.

---

# 5. Control Objective

The controller should optimize greenhouse climate over a prediction horizon while balancing:

```text
temperature tracking
+
humidity / VPD control
+
crop-light preservation
+
winter heat-loss reduction
+
actuator movement reduction
```

Do NOT optimize only temperature.

Initial conceptual objective:

```math
J =
J_T
+
J_H
+
J_light
+
J_heat
+
J_move
```

Expanded:

```math
J =
w_T * Σ(T_pred - T_ref)^2
+
w_H * Σ(humidity_band_penalty)
+
w_L * Σ(light_loss_penalty)
+
w_Q * Σ(ventilation_heat_loss_penalty)
+
w_v * Σ(Δu_vent)^2
+
w_d * Σ(Δu_diffuse)^2
+
w_s * Σ(Δu_shade)^2
```

All weights must be configurable.

Do not hard-code final values.

---

# 6. Reference Scheduler

The MPC must NOT use one fixed temperature setpoint.

Create:

```text
reference_scheduler.py
```

The scheduler should determine climate references from:

```text
growth stage
+
season/month
+
time of day
+
instantaneous solar radiation
+
accumulated light / DLI
+
humidity / condensation risk
+
outdoor temperature
```

Initial growth-stage abstraction:

```yaml
growth_stage:

  establishment_vegetative:
    priorities:
      - temperature_stability
      - gradual_light_acclimation

  flowering_fruit_set:
    priorities:
      - preserve_useful_light
      - stable_temperature
      - humidity_control

  fruit_development_harvest:
    priorities:
      - preserve_light
      - avoid_condensation
      - maintain_temperature
```

---

# 7. Initial Crop / Seasonal Reference Values

Use these as **initial working baselines**, not immutable constants.

## General production

```yaml
mean_24h_temperature_C:
  lower: 18
  upper: 20
```

## October / pre-winter active growth

```yaml
october_mean_24h_temperature_C:
  lower: 20
  upper: 21
```

Purpose:

```text
maintain relatively active development
before winter low-light conditions
```

## Winter

```yaml
winter:
  minimum_temperature_C:
    practical_reference: 14

  mean_24h_temperature_min_C:
    preferred: 18

  night_RH_high_risk_percent:
    value: 90
```

## VPD

```yaml
VPD_working_band_kPa:
  lower: 0.5
  upper: 1.2

VPD_initial_center_kPa:
  value: 0.8
```

Treat as a soft physiological band.

Do NOT force exact tracking to 0.8 kPa.

## Light

```yaml
instantaneous_radiation_reference_W_m2:
  lower: 600
  upper: 700
```

For autumn/winter:

```text
avoid unnecessary shading
especially when accumulated DLI is still low
```

General tomato DLI literature may be retained as:

```yaml
DLI_initial_reference_mol_m2_d:
  lower: 20
  upper: 30
  status: general_tomato_baseline_only
```

Do not treat it as a universal cherry-tomato optimum.

---

# 8. Screen Role Separation

This is mandatory.

## 8.1 Diffuse screen

Model separately:

```yaml
diffuse_screen:
  primary_effects:
    - radiation_distribution
    - effective_transmission
    - possible_airflow_resistance

  night_insulation_role:
    assume: false
    unless_field_verified: true
```

## 8.2 Shade screen

```yaml
shade_screen:

  daytime:
    primary_effect:
      - reduce_excess_solar_gain

  nighttime:
    primary_effect:
      - heat_retention
      - practical_insulation

  humidity_interaction:
    possible: true
```

If literature uses `thermal screen`, map it to the **nighttime role of the shade screen** only where physically reasonable.

Create an explicit adapter/config comment such as:

```yaml
literature_mapping:

  thermal_screen:
    project_actuator: shade_screen
    usage:
      - night_insulation
      - dawn_opening
      - humidity_relief_logic
    confidence: provisional

  shading_screen:
    project_actuator: shade_screen
    usage:
      - daytime_shading

  diffuse_screen:
    project_actuator: diffuse_screen
```

---

# 9. Supervisory Control Logic

MPC should operate under a supervisory layer.

Create:

```text
supervisor.py
```

Priority:

```text
1. safety
2. temperature protection
3. condensation / extreme humidity protection
4. preserve useful light
5. reduce heat loss
6. reduce actuator movement
```

---

# 10. Roof Vent Baseline Logic

## Temperature logic

```text
IF Tin > dynamic Tref
THEN increase ventilation
subject to:
  Tout
  wind
  rain
  predicted cooling effectiveness
```

## Humidity logic

```text
IF RH is excessive
OR VPD too low
OR condensation risk is high

THEN permit ventilation
even when cooling demand is small
```

In winter:

```text
ventilation benefit
vs
heat-loss penalty
```

must be evaluated.

---

# 11. Daytime Screen Logic

Initial preferred cool-season sequence:

```text
Tin / solar rise
      ↓
use roof ventilation first
      ↓
predict response
      ↓
if temperature still excessive
AND radiation excessive
AND light availability is sufficient
      ↓
deploy shade screen
```

Do NOT use:

```text
high solar
→ automatically deploy shade screen
```

because autumn/winter production is often light-limited.

---

# 12. Diffuse-Screen Logic

Do not initially optimize diffuse screen using the exact same objective as shade screen.

Initial implementation:

```yaml
diffuse_screen_control:
  mode: conservative

  objectives:
    - improve_light_distribution
    - moderate_excess_direct_radiation

  default_policy:
    preserve_light: true

  MPC_status:
    include_as_control_input: true
    strong_penalty_on_unnecessary_movement: true
```

If its true field function is uncertain, make it easy to disable:

```yaml
enable_diffuse_screen_control: true
```

and allow:

```yaml
enable_diffuse_screen_control: false
```

without changing the rest of the MPC.

---

# 13. Night Shade-Screen Logic

Because the shade screen is also used for insulation:

```text
night:
  low/no solar
  low Tout
      ↓
  deploy shade screen for heat retention
```

At dawn:

```text
shade screen deployed
        ↓
check RH / condensation
        ↓
check useful solar gain
        ↓
progressively retract screen
```

Do not use fixed sunrise-only logic.

Use:

```text
solar gain
+
Tin - Tout
+
humidity condition
```

---

# 14. Humidity Under Closed Shade Screen

Literature indicates that small screen opening can help release humidity, but can also create cold downdrafts and spatial temperature gradients.

Therefore implement only as a controlled option:

```yaml
night_humidity_relief:

  first_option:
    action: small_shade_screen_crack

  constraints:
    max_opening_change: configurable
    dwell_time: configurable

  then:
    observe_predicted_humidity_response: true

  fallback:
    limited_roof_ventilation
```

Do NOT hard-code literature examples such as 2.5% opening.

---

# 15. Anti-Chattering

Both screens and roof vents are mechanical actuators.

Implement:

```yaml
actuator_protection:

  roof_vent:
    minimum_dwell_time:
    maximum_rate_of_change:
    movement_penalty:

  diffuse_screen:
    minimum_dwell_time:
    maximum_rate_of_change:
    movement_penalty:

  shade_screen:
    minimum_dwell_time:
    maximum_rate_of_change:
    movement_penalty:
```

Initial values may be provisional.

The code architecture must allow field actuator speeds to replace them later.

---

# 16. Prediction Model Structure

Create separate models:

```text
models/
  thermal.py
  moisture.py
  ventilation.py
  screen.py
  radiation.py
```

---

# 17. Thermal Model

Start with a 0-D / lumped gray-box model.

Recommended structure:

```math
C_eff * dTin/dt
=
Q_solar
- Q_cover
- Q_vent
+ Q_screen_insulation
+ Q_other
```

Practical initial form:

```math
C_eff * dTin/dt
=
Q_solar
-
U_eff * A_cover * (Tin - Tout)
-
rho_air * cp * Vdot * (Tin - Tout)
```

Screen states modify:

```text
Q_solar
U_eff
possibly Vdot
```

Do not add unnecessary complexity in V1.

---

# 18. Moisture Model

Initial structure:

```math
rho_air * V_greenhouse * dXi_in/dt
=
E_crop
-
rho_air * Vdot * (Xi_in - Xi_out)
-
M_cond
```

For V1:

```yaml
crop_transpiration:
  may_use: simplified_model

condensation:
  may_start_as: simplified_or_disabled
  but:
    must_be_explicitly_documented: true
```

---

# 19. Natural Ventilation Model

Use a combined wind + buoyancy structure.

Generic project form:

```math
Vdot =
Cd * A_eff *
sqrt(
  Cw * wind_speed^2
  +
  buoyancy_term
)
```

Inputs:

```yaml
ventilation_model_inputs:
  - vent_opening_percent
  - effective_opening_area
  - vent_opening_angle
  - wind_speed
  - wind_direction
  - Tin
  - Tout
  - screen_states
```

Do not assume:

```text
vent opening %
=
ventilation %
```

---

# 20. Screen–Vent Interaction

The screens may affect airflow.

Use:

```math
Vdot_eff
=
Vdot_vent *
f_diffuse(u_diffuse) *
f_shade(u_shade)
```

Initial `f_*` can be provisional.

Architecture requirement:

```text
screen airflow modifier
must be replaceable by:
  measured data
  manufacturer information
  calibrated coefficient
```

Do not assume both screens have identical resistance.

---

# 21. Radiation Model

Do not perform full ray tracing inside every MPC optimizer iteration.

Create a clean interface:

```python
effective_radiation = radiation_model.predict(
    timestamp=...,
    solar=...,
    diffuse_screen=...,
    shade_screen=...,
)
```

V1:

```math
I_eff
=
I_out
*
tau_cover
*
tau_diffuse(u_diffuse)
*
tau_shade(u_shade)
```

Later:

```text
replace simple model
→ ray-derived lookup table / surrogate
```

without changing MPC code.

---

# 22. Continuous → Discrete Model

MPC requires:

```math
x_{k+1} = f_d(x_k, u_k, d_k)
```

Implement one clear discretization method initially.

Recommended:

```text
forward Euler
```

for prototype transparency.

Example:

```math
T_{k+1}
=
T_k
+
Delta_t * dT/dt
```

```math
Xi_{k+1}
=
Xi_k
+
Delta_t * dXi/dt
```

Keep discretization isolated so RK4 or other integration can later replace it.

---

# 23. Sampling Time / Horizons

Do not claim final values yet.

Start with configurable engineering candidates:

```yaml
sampling_time_minutes:
  initial: 5

prediction_horizon_minutes:
  initial: 60

control_horizon_minutes:
  initial: 20
```

These are NOT final literature-derived values.

Make them configuration parameters.

Later perform sensitivity tests.

---

# 24. MPC Constraints

## Actuator bounds

```yaml
roof_vent_percent: [0, 100]
diffuse_screen_percent: [0, 100]
shade_screen_percent: [0, 100]
```

## Soft crop constraints

```yaml
temperature:
  winter_min_C: 14

VPD:
  working_band_kPa: [0.5, 1.2]

night_RH:
  risk_threshold_percent: 90
```

## Rate constraints

```yaml
delta_roof_vent_max:
delta_diffuse_screen_max:
delta_shade_screen_max:
```

Keep `null / provisional` until hardware behavior is known.

---

# 25. Safety Layer

Hard safety constraints are NOT literature-driven.

Create config placeholders:

```yaml
safety:

  rain:
    vent_max_percent: null

  wind:
    maximum_safe_speed_m_s: null

  communication_failure:
    action: recommendation_unavailable

  missing_sensor:
    action: do_not_optimize
```

No fake values.

---

# 26. Solver

Do not over-engineer initially.

The first implementation should support a nonlinear prediction function.

Recommended candidate stack:

```text
Python
NumPy
SciPy
```

Use `scipy.optimize.minimize` initially if sufficient.

Optional later:

```text
CasADi
```

but do NOT introduce CasADi unless it provides a concrete benefit.

Keep solver behind:

```python
class MPCSolver:
    solve(...)
```

so it is replaceable.

---

# 27. Standalone Folder Structure

Create ONLY inside the new MPC directory.

Recommended:

```text
mpc_lab/
│
├── README.md
├── pyproject.toml
├── requirements.txt
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── MODEL_ASSUMPTIONS.md
│   ├── CONTROL_LOGIC.md
│   ├── PARAMETER_REGISTRY.md
│   └── VALIDATION_PLAN.md
│
├── config/
│   ├── crop_reference.yaml
│   ├── controller.yaml
│   ├── greenhouse.yaml
│   ├── actuators.yaml
│   └── safety.yaml
│
├── src/
│   └── greenhouse_mpc/
│       ├── __init__.py
│       │
│       ├── types.py
│       ├── psychrometrics.py
│       │
│       ├── scheduler/
│       │   └── reference_scheduler.py
│       │
│       ├── models/
│       │   ├── thermal.py
│       │   ├── moisture.py
│       │   ├── ventilation.py
│       │   ├── screen.py
│       │   ├── radiation.py
│       │   └── discrete_model.py
│       │
│       ├── control/
│       │   ├── objective.py
│       │   ├── constraints.py
│       │   ├── supervisor.py
│       │   ├── baseline_rules.py
│       │   └── mpc.py
│       │
│       ├── solver/
│       │   └── scipy_solver.py
│       │
│       ├── simulation/
│       │   ├── scenario.py
│       │   └── runner.py
│       │
│       └── validation/
│           └── metrics.py
│
├── scripts/
│   ├── run_demo.py
│   ├── run_scenario.py
│   └── compare_baseline_vs_mpc.py
│
└── tests/
    ├── test_psychrometrics.py
    ├── test_scheduler.py
    ├── test_ventilation.py
    ├── test_screen.py
    ├── test_discrete_model.py
    ├── test_supervisor.py
    └── test_mpc_sanity.py
```

---

# 28. Existing 3D Dashboard Protection Rules

This is mandatory.

Before coding:

1. Detect repository root.
2. Identify the existing dashboard folders.
3. Record them in `mpc_lab/docs/PROTECTED_PATHS.md`.
4. Treat those paths as read-only.

Do NOT:

```text
modify Django settings
modify Three.js code
modify templates
modify static files
modify Blender files
move dashboard modules
rename existing project packages
change current API routes
change current tests
change current database
```

Do NOT add imports from `mpc_lab` into the dashboard yet.

Integration will be a separate future phase.

---

# 29. Mock Data First

No live field connection is required for this implementation.

Create mock scenario data with:

```yaml
weather:
  Tout:
  RHout:
  solar:
  wind_speed:
  wind_direction:
  rain:

greenhouse:
  Tin:
  RHin:

actuators:
  roof_vent:
  diffuse_screen:
  shade_screen:
```

Create at least:

```text
Scenario A — sunny October daytime
Scenario B — winter sunny morning
Scenario C — winter cloudy humid morning
Scenario D — high RH night with shade screen deployed
Scenario E — hot/high-radiation daytime
Scenario F — rain safety case
```

---

# 30. Baseline Rule Controller

Implement a rule-based controller before MPC.

Purpose:

```text
sanity baseline
+
comparison target
+
fallback behavior
```

It must be clearly marked:

```text
NOT the final controller
```

Its rules should follow:

```text
temperature high
→ vent

vent insufficient + solar excessive
→ shade screen

low winter light
→ preserve light

night cold
→ deploy shade screen

night high humidity under deployed shade screen
→ limited controlled humidity relief

rain/wind
→ supervisor override
```

Diffuse screen should use a conservative rule until field function is better verified.

---

# 31. Required Tests Before MPC Optimization

Do not proceed to optimizer tuning until these pass.

## Direction tests

```text
higher Tin
→ vent demand must not decrease

higher wind at same vent %
→ predicted ventilation must change

lower Tout in winter
→ vent heat-loss penalty must increase

more shade-screen deployment
→ transmitted radiation must decrease

more diffuse-screen deployment
→ effective radiation model must respond

low winter DLI
→ shading penalty must increase

high RH / low VPD
→ humidity-relief action must become possible
```

## Safety tests

```text
rain override
→ unsafe vent command blocked

missing critical sensor
→ no recommendation

invalid % input
→ validation error
```

---

# 32. Work Flow

Follow this order strictly.

---

## Phase 2.0 — Repository Isolation

Tasks:

```text
- inspect repository structure
- identify protected dashboard paths
- create standalone mpc_lab/
- create PROTECTED_PATHS.md
- make no changes outside mpc_lab/
```

Deliverable:

```text
mpc_lab/docs/PROTECTED_PATHS.md
```

---

## Phase 2.1 — Structural Specification

Before model coding, create:

```text
docs/ARCHITECTURE.md
docs/CONTROL_LOGIC.md
docs/MODEL_ASSUMPTIONS.md
```

The architecture document must explicitly define:

```text
x
u
d
y
reference scheduler
prediction model
supervisor
optimizer
recommendation output
```

Also document:

```text
shade screen = daytime shade + nighttime insulation

diffuse screen = separate actuator
```

Do not code MPC before this document is complete.

---

## Phase 2.2 — Types and Configuration

Implement:

```text
types.py
config YAMLs
input validation
```

Define dataclasses or equivalent typed structures for:

```text
GreenhouseState
WeatherInput
ActuatorState
ReferenceSchedule
MPCConfig
MPCRecommendation
```

---

## Phase 2.3 — Psychrometrics

Implement:

```text
RH + T → Xi
Xi + T → RH
T + RH → VPD
```

Add unit tests.

This must be completed before the moisture model.

---

## Phase 2.4 — Reference Scheduler

Implement August / October / December / growth-stage logic.

Output dynamic:

```text
Tref
temperature bounds
VPD band
light priority
DLI target/reference
vent heat-loss weight modifier
screen light-loss weight modifier
```

---

## Phase 2.5 — Prediction Models

Implement in this order:

```text
1. radiation
2. screen effects
3. ventilation
4. thermal
5. moisture
6. discrete combined model
```

Each model must have independent unit tests.

---

## Phase 2.6 — Supervisor

Implement:

```text
safety override
actuator bounds
rate bounds
dwell logic placeholders
night/day screen-role mapping
```

---

## Phase 2.7 — Baseline Rule Controller

Run all mock scenarios.

Verify qualitative behavior.

Generate a machine-readable result file:

```text
outputs/baseline_scenarios.json
```

---

## Phase 2.8 — MPC Objective and Constraints

Implement:

```text
temperature term
humidity/VPD band term
light term
heat-loss term
movement term
```

Expose each cost component separately in diagnostics.

---

## Phase 2.9 — Optimizer

Implement a first working solver.

Requirements:

```text
- accepts current measured state
- predicts future trajectory
- optimizes three control inputs
- returns first action + full predicted trajectory
- never bypasses supervisor
```

---

## Phase 2.10 — MPC Sanity Scenarios

Run same scenarios as the baseline controller.

Create:

```text
outputs/mpc_scenarios.json
outputs/baseline_vs_mpc.json
```

Compare:

```text
T trajectory
RH / VPD
radiation
DLI
heat-loss proxy
actuator movement
```

---

## Phase 2.11 — Documentation

Update:

```text
README.md
MODEL_ASSUMPTIONS.md
PARAMETER_REGISTRY.md
VALIDATION_PLAN.md
```

Every provisional parameter must state:

```text
source
reason
calibration requirement
```

---

# 33. Stop Conditions

STOP and report instead of guessing if any of these are required:

```text
exact screen transmittance
exact screen insulation coefficient
roof vent angle mapping
wind safety limit
rain safety rule
screen actuator speed
vent actuator speed
greenhouse U-value
exact infiltration rate
```

For prototype-only values, use explicit:

```yaml
status: temporary_test_fixture
verified: false
```

Do not silently invent field values.

---

# 34. Expected First Completion Report

At the end of this work, report:

```markdown
# MPC Standalone Prototype Result

## Created
- folder structure
- architecture
- models
- scheduler
- supervisor
- rule baseline
- MPC prototype
- tests

## Verified
- unit tests
- mock scenarios
- qualitative direction tests

## Provisional
- parameters still using literature/test values

## Blocked by field information
- list exact values needed

## Protected dashboard
- confirm no files outside mpc_lab were modified

## Recommended next step
- passive field-data model validation
```

---

# 35. Final Development Rules

1. **Do not touch the existing 3D dashboard.**
2. Work only inside the standalone MPC directory.
3. Preserve clear provenance for every parameter.
4. Keep crop references separate from greenhouse physics.
5. Keep physical models separate from control rules.
6. Keep supervisor separate from optimizer.
7. Keep diffuse and shade screens as separate actuators.
8. Treat the shade screen as the nighttime insulation screen.
9. Do not invent missing field values.
10. Build a working prototype with provisional values rather than waiting for perfect calibration.
11. All model components must be replaceable later.
12. The first target is simulation + recommendation, not autonomous control.
