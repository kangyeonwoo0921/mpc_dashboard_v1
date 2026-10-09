# Greenhouse MPC Design Baseline
## Cherry Tomato — Roof Vent + Screen Control

**Document role:** implementation baseline for Claude Code / Codex / human review  
**Project scope:** cherry tomato greenhouse, roof-vent + screen recommendation MPC, no autonomous PLC write  
**Primary cropping context:** mid/late-September transplant → autumn establishment/flowering → winter low-light production  
**Version:** Stage 1 + Stage 2 integrated baseline

---

# 0. How to Use This Document

This document is intentionally split into four layers that MUST remain separate in code:

```text
A. Crop / climate references
   → reference scheduler

B. Physics / prediction equations
   → greenhouse prediction model

C. Control logic / supervisory rules
   → safety + actuator admissibility + fallback controller

D. MPC optimization
   → future actuator trajectory
```

Do not merge them into a single rule engine.

```yaml
design_principles:
  literature_value_policy:
    start_from_literature: true
    field_calibration_expected: true
    perfect_verification_before_prototype: false

  control_scope:
    roof_vent: true
    screen: true
    heating: false
    fogging: false
    CO2_control: false
    direct_PLC_write: false

  runtime_mode:
    LIVE_REAL:
      meaning: actual sensor and actuator state
    VIRTUAL_MPC:
      meaning: simulation initialized from current real state

  reanchoring:
    every_control_cycle:
      reset_prediction_initial_state_from_measurement: true
```

---

# 1. Canonical Source Registry

Only the portions relevant to this project are adopted. A source is NOT accepted as a whole.

| ID | Source | Main role in this project | Adoption level |
|---|---|---|---|
| `SRC-1997-KR` | 1997 Korean greenhouse tomato automatic-control report | overall structure: weather → microclimate model → crop/environment target → controller | structure only |
| `SRC-VENT-DEJONG1990` | de Jong, *Natural Ventilation of Large Multi-Span Greenhouses* | wind + buoyancy ventilation structure; window geometry/opening/wind direction | physics structure |
| `SRC-VENT-REVIEW2022` | Agronomy 2022 greenhouse natural-ventilation review | comparison of ventilation equations and coefficients | equation selection reference |
| `SRC-KITTAS2008` | Kittas et al., 2008 | roof/side vent microclimate, screen resistance, spatial heterogeneity | interaction evidence |
| `SRC-FAO2013` | FAO greenhouse climate control & energy use | practical vent/shade/screen priority and timing | high-value control logic |
| `SRC-BAILEY1988` | Bailey, *Control Strategies to Enhance the Performance of Greenhouse Thermal Screens* | screen timing, energy vs light trade-off, heat-loss model | control + equation reference |
| `SRC-LIU2023` | Liu et al., *Two-Factor Thermal Screen Control Strategy* | solar + indoor/outdoor ΔT screen timing | logic only |
| `SRC-CAMPEN2009` | Campen et al., *Mechanically controlled moisture removal from greenhouses* | humidity control under thermal screen; screen-gap risk | high-value humidity logic |
| `SRC-JUNG2020` | Jung et al., multi-window ventilation predictive control | 0–100% vent control, prediction-driven control architecture | architecture reference |
| `SRC-SUXU2022` | Su & Xu, setpoint decision + hybrid control | layer separation; vent/shade/thermal-screen expert rules | architecture + logic |
| `SRC-HAHN2011` | Hahn, fuzzy shade-screen controller | persistence / anti-chattering / screen actuation timing | logic reference |
| `SRC-CHAVAN2025` | Chavan et al., shade-screen × ventilation combinations | coupled actuator outcome evidence | comparison/reference |
| `SRC-ZHANG2020-RAD` | Zhang et al., solar-radiation allocation model | direct/diffuse/internal radiation structure | radiation model reference |
| `SRC-MIGUEL-SCREEN` | Miguel screen-radiation studies | screen optical transmittance / screen crossing logic | optical reference |
| `SRC-HTFF-SCREEN` | thermal-screen heat-transfer paper | thermal insulation / convection / permeability | screen thermal reference |
| `SRC-CUPID` | cherry tomato 'Cupid' growth/environment study | crop-specific day/night temperature, RH, CO2, GDD | crop reference |
| `SRC-FIELD-AUG` | August cherry-tomato cultivation guide | transplant/establishment setpoints and shading logic | primary operational baseline |
| `SRC-FIELD-OCT` | October cherry-tomato cultivation guide | active growth / flowering / fruit-set setpoints | primary operational baseline |
| `SRC-FIELD-DEC` | December cherry-tomato cultivation guide | winter low-light / humidity / screen / vent scheduling | primary operational baseline |

### Explicitly excluded from the core baseline

```yaml
excluded_sources:
  Mahmood_2023_RMPC:
    status: excluded_by_project_decision
    reason: not suitable as core greenhouse/crop/control reference for current project
```

---

# 2. Terminology and Sign Conventions

## 2.1 Screen semantics

One convention MUST be selected and used everywhere.

Recommended:

```yaml
screen_semantics:
  screen_opening_percent:
    100: fully_retracted_open_to_light
    0: fully_deployed_closed
  deployment_fraction:
    formula: 1 - screen_opening_percent / 100
```

Do not mix `opening %` and `deployment %`.

## 2.2 Vent semantics

```yaml
roof_vent_opening_percent:
  min: 0
  max: 100
  meaning: controller opening command/state
  note: not equal to physical opening angle or ventilation rate
```

Required future mapping:

```text
vent %
→ opening angle
→ effective opening area
→ air exchange rate
```

## 2.3 Coordinate / weather conventions

```yaml
physics_coordinates:
  X: greenhouse_longitudinal
  Y: greenhouse_lateral
  Z: vertical_up

azimuth:
  zero_deg: true_north
  direction: clockwise
```

---

# 3. Initial MPC State / Input / Disturbance / Output Contract

This is the recommended Stage-2 starting point.

```yaml
state_x:
  Tin_C:
    role: dynamic_state
  Xi_in:
    role: dynamic_moisture_state
    preferred_over_RH_state: true

control_u:
  roof_vent_opening_percent:
    range: [0, 100]
  screen_opening_percent:
    range: [0, 100]

disturbance_d:
  Tout_C:
  Xi_out:
  solar_global_W_m2:
  wind_speed_m_s:
  wind_direction_deg:
  rain_state:
  time:
  sun_position:

output_y:
  Tin_C:
  RH_in_percent:
  VPD_kPa:
  effective_crop_radiation:
  DLI:
```

### Why `Xi` rather than RH as the moisture state

```text
sensor measurement → RH
dynamic moisture balance → Xi / absolute humidity / vapor concentration
crop/control evaluation → RH and VPD
```

This preserves a physically meaningful conserved moisture state while allowing RH/VPD to remain user-facing outputs.

---

# 4. Reference Scheduler — Crop and Seasonal Baseline

The scheduler is a separate module. It does NOT belong inside the MPC cost function code.

## 4.1 Baseline crop targets

```yaml
temperature:
  normal_mean_24h_C: [18, 20]
  october_pre_winter_mean_24h_C: [20, 21]
  winter_mean_24h_min_C: [17, 18]
  winter_minimum_C: [13, 14]

humidity:
  spring_reference_RH_percent:
    target: 65
    tolerance: 5
  winter_night_high_risk_RH_percent: 90

vpd:
  initial_working_band_kPa: [0.5, 1.2]
  initial_center_reference_kPa: 0.8
  status: literature_baseline_not_universal_optimum

light:
  field_guide_instantaneous_reference_W_m2: [600, 700]
  general_tomato_DLI_reference_mol_m2_d: [20, 30]
  cherry_tomato_natural_light_example_mol_m2_d: 14.5
```

## 4.2 Growth stages

```yaml
growth_stages:

  establishment_vegetative:
    priorities:
      - temperature_stability
      - gradual_light_acclimation
      - avoid_excessive_post_establishment_shading

  flowering_fruit_set:
    priorities:
      - preserve_useful_light
      - stable_temperature
      - humidity_control
      - transpiration_support

  fruit_development_harvest:
    priorities:
      - preserve_light
      - stabilize_temperature
      - prevent_condensation
      - humidity_control
```

## 4.3 August operational baseline

```yaml
august:
  biological_context:
    - transplant
    - establishment
    - early_vegetative

  temperature:
    mean_24h_C: [18, 20]

  light:
    preferred_instantaneous_W_m2: [600, 700]
    establishment:
      high_light_not_required: true
    after_establishment:
      gradually_reduce_shading_every_days: [4, 5]

  leaf_air_temperature_difference:
    shading_reference_C: 4
    severe_transpiration_warning_C: 6

  night_thermal_screen:
    reference_closure_percent: 80

  humidity_rain:
    roof_vent_reference_max_percent: 5
    status: field_guide_rule_not_hardware_safety_limit
```

## 4.4 October operational baseline

```yaml
october:
  biological_context:
    - active_growth
    - flowering
    - fruit_set
    - early_fruit_enlargement

  truss_development_days: [7, 9]

  temperature:
    normal_mean_24h_C: [18, 20]
    pre_winter_acceleration_mean_24h_C: [20, 21]

  light:
    observed_mean_W_m2: 645
    observed_max_W_m2: 890
    preferred_W_m2: [600, 700]
    policy: maximize_useful_light_after_acclimation

  screen:
    daytime_unnecessary_shading_penalty: high
    night_thermal_screen_closure_reference_percent: 80
```

## 4.5 December operational baseline

```yaml
december:
  biological_context:
    - winter_low_light
    - slower_development
    - increasing_condensation_risk

  truss_development_days: [12, 14]

  temperature:
    minimum_C: [13, 14]
    mean_24h_min_C: [17, 18]

  vent_temperature_schedule_C:
    morning: 19
    afternoon: [26, 27]
    early_evening: 16.5
    night: 16

  solar_temperature_modifiers:
    morning_max_add_C: 1
    afternoon_max_add_C: 2
    night_accumulated_light_max_add_C: 2

  humidity:
    RH_high_risk_percent: 90
    daytime_absolute_humidity_low_g_per_kg: 8
    morning_humidity_relief_temperature_C: 18

  screen:
    thermal:
      start: sunset_minus_1h
      end: sunrise_plus_0_5h
    diffuse:
      start: sunset_minus_2h
      end: sunrise_plus_2h
      outside_temperature_use_below_C: 15
```

## 4.6 Scheduler output interface

```yaml
ReferenceSchedule:
  timestamp:
  growth_stage:
  season_mode:

  T_ref_C:
  T_soft_min_C:
  T_soft_max_C:

  VPD_ref_kPa:
  VPD_soft_min_kPa:
  VPD_soft_max_kPa:

  instantaneous_light_ref_W_m2:
  DLI_target_mol_m2_d:

  condensation_risk_level:
  light_preservation_priority:
  vent_heat_loss_penalty_multiplier:
  screen_shading_penalty_multiplier:
```

---

# 5. Supervisory Control Logic — Minimum Mandatory Baseline

The supervisory layer sits above the optimizer.

```text
SAFETY
  ↓
crop temperature protection
  ↓
humidity / condensation protection
  ↓
useful-light preservation
  ↓
heat-loss minimization
  ↓
actuator movement minimization
```

## 5.1 Vent logic

```yaml
VENT_M1_temperature:
  if:
    - Tin > T_ref
  consider:
    - Tout
    - wind_speed
    - wind_direction
    - solar
  action:
    - increase_vent_opening

VENT_M2_humidity:
  if:
    - RH_high
    - VPD_low
    - condensation_risk
  action:
    - permit_minimum_or_limited_ventilation
  cost:
    - winter_heat_loss

VENT_M3_safety:
  if:
    - rain
    - excessive_wind
    - actuator_fault
    - communication_fault
  action:
    - apply_field_override
```

## 5.2 Shade-screen logic

```yaml
SHADE_M1_light_preservation:
  if:
    - low_current_light
    - low_predicted_DLI
  action:
    - keep_screen_retracted_if_thermally_safe

SHADE_M2_assist_cooling:
  if:
    - high_solar
    - Tin_rising
    - vent_prediction_insufficient
  action:
    - deploy_progressively
```

Preferred cool-season sequence:

```text
ventilation first
→ predict response
→ shading only if needed
```

## 5.3 Thermal-screen logic

```yaml
THERMAL_M1_night_insulation:
  condition:
    - useful_solar_gain_low
    - outside_temperature_low
  action:
    - deploy_for_heat_retention

THERMAL_M2_morning_open:
  condition:
    - useful_solar_gain_available
    - heat_balance_improving
  action:
    - progressively_retract

THERMAL_M3_humidity_relief:
  condition:
    - screen_deployed
    - excessive_humidity
  first_action:
    - controlled_small_screen_crack
  fallback:
    - limited_ventilation
```

Important: `screen first` is a humidity-control reference, NOT a universal unconditional rule.

---

# 6. Day-Phase State Machine

```yaml
states:

  NIGHT_INSULATION:
    screen: mostly_deployed
    vent: minimal
    monitor:
      - Tin
      - RH
      - VPD

  DAWN_HUMIDITY_RELIEF:
    entry:
      - screen_deployed
      - humidity_risk_high
    actions:
      - controlled_screen_crack
      - limited_vent_if_needed

  MORNING_SOLAR_GAIN:
    actions:
      - progressively_retract_thermal_screen
      - preserve_solar_gain
      - delay_large_ventilation_until_needed

  DAY_VENTILATION:
    primary_cooling: roof_vent
    shading: secondary

  DAY_SHADE_ASSIST:
    entry:
      - vent_insufficient
      - radiation_high
    actions:
      - progressive_shading

  EVENING_TRANSITION:
    actions:
      - reduce_ventilation
      - evaluate_screen_closure
      - monitor_humidity_rise

  SAFETY_OVERRIDE:
    priority: highest
```

The state machine limits admissible MPC actions. It does not replace MPC.

---

# 7. Greenhouse Prediction Model — Recommended V1

V1 should be physically interpretable and replaceable.

## 7.1 Temperature state

Recommended project equation:

```math
C_eff * dTin/dt
=
Q_solar
- Q_cover
- Q_vent
+ Q_screen_thermal
- Q_crop_latent_effect
+ Q_other
```

Initial implementation may simplify to:

```math
C_eff * dTin/dt
=
Q_solar
- U_eff * A_cover * (Tin - Tout)
- rho_air * cp * Vdot * (Tin - Tout)
```

where screen effects modify both `Q_solar`, `U_eff`, and optionally `Vdot`.

## 7.2 Moisture state

Recommended project structure:

```math
dM_v/dt
=
E_crop
- Mdot_vent
- Mdot_condensation
```

or using humidity ratio:

```math
rho_air * V_greenhouse * dXi_in/dt
=
E_crop
- rho_air * Vdot * (Xi_in - Xi_out)
- Mdot_cond
```

V1 can initially omit detailed condensation if data are unavailable, but the omission must be explicit.

---

# 8. Natural Ventilation Model Registry

## 8.1 Physical variables required

```yaml
natural_ventilation_inputs:
  - vent_opening_percent
  - effective_opening_area
  - vent_opening_angle
  - wind_speed
  - wind_direction
  - Tin
  - Tout
  - discharge_coefficient
```

## 8.2 Project model structure

Use a wind + buoyancy formulation:

```text
Vdot = combine(
  wind_driven_flow,
  buoyancy_driven_flow
)
```

A common practical structure is:

```math
Vdot = Cd * A_eff * sqrt(
  Cw * wind_speed^2
  + buoyancy_term(DeltaT, geometry)
)
```

This is a **project-level generalized form**, not a verbatim equation from one paper.

## 8.3 de Jong transferables

Use:
- windward / leeward distinction,
- wind direction,
- window count,
- window size,
- opening angle,
- separate wind and buoyancy contributions before combination.

Do not copy coefficients without matching geometry.

## 8.4 Kittas 2008 transferables

```yaml
Kittas_2008:
  insect_screen_effect:
    normalized_air_velocity_reduction_percent: 58
    context: side_vent_insect_screens
    use: evidence_of_flow_resistance_not_direct_coefficient

  vent_configuration:
    roof_only:
      climate_uniformity: highest_among_tested_cases
    roof_plus_side:
      air_velocity: higher
      temperature: lower
      spatial_heterogeneity: higher
```

The target project is roof-vent dominant, so roof-only evidence is structurally relevant, but not directly parameter-transferable.

## 8.5 FAO simplified ventilation sanity check

Original reference form:

```math
Va = 0.0003 * tau * Rs,o,max / DeltaT
```

Use only for:
- order-of-magnitude ventilation demand check,
- comparison against simulation outputs.

Do not use as the final natural-ventilation actuator model.

---

# 9. Screen Model Registry

Three effects must be modeled separately.

```yaml
screen_effects:
  optical:
    affects: Q_solar
  thermal:
    affects: cover_heat_loss
  aerodynamic:
    affects: internal_air_exchange_and_vent_effectiveness
```

## 9.1 Optical model

Initial surrogate:

```math
I_eff = I_out * tau_cover * tau_screen(u_screen)
```

Ray-integrated version:

```math
I_eff
=
DNI * F_dir(sun_position, screen_state, geometry)
+
DHI * F_diff(screen_state, geometry)
```

## 9.2 Thermal model — Bailey reference

Original Bailey relation:

```math
U = alpha + beta * w
```

Screened approximation:

```math
U_screened = (1 - delta) * U
```

where `delta` is the fractional heat-loss reduction by the screen.

Project use:
- equation structure: YES
- Bailey numeric coefficients: NO
- field/manufacturer calibration: REQUIRED

## 9.3 Screen heat-loss ranges retained for sensitivity testing

From Bailey's context:

```yaml
thermal_screen_heat_loss_reduction:
  transparent_screen_percent: about_38
  aluminized_high_performance_percent: about_60
  status: sensitivity_reference_only
```

## 9.4 Aerodynamic interaction

Internal screen deployment can reduce air movement and roof-vent performance.

Recommended coupling:

```math
Vdot_eff = Vdot_vent * f_screen_airflow(u_screen)
```

where:

```yaml
f_screen_airflow:
  range: [0, 1]
  initial_status: provisional
  calibration_required: true
```

Do not set `f_screen_airflow = 1` permanently.

---

# 10. Screen Timing and Humidity Logic Registry

## 10.1 FAO timing logic

High-value logic:

```text
cold/low-light conditions:
delay ventilation or screen opening to preserve solar gain
```

Humidity control with thermal screen:

```text
open screen before opening ventilators
```

Morning energy reference:

```yaml
delayed_screen_opening_radiation_reference_W_m2:
  lower: 50
  upper: 150
  status: design_reference_not_hard_threshold
```

## 10.2 Liu 2023 logic

Core transferable condition:

```text
open thermal screen when solar/roof energy gain can compensate heat loss
```

Project abstraction:

```text
thermal_screen_command
=
f(
  solar_radiation,
  Tin - Tout,
  time_of_day,
  predicted_heat_balance
)
```

Do not reuse:
- Chinese solar greenhouse wall-storage assumptions,
- fitted empirical polynomial,
- their exact geometry.

## 10.3 Campen 2009 humidity caution

Conventional practice:

```text
high RH below thermal screen
→ slightly open screen
```

But:

```yaml
Campen_screen_gap_case:
  screen_opening_percent: about_2.5
  CFD_temperature_difference_K: almost_10
  observed_problem:
    - cold_downdraft
    - horizontal_temperature_gradient
    - local_RH_can_increase
```

Therefore:

```text
small screen crack = controlled fallback
NOT default unrestricted humidity solution
```

## 10.4 Hahn 2011 anti-chatter logic

Hahn used persistence-related timing around 15 min.

Project abstraction:

```yaml
anti_chatter:
  minimum_dwell_time_s: configurable
  persistence_time_s: configurable
  contradictory_signal_filter: true
```

Do not hard-code 15 min until actuator and field response are observed.

---

# 11. Prediction-Based Vent Control Reference — Jung 2020

Jung et al. is NOT adopted as the final MPC model.

Transferable architecture:

```text
weather + current greenhouse state + actuator history
→ predict Tin at future time
→ optimize window opening %
→ minimize predicted target error
```

Relevant source characteristics:

```yaml
Jung_2020:
  actuator:
    windows:
      range_percent: [0, 100]
  prediction:
    future_Tin_minutes: 30
  objective:
    temperature_prediction_error_MSE: true
  conventional_baseline:
    controller: P_band
    modifiers:
      - external_temperature
      - wind_direction
      - wind_speed
      - solar_radiation
```

Project interpretation:

```math
J_T = sum (T_pred - T_ref)^2
```

Do NOT automatically adopt 30 min as our prediction horizon.

---

# 12. Su & Xu Hybrid-Control Logic Reference

Useful architectural concept:

```text
setpoint optimization
+
expert-rule actuator logic for slow mechanical devices
+
adaptive controller for fast continuous actuators
```

Relevant to this project because vent windows and screens:
- cannot change arbitrarily fast,
- should not chatter,
- require actuator protection.

Their reported expert logic includes:
- roof vent based on temperature/humidity/wind,
- shading based on solar radiation + temperature + wind,
- thermal screen based on outside temperature + solar/no-solar condition.

Project transfer:

```yaml
slow_actuator_constraints:
  include:
    - rate_limit
    - minimum_dwell
    - movement_penalty
    - safety_override
```

Do not copy their threshold values directly.

---

# 13. Coupled Vent + Screen Control

The actuators interact physically and economically.

## 13.1 Daytime cooling trade-off

```text
roof vent:
  + removes sensible heat
  + removes moisture
  - loses heat when outside is cold
  - depends on wind

shade screen:
  + reduces solar gain
  - reduces useful crop light
  - can reduce internal airflow / vent effectiveness
```

## 13.2 Cool-season default preference

```text
if useful light is valuable:
  vent first
  then shade if ventilation prediction is insufficient
```

This preference can be overridden by:
- excessive radiation,
- very high Tin,
- insufficient vent authority,
- wind/rain safety restriction.

## 13.3 Chavan combination study

Retain as comparison evidence:

```yaml
tested_state_combinations:
  - screen_open_vent_open
  - screen_open_vent_closed
  - screen_closed_vent_closed
  - screen_closed_vent_open
```

Use:
- evidence that coupled state matters,
- not as a direct controller or threshold source.

---

# 14. Radiation Model Interface

The ray/radiation model must be replaceable without changing MPC.

## 14.1 V1 interface

```yaml
RadiationModelInput:
  timestamp:
  sun_position:
  GHI:
  DNI:
  DHI:
  screen_state:
  geometry_state:

RadiationModelOutput:
  crop_effective_radiation:
  direct_component:
  diffuse_component:
  spatial_optional:
```

## 14.2 Core model

```math
I_dir,j
=
DNI * max(0, n_crop,j dot s) * tau_cover * T_screen,j * S_j
```

```math
I_diff,j
=
DHI * tau_cover,diff * T_screen,diff,j * F_sky,j
```

```math
I_eff
=
sum(I_j * A_j) / sum(A_j)
```

## 14.3 Runtime strategy

Avoid full ray tracing inside every optimizer iteration.

Preferred:

```text
offline / periodic ray tracing
→ lookup table / surrogate
→ MPC runtime
```

Example:

```math
I_crop
=
DNI * F_dir(solar_altitude, solar_azimuth, screen)
+
DHI * F_diff(screen)
```

---

# 15. MPC Objective — Initial Design

Recommended conceptual objective:

```math
J =
J_temperature
+ J_humidity
+ J_light
+ J_heat_loss
+ J_actuator
```

Expanded:

```math
J =
wT * sum(T_pred - T_ref)^2
+ wH * humidity_penalty
+ wL * light_penalty
+ wQ * heat_loss_penalty
+ wV * sum(delta_u_vent)^2
+ wS * sum(delta_u_screen)^2
```

## 15.1 Temperature term

```math
J_T = wT * sum(T_k - T_ref,k)^2
```

## 15.2 VPD / humidity term

Prefer band penalty rather than rigid single-point tracking.

```text
within VPD band → near-zero penalty
outside band → increasing penalty
```

## 15.3 Light term

Separate two time scales:

```text
instantaneous excessive radiation
vs
daily accumulated DLI deficit
```

Potential daily deficit term:

```math
J_DLI = w_DLI * max(0, DLI_target - DLI_predicted)^2
```

## 15.4 Heat-loss term

For winter venting:

```text
venting benefit for humidity/cooling
minus
thermal loss cost
```

Approximate proxy:

```math
Q_vent = rho_air * cp * Vdot * (Tin - Tout)
```

## 15.5 Movement term

```math
J_move =
wV * sum(delta_vent)^2
+
wS * sum(delta_screen)^2
```

This reduces chatter and actuator wear.

---

# 16. Constraints

## 16.1 Input bounds

```yaml
roof_vent_opening_percent: [0, 100]
screen_opening_percent: [0, 100]
```

## 16.2 Input-rate bounds

Keep configurable:

```yaml
delta_vent_max_per_step: null
delta_screen_max_per_step: null
status: field_required
```

## 16.3 Environmental soft constraints

```yaml
temperature:
  winter_min_C: 14
  winter_mean_24h_min_C: 18

vpd:
  soft_band_kPa: [0.5, 1.2]

humidity:
  night_RH_high_risk_percent: 90
```

## 16.4 Hard safety constraints

```yaml
hard_safety:
  rain:
    rule: target_site_controller_required
  wind:
    max_safe_speed: null
  communication_fault:
    fallback: existing_farm_rule_or_safe_state
  actuator_fault:
    fallback: safe_state
```

Field-guide `vent <= 5% under rain` is retained as a baseline/reference only, not a certified structural limit.

---

# 17. Sampling Time and Horizons

Do not copy values from one paper.

Recommended design method:

```text
choose sampling time from:
- sensor update rate
- actuator movement speed
- greenhouse thermal time constant
- desired recommendation refresh rate
```

Initial engineering candidates:

```yaml
sampling_time:
  candidate_minutes: [2, 5]
  status: to_be_tested

prediction_horizon:
  desired_physical_span_minutes: [30, 120]
  status: sensitivity_test

control_horizon:
  shorter_than_prediction_horizon: true
```

These are PROJECT DESIGN CANDIDATES, not literature claims.

---

# 18. Baseline Rule Controller for Validation

A rule controller is required even if MPC is the main research target.

```yaml
baseline_rule_controller:

  roof_vent:
    temperature:
      method: proportional_band
    humidity:
      allow_minimum_ventilation: true
    safety:
      use_field_override: true

  shade_screen:
    low_light:
      action: retract
    high_solar_and_vent_insufficient:
      action: deploy_progressively

  thermal_screen:
    night:
      action: deploy
    dawn:
      action: delayed_progressive_open
    high_humidity:
      action: controlled_small_crack_then_reassess
```

Comparison framework:

```text
actual farm rule
vs
literature baseline rule
vs
MPC recommendation
```

---

# 19. Parameter Registry Schema

Every parameter MUST have provenance.

```yaml
Parameter:
  id:
  value:
  units:

  source_type:
    - field_guide_baseline
    - cherry_tomato_study
    - general_tomato_literature
    - greenhouse_physics_literature
    - manufacturer_spec
    - measured
    - calibrated
    - temporary_test_fixture
    - unknown

  source_id:
  original_value:
  transformed_value:
  transformation_reason:

  confidence:
    - high
    - medium
    - low

  status:
    - literature_baseline
    - field_guide_baseline
    - provisional
    - calibrated
    - field_verified
    - unknown

  calibration_required:
  notes:
```

---

# 20. Equation Registry Schema

Never mix an original source equation with the project-modified equation.

```yaml
EquationRecord:

  id: VENT_001
  category: natural_ventilation

  source:
    source_id:
    equation_number:
    context:

  original_equation:
  original_variables:

  assumptions:
  transferable_parts:
  non_transferable_parts:

  project_equation:
  modification_reason:

  parameter_sources:
  validation_plan:

  status:
    - candidate
    - adopted
    - modified
    - rejected
```

Suggested IDs:

```yaml
equation_ids:
  TEMP_001: greenhouse_air_energy_balance
  HUM_001: greenhouse_moisture_balance
  VENT_001: natural_ventilation_combined_wind_buoyancy
  VENT_002: FAO_ventilation_sanity_check
  SCREEN_001: Bailey_wind_dependent_U
  SCREEN_002: screen_heat_loss_reduction
  SCREEN_003: screen_airflow_modifier
  RAD_001: direct_radiation
  RAD_002: diffuse_radiation
  RAD_003: crop_effective_radiation
```

---

# 21. Parameter Calibration Strategy

## 21.1 Calibrate in this order

```text
1. vent effectiveness
2. screen radiation effect
3. effective greenhouse thermal capacity
4. cover heat-loss coefficient
5. humidity / transpiration terms
```

Do not calibrate every parameter simultaneously.

## 21.2 Vent calibration

Use clean actuator transitions where possible.

```yaml
inputs:
  - Tin
  - Tout
  - vent_percent
  - wind_speed
  - wind_direction
  - solar

estimate:
  - response_delay
  - effective_ventilation_gain
  - nonlinear_opening_response
```

Important:

```text
50% vent opening != 50% ventilation rate
```

## 21.3 Screen calibration

Preferred measurements:

```yaml
inputs:
  - outside_radiation
  - inside_radiation_or_PAR_if_available
  - screen_position
  - solar_altitude
  - solar_azimuth
```

Estimate:

```yaml
outputs:
  - effective_transmission_vs_screen_position
  - deployment_delay
  - partial_deployment_nonlinearity
```

---

# 22. Validation Strategy

## 22.1 Validation levels

```yaml
Level_0:
  name: offline_sanity
  data: mock_or_public
  purpose: direction_and_stability

Level_1:
  name: passive_live_validation
  data: actual_field_sensor_data
  controller: existing_farm_control
  purpose: prediction_model_validation

Level_2:
  name: shadow_mode
  action: MPC_recommendation_not_applied
  purpose: compare_recommendation_with_existing_rule

Level_3:
  name: supervised_field_trial
  action: human_approved
  optional: true

Level_4:
  name: autonomous_control
  current_scope: false
```

## 22.2 Store this validation record

```yaml
ValidationRecord:

  timestamp:

  measured_now:
    Tin:
    RH:
    Tout:
    solar:
    wind_speed:
    wind_direction:

  actual_control:
    vent_percent:
    screen_percent:

  MPC_recommendation:
    vent_percent:
    screen_percent:

  predicted_future:
    Tin:
    RH:
    VPD:
    Ieff:

  measured_future:
    Tin:
    RH:
```

## 22.3 Metrics

```yaml
temperature:
  - RMSE
  - MAE
  - bias
  - peak_error
  - response_delay_error

humidity:
  - RMSE
  - MAE
  - bias

radiation:
  - RMSE
  - relative_error

control:
  - movement_count
  - total_variation
  - time_outside_target_band
```

---

# 23. Runtime Data Contract

```yaml
MPCInput:
  timestamp:
  crop_stage:
  season_mode:

  measured:
    Tin_C:
    RH_in_percent:
    Tout_C:
    RH_out_percent:
    solar_global_W_m2:
    wind_speed_m_s:
    wind_direction_deg:
    rain_state:
    roof_vent_opening_percent:
    screen_opening_percent:

  derived:
    Xi_in:
    Xi_out:
    VPD_kPa:
    sun_altitude_deg:
    sun_azimuth_deg:
    accumulated_DLI:

  forecast:
    Tout_C: []
    solar_W_m2: []
    wind_speed_m_s: []
    wind_direction_deg: []

  references:
    T_ref_C: []
    VPD_band_kPa: []
    DLI_target:
```

Output:

```yaml
MPCOutput:
  recommendation:
    roof_vent_opening_percent:
    screen_opening_percent:

  trajectory:
    vent_percent: []
    screen_percent: []

  predicted:
    Tin_C: []
    RH_percent: []
    VPD_kPa: []
    effective_radiation: []

  diagnostics:
    objective_total:
    objective_temperature:
    objective_humidity:
    objective_light:
    objective_heat_loss:
    objective_movement:

  active_constraints: []
  source_status:
  confidence:
```

---

# 24. Recommended Software Module Layout

```text
greenhouse_mpc/
│
├── config/
│   ├── crop_reference.yaml
│   ├── actuator_limits.yaml
│   ├── physics_parameters.yaml
│   └── source_registry.yaml
│
├── models/
│   ├── thermal.py
│   ├── moisture.py
│   ├── ventilation.py
│   ├── screen.py
│   └── radiation.py
│
├── control/
│   ├── reference_scheduler.py
│   ├── supervisor.py
│   ├── baseline_rules.py
│   ├── constraints.py
│   ├── objective.py
│   └── mpc.py
│
├── estimation/
│   ├── psychrometrics.py
│   ├── state_estimator.py
│   └── calibration.py
│
├── data/
│   ├── adapters.py
│   ├── live_snapshot.py
│   └── forecast.py
│
├── validation/
│   ├── metrics.py
│   ├── shadow_mode.py
│   └── reports.py
│
└── tests/
    ├── test_reference_scheduler.py
    ├── test_ventilation.py
    ├── test_screen_logic.py
    ├── test_constraints.py
    └── test_mpc_sanity.py
```

---

# 25. Minimum Acceptance Tests

## 25.1 Physical direction tests

```yaml
tests:

  hotter_inside_same_weather:
    expect:
      vent_recommendation_not_decrease: true

  higher_wind_same_vent:
    expect:
      predicted_ventilation_effect_changes: true

  lower_outdoor_temperature_winter:
    expect:
      vent_heat_loss_penalty_increases: true

  screen_more_deployed:
    expect:
      transmitted_radiation_decreases: true
      thermal_loss_not_increase_without_reason: true

  low_DLI_winter:
    expect:
      unnecessary_shading_penalty_increases: true

  RH_risk_high:
    expect:
      humidity_relief_action_enabled: true
```

## 25.2 Control consistency tests

```yaml
rain_override:
  expect:
    MPC_cannot_command_unsafe_vent_opening: true

anti_chatter:
  expect:
    rapid_screen_flip_flop_reduced: true

state_reanchoring:
  expect:
    every_cycle_starts_from_latest_measurement: true
```

---

# 26. Unknowns — Must Remain Explicit

```yaml
unknowns:

  crop:
    - exact_target_farm_cultivar
    - exact_current_growth_stage

  roof_vent:
    - percent_to_angle
    - percent_to_effective_area
    - actuator_speed
    - safe_wind_limit
    - rain_override_exact_rule

  screen:
    - exact_screen_type
    - optical_transmittance
    - thermal_property
    - airflow_resistance
    - actuator_speed
    - opening_percent_semantics_field_confirmation

  greenhouse:
    - cover_U_value
    - effective_thermal_capacity
    - infiltration_rate

  sensors:
    - exact_radiation_sensor_type
    - measurement_location
    - inside_PAR_or_radiation_availability
```

Unknown MUST NOT be silently replaced by zero.

---

# 27. Do-Not-Hardcode List

```yaml
do_not_hardcode:

  - VPD_0_8_as_universal_optimum
  - DLI_20_30_as_universal_cherry_tomato_optimum
  - field_guide_1600J_without_unit_verification

  - FAO_screen_opening_50_150_W_m2_as_fixed_threshold
  - Campen_2_5_percent_screen_gap
  - Hahn_15_min_persistence
  - Jung_30_min_prediction_horizon
  - Bailey_alpha_beta_coefficients
  - Liu_empirical_formula

  - rain_5_percent_as_structural_safety_limit
  - generic_max_wind_limit
```

---

# 28. Current Baseline Decisions

```yaml
decisions:

  state:
    temperature: Tin
    moisture: Xi
    output_RH: calculated
    output_VPD: calculated

  actuator:
    roof_vent: continuous_percent
    screen: continuous_percent_if_hardware_allows

  cooling_priority_cool_season:
    first: roof_vent
    second: shade_screen

  thermal_screen:
    night_heat_retention: enabled
    morning_delayed_opening: enabled
    humidity_small_crack: allowed_with_constraints

  radiation:
    runtime_full_ray: not_required
    surrogate_interface: required

  mpc:
    direct_PLC_write: false
    shadow_mode_first: true
```

---

# 29. Implementation Order

```text
STEP 1
Implement data classes + configuration schema

STEP 2
Implement psychrometrics:
RH ↔ Xi ↔ VPD

STEP 3
Implement reference scheduler
(Aug / Oct / Dec + growth stage)

STEP 4
Implement simple thermal model

STEP 5
Implement provisional natural-ventilation model

STEP 6
Implement provisional screen optical + thermal model

STEP 7
Implement baseline supervisory rules

STEP 8
Implement baseline rule controller

STEP 9
Implement MPC objective + constraints

STEP 10
Run offline sanity tests

STEP 11
Connect live read-only data

STEP 12
Passive model validation

STEP 13
Calibrate vent / screen / thermal parameters

STEP 14
Shadow-mode MPC

STEP 15
Compare actual farm rule vs baseline vs MPC
```

---

# 30. Final Architecture

```text
Growlink / PLC read-only data
          │
          ▼
   State preprocessing
  RH → Xi, VPD, DLI
          │
          ├──────────────┐
          ▼              ▼
Reference Scheduler   Weather Forecast
(crop/season/time)        │
          │              │
          └──────┬───────┘
                 ▼
       Prediction Model
 thermal + moisture + vent
       + screen + radiation
                 │
                 ▼
        MPC Optimizer
                 │
                 ▼
      Supervisory Filter
 safety / dwell / overrides
                 │
                 ▼
       Recommendation
  vent % / screen % trajectory
                 │
                 ▼
        Dashboard only
```

---

# 31. Research Interpretation

The research question is not:

> "Can a literature threshold control the greenhouse?"

The intended question is:

> "Can a physics-informed, crop-reference-driven predictive controller generate more rational roof-vent and screen recommendations than the existing rule-based operation, while preserving light, temperature, humidity, and winter energy trade-offs?"

The project therefore uses:

```text
literature
→ initial structure and parameters

field guide
→ practical crop setpoint baseline

field measurements
→ parameter calibration

existing farm rule
→ operational comparison baseline

MPC
→ optimized future recommendation
```

---

# Appendix A — Detailed Stage-1 Climate Reference

The following embedded section preserves the previous detailed crop/climate reference as supporting material.


# Cherry Tomato Greenhouse Climate Reference — MPC Stage 1 Specification

> 목적: Claude Code / Codex가 방울토마토 재배환경 기준을 구조적으로 해석하여 이후 MPC skeleton 설계에 사용할 수 있도록 정리한 기준 문서.
>
> 연구 범위: **Cherry tomato + Roof Vent + Shade/Thermal Screen + MPC**
>
> 대상 작기 맥락: **9월 중순~말 정식 → 가을 생육 → 겨울 저온·약광기 재배**
>
> 중요:
> - 아래 값은 모두 동일한 근거 수준이 아니다.
> - `FIELD_GUIDE`, `CHERRY_TOMATO_STUDY`, `GENERAL_TOMATO_LITERATURE`를 반드시 구분한다.
> - 논문/가이드가 직접 지지하지 않는 값을 자동으로 “최적값”으로 간주하지 않는다.
> - 아직 미확정인 값은 `candidate`, `working_range`, `needs_validation`으로 취급한다.

---

# 1. Source Classes

```yaml
source_classes:
  CHERRY_TOMATO_STUDY:
    meaning: 방울토마토를 직접 대상으로 한 학술 연구
    priority: high
  FIELD_GUIDE:
    meaning: 스마트팜 방울토마토 현장 재배 가이드
    priority: high_for_operation
  GENERAL_TOMATO_LITERATURE:
    meaning: 일반 토마토 온실 문헌
    priority: supporting
  PROJECT_ASSUMPTION:
    meaning: 프로젝트 구현을 위한 임시 가정
    priority: temporary_only
```

---

# 2. Final Reference Table

| Category | Variable | Current Reference | Status | Source Type | Use in MPC |
|---|---|---:|---|---|---|
| Crop | Crop type | Cherry tomato / 대추방울토마토 | Confirmed | CHERRY_TOMATO_STUDY + FIELD_GUIDE | crop profile |
| Crop | Example cultivar | `Cupid` | Reference only | CHERRY_TOMATO_STUDY | cultivar metadata |
| Temperature | 24 h mean temperature | **18–20°C** | Strong operational reference | FIELD_GUIDE | reference band |
| Temperature | October accelerated-growth 24 h mean | **20–21°C** | Seasonal operational recommendation | FIELD_GUIDE | seasonal scheduler |
| Temperature | Spring study day setpoint | **22 ± 2°C** | Experimental management condition, not universal optimum | CHERRY_TOMATO_STUDY | supporting reference |
| Temperature | Spring study night setpoint | **16 ± 2°C** | Experimental management condition, not universal optimum | CHERRY_TOMATO_STUDY | supporting reference |
| Temperature | Winter minimum temperature | **13–14°C minimum** | Strong winter operational floor | FIELD_GUIDE | lower safety/reference bound |
| Temperature | Winter 24 h mean | **≥17–18°C** | Strong winter operational reference | FIELD_GUIDE | winter reference |
| Temperature | Winter vent-temperature schedule | morning 19°C / afternoon 26–27°C / early evening 16.5°C / night 16°C | Operational rule | FIELD_GUIDE | baseline scheduler |
| Temperature | Winter heating schedule | day 16°C / night 14°C | Operational rule | FIELD_GUIDE | baseline only; heating outside current control scope |
| Humidity | Spring study RH setpoint | **65 ± 5%** | Experimental management condition | CHERRY_TOMATO_STUDY | supporting reference |
| Humidity | Winter night RH risk | **>90% RH** | Strong operational risk threshold | FIELD_GUIDE | humidity/condensation constraint |
| Humidity | Day absolute humidity lower bound | **8 g/kg** | Operational control threshold | FIELD_GUIDE | ventilation/screen constraint |
| VPD | Working range | **0.5–1.2 kPa** | Candidate working range | GENERAL_TOMATO_LITERATURE | soft constraint / target band |
| VPD | Representative center target | **~0.8 kPa** | Candidate only | GENERAL_TOMATO_LITERATURE | optional reference |
| Light | Instantaneous radiation target | **600–700 W/m²** | Strong field-guide reference | FIELD_GUIDE | screen control reference |
| Light | October actual average instantaneous radiation | **645 W/m²** | Observed context | FIELD_GUIDE | context only |
| Light | October maximum instantaneous radiation | **890 W/m²** | Observed context | FIELD_GUIDE | context only |
| Light | Winter instantaneous radiation observed range | **380–650 W/m²** | Observed winter context | FIELD_GUIDE | context only |
| Light | Cumulative light reference in guide | **1600 J** | Unit definition unclear | FIELD_GUIDE | DO NOT USE numerically until unit verified |
| DLI | Tomato high-production reference | **20–30 mol·m⁻²·d⁻¹** | General tomato literature candidate | GENERAL_TOMATO_LITERATURE | daily-light objective candidate |
| DLI | Cherry tomato natural-light example | **~14.5 mol·m⁻²·d⁻¹** | Experimental context, not optimum | CHERRY_TOMATO_STUDY | supporting context |
| CO2 | Spring study setpoint | **800 ± 50 ppm** | Experimental management condition | CHERRY_TOMATO_STUDY | monitoring only, out of control scope |
| Screen | August/October night thermal screen | **~80% closed when needed** | Operational recommendation | FIELD_GUIDE | baseline screen rule |
| Screen | Winter aluminum screen timing | sunset -1 h → sunrise +0.5 h | Operational rule | FIELD_GUIDE | baseline timing |
| Screen | Winter diffusive screen timing | sunset -2 h → sunrise +2 h | Operational rule | FIELD_GUIDE | baseline timing |
| Screen | Diffusive screen external-temp condition | **Tout < 15°C** | Operational rule | FIELD_GUIDE | baseline rule |
| Vent | Rain-condition roof vent opening | **≤5%** | Operational safety reference | FIELD_GUIDE | hard/override candidate |
| Vent | Winter morning humidity ventilation | start ventilation when greenhouse T ≥18°C even under low-light/cloudy conditions | Operational rule | FIELD_GUIDE | baseline humidity logic |
| Growth | High-temperature truss development rate | **5–7 d/truss** | Seasonal growth indicator | FIELD_GUIDE | monitoring only |
| Growth | October truss development rate | **7–9 d/truss** | Seasonal growth indicator | FIELD_GUIDE | growth-stage context |
| Growth | Winter low-light truss development rate | **12–14 d/truss** | Seasonal growth indicator | FIELD_GUIDE | growth-stage context |

---

# 3. Recommended MPC Climate Targets — Current Working Version

```yaml
temperature:
  mean_24h_target_C:
    lower: 18
    upper: 20
    status: working_reference
  october:
    mean_24h_target_C:
      lower: 20
      upper: 21
    purpose: accelerate_growth_before_winter
  winter:
    minimum_temperature_C:
      lower_candidate: 13
      preferred_lower_bound: 14
    mean_24h_temperature_C:
      minimum_candidate: 17
      preferred_minimum: 18

humidity:
  spring_reference_RH_percent:
    target: 65
    tolerance: 5
  winter_night_high_risk_RH_percent:
    threshold: 90

absolute_humidity:
  daytime_min_g_per_kg: 8

vpd:
  working_range_kPa:
    lower: 0.5
    upper: 1.2
  representative_reference_kPa: 0.8
  status: candidate

instantaneous_radiation:
  preferred_range_W_m2:
    lower: 600
    upper: 700

dli:
  general_tomato_high_production_reference_mol_m2_d:
    lower: 20
    upper: 30
  cherry_tomato_natural_light_example_mol_m2_d:
    value: 14.5
    interpretation: experimental_context_not_optimum
```

---

# 4. Seasonal Light Logic

```yaml
seasonal_light_logic:
  august:
    stage: transplant_establishment
    rules:
      - establishment period does not require maximum light
      - after establishment, gradually reduce shading every 4–5 days

  october:
    stage: active_growth_flowering_fruit_set
    rules:
      - avoid unnecessary shading
      - maximize available light if crop has completed acclimation

  december:
    stage: low_temperature_low_light
    rules:
      - light preservation has high priority
      - unnecessary shading should be avoided
```

---

# 5. Growth-Stage Scheduler

```yaml
growth_stages:
  stage_1:
    name: establishment_vegetative
    priorities:
      - stable_temperature
      - light_acclimation
      - avoid_excessive_shading_after_establishment

  stage_2:
    name: flowering_fruit_set
    priorities:
      - maintain_light
      - maintain_temperature
      - avoid_excess_humidity
      - support_transpiration

  stage_3:
    name: fruit_development_harvest
    priorities:
      - maintain_light
      - stabilize_temperature
      - prevent_condensation
      - humidity_control
```

---

# 6. Baseline Screen Rules from Field Guides

```yaml
screen_baseline:
  thermal_screen:
    autumn_night_closure_percent: 80
    winter_use_window:
      start: sunset_minus_1h
      end: sunrise_plus_0_5h

  diffuse_screen:
    winter_use_window:
      start: sunset_minus_2h
      end: sunrise_plus_2h
    outside_temperature_trigger_C:
      below: 15
```

Notes:
- These are **baseline field-guide rules**, not final MPC-optimal laws.
- Use them as comparison/controller baseline or rule-based fallback.

---

# 7. Baseline Roof Vent Rules from Field Guides

```yaml
roof_vent_baseline:
  rain:
    max_opening_percent: 5
    status: baseline_only

  winter_morning_humidity:
    if_greenhouse_temperature_C_gte: 18
    action: begin_ventilation_even_if_low_light

  screen_active:
    action: maintain_minimum_ventilation_if_needed_to_prevent_condensation
```

Important:
- `5%` is not a manufacturer-certified safety limit.
- Actual wind/rain protection limits must come from the target greenhouse/controller.

---

# 8. Candidate MPC Variables from Stage 1

```yaml
candidate_state_variables:
  - indoor_air_temperature
  - indoor_relative_humidity
  - indoor_vpd

candidate_control_variables:
  - roof_vent_opening_percent
  - screen_opening_or_deployment_percent

candidate_disturbances:
  - outdoor_temperature
  - solar_radiation
  - wind_speed
  - wind_direction
  - rain_status

candidate_outputs:
  - indoor_temperature
  - indoor_relative_humidity
  - indoor_vpd
  - effective_crop_radiation
  - daily_light_integral
```

---

# 9. Candidate Constraints

```yaml
constraints:
  temperature:
    winter_minimum_C:
      value: 14
      type: soft_or_warning
    winter_mean_24h_minimum_C:
      value: 18
      type: reference

  humidity:
    night_RH_high_risk_percent:
      value: 90
      type: warning_or_soft_constraint

  vpd:
    lower_kPa: 0.5
    upper_kPa: 1.2
    type: soft

  roof_vent:
    min_percent: 0
    max_percent: 100
    rain_max_opening_percent:
      value: 5
      status: baseline_only

  screen:
    min_percent: 0
    max_percent: 100
```

---

# 10. Important Unknowns

```yaml
unknowns:
  crop:
    - exact cultivar at target farm
    - exact transplant date
    - actual current phenological stage
    - stage-specific VPD target
    - stage-specific DLI target

  greenhouse:
    - roof_vent_percent_to_angle_mapping
    - roof_vent_area
    - roof_vent_safe_wind_limit
    - rain_override_logic
    - screen_percent_semantics
    - screen_transmittance
    - screen_type_and_material

  radiation:
    - cumulative_light_guide_unit_definition_for_1600J
    - greenhouse_cover_transmittance
    - actual_inside_DLI
```

---

# 11. Do Not Use Directly

```yaml
do_not_use_directly:
  - cumulative_light_value_1600J_without_unit_verification
  - general_tomato_DLI_as_universal_cherry_tomato_optimum
  - VPD_0_8kPa_as_fixed_universal_setpoint
  - spring_Cupid_day_night_temperature_as_all-season_optimum
  - rain_5_percent_vent_as_manufacturer_safety_limit
```

---

# 12. Controller Interpretation

## Temperature

Do not hard-code:

```python
if Tin > 22:
    vent = 50
```

Prefer:

```text
season
+ growth stage
+ time of day
+ solar radiation
+ outdoor temperature
→ reference temperature
→ MPC
```

## Light

Use two time scales:

```text
instantaneous radiation
→ short-term screen decision

daily accumulated DLI
→ daily light preservation objective
```

## Humidity

```text
RH / VPD
→ constraint

night RH > 90%
→ high condensation risk

morning greenhouse T >= 18°C
→ ventilation may be justified for moisture removal
```

---

# 13. Stage-1 Completion Status

```yaml
stage_1_completion:
  temperature_reference: 0.95
  seasonal_temperature_logic: 0.90
  humidity_operational_logic: 0.85
  vpd_reference: 0.65
  instantaneous_light_reference: 0.85
  dli_reference: 0.60
  growth_stage_context: 0.85
  winter_low_light_logic: 0.90
```

Interpretation:
- Temperature / humidity / seasonal logic: sufficient for MPC skeleton design.
- VPD / DLI: usable as candidates but still require validation.
- Exact cultivar- and stage-specific targets remain unresolved.

---

# 14. Next Step — MPC Skeleton

Proceed to:

```text
1. define state x
2. define control u
3. define disturbance d
4. define outputs y
5. define reference scheduler
6. define constraints
7. define objective function terms
```

Recommended starting abstraction:

```yaml
x:
  - Tin
  - RH_or_VPD

u:
  - roof_vent_percent
  - screen_percent

d:
  - Tout
  - solar
  - wind_speed
  - wind_direction
  - rain

y:
  - Tin
  - VPD
  - effective_radiation
  - DLI
```

---

# 15. Provenance Summary

## CHERRY_TOMATO_STUDY
- `Cupid`, Jeonju, Venlo glass greenhouse
- spring crop
- day 22±2°C
- night 16±2°C
- RH 65±5%
- CO₂ 800±50 ppm

## FIELD_GUIDE
- daechu/cherry tomato
- August, October, December operational conditions
- 24 h mean 18–20°C
- October 20–21°C for faster pre-winter growth
- winter minimum 13–14°C
- winter mean ≥17–18°C
- instantaneous light 600–700 W/m²
- night RH >90% risk
- absolute humidity 8 g/kg operational lower threshold
- rain roof vent ≤5%
- seasonal screen timing and use logic

## GENERAL_TOMATO_LITERATURE
- VPD working range 0.5–1.2 kPa
- representative target candidate ~0.8 kPa
- DLI reference 20–30 mol·m⁻²·d⁻¹

---

# 16. Rules for Claude Code / Codex

```text
1. Preserve source type.
2. Preserve uncertainty/status labels.
3. Do not convert candidate values into hard constraints automatically.
4. Do not invent missing cultivar/site parameters.
5. Expose seasonal and growth-stage scheduling as configurable.
6. Keep field-guide baseline separate from MPC optimum.
7. Keep instantaneous-light logic separate from DLI logic.
8. Unknown != zero.
9. Baseline operational rules should remain replaceable.
10. All hard constraints must be traceable to a verified source or target-site rule.
```

Recommended software representation:

```python
ClimateReference(
    source_type=...,
    variable=...,
    value=...,
    units=...,
    status="confirmed|candidate|baseline|unknown",
    season=...,
    growth_stage=...,
    notes=...
)
```

This document is the Stage-1 input specification for:
**MPC state / control / disturbance / objective / constraint design.**

---


# 17. Seasonal Setpoint Baseline — Field Guide Priority Layer

> **Priority rule for MPC setpoint/reference design**
>
> For the initial MPC reference scheduler, use the August/October/December cherry-tomato field guides as the **primary operational baseline** because they provide season-specific, crop-specific, and actuator-relevant management rules.
>
> Use academic literature to:
> 1. check physiological plausibility,
> 2. fill variables absent from the field guides,
> 3. define broader working ranges,
> 4. support later calibration and generalization.
>
> Do not let a broad general-tomato literature value silently overwrite a more specific field-guide value without explicit justification.

```yaml
setpoint_priority:
  1: FIELD_GUIDE_seasonal_operational_baseline
  2: CHERRY_TOMATO_STUDY_crop_specific_support
  3: GENERAL_TOMATO_LITERATURE_gap_filling
  4: TARGET_SITE_DATA_calibration_and_validation
```

---

## 17.1 August Guide — Transplant / Establishment / High-Temperature Transition

### Crop context

```yaml
august_crop_context:
  crop: daechu_cherry_tomato
  likely_stage:
    - transplant
    - establishment
    - early_vegetative_growth
  stem_diameter_mm:
    typical_range: [8, 10]
  truss_development_rate_days_per_truss:
    range: [5, 7]
  notes:
    - high temperature raises respiration demand
    - early vigor may weaken and internode elongation may occur
```

### Light

```yaml
august_light:
  preferred_instantaneous_radiation_W_m2:
    lower: 600
    upper: 700

  cumulative_light_reference:
    value: 1600
    unit_as_written_in_guide: J
    status: UNIT_REQUIRES_VERIFICATION

  establishment_policy:
    - high light is not required during establishment
    - after establishment, gradually reduce shading duration and shading rate
    - recommended adjustment interval: every 4–5 days

  leaf_air_temperature_difference:
    shading_trigger_C:
      value: 4
      interpretation: if leaf temperature - greenhouse air temperature exceeds about 4°C, shading is recommended
    severe_transpiration_warning_C:
      value: 6
      interpretation: guide associates >=6°C difference with excessive transpiration/wilting risk
```

### Temperature

```yaml
august_temperature:
  preferred_24h_mean_C:
    lower: 18
    upper: 20

  operational_intent:
    - remove excess greenhouse heat using natural and forced ventilation
    - prevent excessive day-night temperature difference

  night_thermal_screen:
    closure_percent:
      value: 80
      meaning: approximately 80% closed when night temperature decreases
```

### Humidity / Ventilation

```yaml
august_humidity:
  rainy_or_high_humidity_condition:
    roof_vent_max_opening_percent:
      value: 5
      context: rain / natural ventilation limited
    forced_ventilation:
      recommended: true
    lower_duct_use:
      recommended: true

  objective:
    - remove moisture around crop canopy, especially lower leaf surfaces
    - maintain transpiration
    - reduce fungal disease risk
```

### CO2 / airflow — outside current actuator scope but retain

```yaml
august_CO2:
  high_ventilation_period:
    external_CO2_ppm_reference: 380
  possible_morning_CO2_application:
    timing: approximately_first_2h_after_sunrise
  transplant_stage_note:
    CO2_is_often_not_the_primary_limiting_factor: true

august_airflow:
  forced_ventilation_priority: high
  horizontal_fan_on_cloudy_days:
    day_and_night: recommended
```

### MPC interpretation

```yaml
august_MPC_interpretation:
  temperature_reference:
    mean_24h_C: [18, 20]

  light_control:
    during_establishment:
      shading_tolerance: relatively_high
    after_establishment:
      progressively_reduce_shading: true

  screen_priority:
    daytime_shade: crop_acclimation_dependent
    night_thermal_screen: available_as_baseline_rule

  roof_vent_priority:
    cooling: high
    humidity_removal: high

  note:
    - August values mainly serve as stage-transition reference.
    - Target greenhouse was transplanted later, so use biological-stage logic rather than month-only logic.
```

---

## 17.2 October Guide — Active Growth / Flowering / Fruit Set / Pre-Winter Acceleration

### Crop context

```yaml
october_crop_context:
  reference_transplant_timing: late_August
  observed_stage:
    - first_truss_fruit_enlargement
    - truss_2_to_3_flowering_and_fruit_set
    - truss_2_to_4_flowering_and_fruit_set
  truss_development_rate_days_per_truss:
    range: [7, 9]

  growth_balance:
    - crop vigor generally strengthens
    - growth becomes balanced or slightly reproductive
```

### Light

```yaml
october_light:
  observed_max_instantaneous_radiation_W_m2: 890
  observed_mean_instantaneous_radiation_W_m2: 645
  observed_mean_cumulative_light:
    value: 1340
    unit_as_written_in_guide: J
    status: UNIT_REQUIRES_VERIFICATION

  preferred_instantaneous_radiation_W_m2:
    lower: 600
    upper: 700

  cumulative_light_reference:
    value: 1600
    unit_as_written_in_guide: J
    status: UNIT_REQUIRES_VERIFICATION

  shading_policy:
    - after successful light acclimation, avoid unnecessary shading
    - expose crop to as much useful light as possible
```

### Temperature

```yaml
october_temperature:
  general_preferred_24h_mean_C:
    lower: 18
    upper: 20

  accelerated_pre_winter_24h_mean_C:
    lower: 20
    upper: 21
    purpose:
      - accelerate growth before winter low-light period
      - advance crop development while conditions are favorable

  daytime_overheating_control:
    natural_ventilation: recommended
    forced_ventilation: recommended
```

### Humidity / Ventilation

```yaml
october_humidity:
  night_RH_trend:
    increasing: true

  rainy_condition:
    roof_vent_max_opening_percent:
      value: 5
      status: field_guide_rule_not_structural_safety_limit
    forced_exhaust:
      recommended: true

  lower_canopy_airflow:
    recommended: true
```

### Screen

```yaml
october_screen:
  night_thermal_screen:
    closure_percent:
      value: 80
      context: when nighttime temperature decreases

  daytime_shading:
    default_policy: minimize
    reason: high crop light demand during active flowering_and_fruit_set
```

### CO2 / airflow — retained for context

```yaml
october_CO2:
  morning_application_ppm:
    lower: 400
    upper: 500
  suggested_timing:
    after_sunrise_hours: [2, 3]
  afternoon_external_air_reference_ppm: 380

october_airflow:
  vertical_airflow_priority: high
  purpose:
    - reduce vertical temperature_humidity gradients
    - improve leaf gas exchange and transpiration
```

### MPC interpretation

```yaml
october_MPC_interpretation:
  crop_stage_priority:
    light_preservation: very_high
    temperature_tracking: high
    humidity_control: medium_to_high

  temperature_reference:
    normal_mean_24h_C: [18, 20]
    pre_winter_acceleration_mean_24h_C: [20, 21]

  screen_cost_weight:
    unnecessary_daytime_deployment_penalty: high

  roof_vent:
    preferred_for_excess_heat_when_light_should_be_preserved: true

  conceptual_rule:
    - if solar is useful and temperature can be controlled by ventilation, preserve light before deploying shade
```

This is especially relevant to the target greenhouse because a **mid-to-late September transplant** can place the crop in establishment-to-early flowering/fruit-set development during October.

---

## 17.3 December Guide — Winter Low-Light / Slow Growth / Condensation Risk

### Crop development

```yaml
december_crop_context:
  season: low_temperature_low_light
  truss_development_rate_days_per_truss:
    lower: 12
    upper: 14

  growth_behavior:
    - development slows substantially before February
    - crop load and growth rate balance becomes important
    - slight vegetative tendency may be acceptable/useful for maintaining vigor through winter

  stem_diameter_mm:
    reported_range: [7, 12]
```

### Light

```yaml
december_light:
  observed_instantaneous_radiation_W:
    lower: 380
    upper: 650

  observed_cumulative_light:
    lower: 458
    upper: 1320
    unit_as_written_in_guide: J
    status: UNIT_REQUIRES_VERIFICATION

  strategy:
    - preserve available winter light
    - improve greenhouse transmission where possible
    - avoid unnecessary shading
    - maintain appropriate leaf area and fruit exposure
```

### Temperature — basic references

```yaml
december_temperature:
  minimum_temperature_C:
    values_reported_in_guide:
      - 13
      - 14
    interpretation:
      - use 14°C as stronger practical lower baseline
      - retain 13°C as lower reference found in guide text

  mean_24h_temperature_C:
    values_reported:
      - minimum_17
      - preferred_minimum_18

  observed_example_mean_24h_C:
    value: 15.7
    context: December_weeks_1_to_2
    interpretation: observed condition, not desired setpoint
```

### Dynamic vent-temperature schedule

```yaml
december_vent_temperature_schedule_C:
  morning_day:
    base: 19
    solar_modifier:
      trigger_variable: instantaneous_radiation
      max_additional_C: 1

  afternoon_day:
    base_range: [26, 27]
    solar_modifier:
      trigger_variable: cumulative_radiation
      max_additional_C: 2

  early_evening:
    base: 16.5

  night:
    base: 16
    solar_modifier:
      trigger_variable: cumulative_radiation
      max_additional_C: 2
```

This should be interpreted as a **dynamic reference scheduler concept**, not a single fixed threshold:

```text
T_reference(t)
=
base_reference(time_of_day)
+
solar_dependent_modifier
```

### Heating schedule — retained although heating is outside current control scope

```yaml
december_heating_temperature_schedule_C:
  day: 16
  night: 14
  night_solar_modifier:
    trigger_variable: cumulative_radiation
    max_additional_C: 2
```

### Screen schedule

```yaml
december_screen:
  aluminum_thermal_screen:
    start: sunset_minus_1h
    end: sunrise_plus_0_5h

  diffuse_screen:
    start: sunset_minus_2h
    end: sunrise_plus_2h
    outdoor_temperature_condition_C:
      use_when_below: 15

  coupled_ventilation:
    rule: use_minimum_ventilation_as_needed_to_prevent_condensation_while_screen_is_active
```

### Humidity / condensation

```yaml
december_humidity:
  measured_RH_range_percent:
    lower: 41.9
    upper: 100

  measured_absolute_humidity_g_per_kg:
    lower: 6.6
    upper: 19.2

  night_RH_high_risk_percent:
    threshold: 90
    risks:
      - condensation
      - fungal_disease
      - physiological_damage
      - fruit_quality_loss

  morning_ventilation_trigger:
    greenhouse_temperature_C:
      threshold: 18
    condition:
      - even_if_cloudy_or_low_instantaneous_light
    purpose:
      - humidity_removal
      - condensation_prevention

  daytime_absolute_humidity_lower_threshold_g_per_kg:
    value: 8
    if_below:
      - stop_forced_ventilation
      - minimize_roof_vent_opening
      - close_diffuse_screen_if_appropriate
```

### Additional potentially useful environmental values

```yaml
december_root_zone:
  minimum_root_zone_temperature_C: 13

december_CO2:
  economically_favorable_when_ventilation_rate_percent_below: 10
  recommended_CO2_application_when_ventilation_rate_percent_below: 15
  recommended_timing:
    start: sunrise
    end: sunrise_plus_4h

december_airflow:
  circulation_fan_cycle:
    on_minutes: 5
    off_minutes: 10

  forced_ventilation_absolute_humidity_trigger_g_per_kg:
    value: 20
    condition: night
    note: horizontal_screen_closed_while_exhaust_fan_operates
```

### MPC interpretation

```yaml
december_MPC_interpretation:
  dominant_priorities:
    1: avoid_excess_heat_loss
    2: preserve_light
    3: prevent_condensation_and_extreme_humidity
    4: maintain_crop_development_rate

  screen:
    thermal_retention_weight: high
    unnecessary_daytime_shading_penalty: very_high

  vent:
    heat_loss_penalty: high
    humidity_removal_value: conditionally_high

  key_tradeoff:
    - roof vent removes moisture but also loses heat
    - screen preserves heat but can worsen humidity
    - coordinated control is required
```

---

## 17.4 Month Is Not the Only Scheduler Variable

The field guides are monthly, but the MPC should not hard-code control purely by calendar month.

Use:

```yaml
reference_scheduler_inputs:
  required:
    - crop_growth_stage
    - season_or_month
    - time_of_day
    - current_indoor_temperature
    - current_indoor_humidity_or_VPD
    - outdoor_temperature
    - instantaneous_solar_radiation
    - accumulated_light

  future_optional:
    - short_term_weather_forecast
    - predicted_DLI
    - crop_load
    - observed_vigor
```

Recommended hierarchy:

```text
Crop biological stage
       +
Seasonal environment
       +
Current / forecast weather
       ↓
Dynamic reference
       ↓
MPC optimizer
```

---

# 18. Detailed Literature Value Library — Retain Even If Not Immediately Used

> These values are deliberately retained in detail for later model selection, constraint design, sensitivity testing, and field calibration.
>
> **Do not collapse them into a single “best value.”**
>
> Source-specific context must remain visible.

---

## 18.1 General Greenhouse Tomato Temperature Literature

### Shamshiri et al. (2018) review — stage-dependent temperature references

Reported literature values summarized in the review include:

```yaml
general_tomato_temperature_literature:
  leaf_and_truss_development:
    optimal_air_temperature_C: 22
    original_reference_in_review: Sato_et_al_2000

  fruit_addition:
    optimal_air_temperature_C:
      lower: 22
      upper: 26

  fruit_growth_and_fruit_set:
    optimal_air_temperature_C:
      lower: 22
      upper: 25

  warm_season_greenhouse_crop_general_range_C:
    lower: 17
    upper: 27

  marginal_general_temperature_C:
    lower: 10
    upper: 35

  entire_tomato_growing_season_reported_optimal_C:
    lower: 18.3
    upper: 32.2
    note: broad literature range; not suitable as a direct MPC target
```

MPC use:
- support stage-aware temperature scheduler,
- cross-check field-guide values,
- define broad plausibility bounds,
- **do not replace specific Korean cherry-tomato field-guide targets with these broad ranges.**

Source:
- Shamshiri et al. (2018), *International Agrophysics* 32(2):287–302.

---

## 18.2 General Tomato VPD Literature

Shamshiri et al. (2018) reports several distinct sources rather than one universal optimum.

```yaml
general_tomato_VPD_literature:
  source_range_1:
    optimal_kPa:
      lower: 0.47
      upper: 1.27

  source_range_2:
    ideal_kPa:
      lower: 0.40
      upper: 0.79

  commercial_greenhouse_reference:
    optimal_kPa:
      lower: 0.5
      upper: 1.2
    marginal_kPa:
      lower: 0.4
      upper: 1.37

  another_reported_ideal_range_kPa:
    lower: 0.75
    upper: 1.06
    marginal_lower: 0.45
    marginal_upper: 1.25

  physiological_warning:
    high_VPD_kPa:
      threshold: 1.5
      reported_risks:
        - wilting
        - leaf_roll
        - stunted_growth
        - leaf_drying

  winter_fogging_example:
    VPD_before_kPa: 1.4
    VPD_after_kPa: 0.8
    reported_biomass_increase_percent: 17.3
    reported_yield_increase_percent: 12.35
```

Useful psychrometric examples from the same review:

```yaml
VPD_examples:
  constant_RH_75_percent:
    T20_C_VPD_kPa: 0.584
    T25_C_VPD_kPa: 0.791
    T30_C_VPD_kPa: 1.060

  constant_T25_C:
    RH45_VPD_kPa: 1.741
    RH60_VPD_kPa: 1.266
    RH70_VPD_kPa: 0.950
    RH75_VPD_kPa: 0.791
    RH80_VPD_kPa: 0.633
    RH85_VPD_kPa: 0.475
    RH90_VPD_kPa: 0.317
```

Practical interpretation:
- the field-guide RH rules and literature VPD ranges should be used together;
- VPD can serve as a derived physiological variable rather than replacing RH entirely;
- in winter, very high RH can make VPD too low even when temperature is acceptable.

---

## 18.3 Winter Tomato VPD / Temperature Coupling

Literature summarized by Shamshiri et al. notes:

```yaml
winter_VPD_temperature_coupling:
  example:
    action: raise_air_temperature
    amount_C: 2
    context: winter_high_humidity_period
    purpose: maintain_more_favorable_VPD
```

Also retained:
- night temperature below about 16°C has been reported as potentially problematic in some literature, with possible day-temperature compensation.
- This is **not** a direct contradiction of the Korean field guide’s lower night heating/temperature references; they reflect different systems, production strategies, energy economics, and crop-management contexts.

For this project:
- retain both,
- use field-guide values for the baseline,
- test crop response and actual 24-h mean temperature at the target site.

---

## 18.4 General Tomato DLI Literature

A greenhouse tomato supplemental-lighting study states:

```yaml
general_tomato_DLI:
  suggested_for_good_flavor_and_high_yield_mol_m2_d:
    lower: 20
    upper: 30
```

Interpretation:
- this is a useful **production-light reference**, not necessarily the direct internal DLI target for every cultivar, greenhouse, season, or canopy stage;
- it is particularly useful when evaluating whether winter shading is unnecessarily reducing already-limited crop light.

Source retained:
- *Effects of supplemental light on tomato growth and the mechanism of the photosystem II apparatus*.

---

## 18.5 Cherry Tomato DLI — ‘Jun-Ama’ Year-Round Lighting Study

Cherry tomato cultivar:
- `Jun-Ama`

Greenhouse natural-light context:

```yaml
Jun_Ama_cherry_tomato_lighting:
  average_greenhouse_natural_DLI_mol_m2_d: 14.5

  supplemental_DLI_mol_m2_d:
    interlighting: 2.7
    toplighting: 4.9
    inter_plus_toplighting: 7.6

  yield_change_percent_vs_control:
    interlighting: 18
    toplighting: 41
    inter_plus_toplighting: 40

  fruit_number_change_percent:
    interlighting: 11
    toplighting: 26
    inter_plus_toplighting: 27

  fruit_weight_change_percent:
    toplighting: 10
    inter_plus_toplighting: 10
```

Interpretation:
- 14.5 mol·m⁻²·d⁻¹ was **not demonstrated as an optimum**.
- Yield still responded positively to added light.
- This supports using DLI as a meaningful cumulative light objective in the MPC.
- It also supports penalizing unnecessary screen deployment in low-light seasons.

Source:
- Maeda et al. (2022), *Comparison of Supplemental LED Top- and Interlighting for Year-Round Production of Cherry Tomato*.

---

## 18.6 Cherry Tomato DLI — Full-Spectrum Supplemental Lighting Study

Another cherry tomato supplemental-light experiment reported:

```yaml
cherry_tomato_full_spectrum_LED_study:
  natural_light_control_DLI_mol_m2_d: 8.34

  total_DLI_mol_m2_d:
    HPS: 11.24
    narrow_spectrum_LED: 10.83
    full_spectrum_LED_1: 10.23
    full_spectrum_LED_2: 10.08

  reported_yield_increase_percent:
    full_spectrum_LED_1: 73.1
    full_spectrum_LED_2: 70.7

  lighting_duration_hours_per_day: 8
```

Interpretation:
- these DLI values are experimental treatment contexts, not universal optimal DLI;
- nevertheless, they demonstrate strong crop response under relatively low natural-light conditions and are relevant to winter light-preservation logic.

Source:
- *Growth, Fruit Yield, and Bioactive Compounds of Cherry Tomato in Response to Specific White-Based Full-Spectrum Supplemental LED Lighting*.

---

## 18.7 Cherry Tomato Spring Study — ‘Cupid’

From the Korean `Cupid` study:

```yaml
Cupid_spring_study:
  location: Jeonju_Korea
  greenhouse: Venlo_type_glass
  cropping_period: March_to_July

  environmental_management:
    daytime_temperature_C:
      target: 22
      tolerance: 2
    nighttime_temperature_C:
      target: 16
      tolerance: 2
    RH_percent:
      target: 65
      tolerance: 5
    CO2_ppm:
      target: 800
      tolerance: 50

  GDD:
    base_temperature_C: 10
    maximum_threshold_C: 30

  observed_monthly_PPFD_umol_m2_s:
    March: approximately_180
    June: approximately_230

  observed_RH_percent:
    approximately: 78

  growth_model:
    plant_height:
      carrying_capacity_cm: 185.3
      R2: 0.94
    LAI:
      carrying_capacity: 3.85
      R2: 0.92
    fruit_yield:
      carrying_capacity_g_per_plant: 2845
      R2: 0.91
```

Important:
- managed setpoints and measured monthly means are different concepts;
- these spring values should not overwrite winter field-guide setpoints;
- GDD can later be useful for growth-stage scheduling.

---

## 18.8 Light Conversion / Interpretation Warning

The field guides use instantaneous radiation in `W` and accumulated light in `J`, while academic crop-light literature frequently uses:

```text
PPFD      → μmol·m⁻²·s⁻¹
DLI       → mol·m⁻²·d⁻¹
Solar     → W·m⁻²
Radiant energy → J·m⁻²
```

Therefore:

```yaml
light_unit_policy:
  field_guide_600_700W:
    retain_as_written: true
    likely_interpretation: instantaneous_solar_radiation
    verify_sensor_definition: required

  field_guide_1600J:
    use_as_numeric_MPC_target_now: false
    reason: area_and_accumulation_definition_not_explicit_in_document

  academic_DLI:
    unit: mol_m2_d
    use_for_daily_crop_light_objective: yes_candidate
```

Do not convert between W/m² and PPFD using a universal factor unless:
- spectrum/source assumptions are explicitly stated,
- the purpose tolerates approximation.

---

## 18.9 Literature Values That May Become Constraints Later

Retain the following even if not used in MPC v1:

```yaml
potential_future_constraints:
  temperature:
    leaf_truss_development_C: 22
    fruit_addition_C: [22, 26]
    fruit_growth_set_C: [22, 25]
    broad_marginal_C: [10, 35]

  VPD:
    preferred_working_kPa: [0.5, 1.2]
    broader_reported_optimal_kPa: [0.47, 1.27]
    high_risk_kPa: 1.5

  DLI:
    general_tomato_high_production_mol_m2_d: [20, 30]

  winter_cherry_tomato_field_baseline:
    24h_mean_C: [17, 18]
    minimum_C: [13, 14]
    night_RH_high_risk_percent: 90
```

---

## 18.10 Suggested Dynamic Reference Scheduler

The initial setpoint generator should be implemented as a separate module from the MPC optimizer.

```text
Field Guide Seasonal Baseline
        +
Crop Stage
        +
Time of Day
        +
Current Solar
        +
Accumulated Light / DLI
        +
Humidity / Condensation State
        +
Outdoor Temperature
        ↓
Dynamic References
        ↓
MPC
```

Suggested output interface:

```yaml
reference_scheduler_output:
  T_reference_C:
  T_soft_min_C:
  T_soft_max_C:
  VPD_reference_kPa:
  VPD_band_kPa:
  instantaneous_light_reference_W_m2:
  DLI_target_mol_m2_d:
  condensation_risk:
  light_preservation_priority:
  screen_deployment_penalty:
  vent_heat_loss_penalty:
```

Example conceptual winter behavior:

```text
LOW DLI accumulated
+ low external temperature
+ acceptable Tin
→ strong penalty on unnecessary screen shading
→ strong penalty on excessive vent opening

HIGH RH / condensation risk
→ reduce vent heat-loss penalty enough to permit moisture removal

HIGH useful solar
+ Tin rising
→ compare ventilation vs screen action
→ preserve light if ventilation can manage temperature efficiently
```

---

## 18.11 Literature Source Registry

```yaml
literature_registry:

  shamshiri_2018:
    title: Review of optimum temperature, humidity, and vapour pressure deficit for microclimate evaluation and control in greenhouse cultivation of tomato
    journal: International Agrophysics
    year: 2018
    use:
      - temperature_ranges
      - VPD_ranges
      - stage_specific_temperature
      - psychrometric_context

  maeda_2022:
    title: Comparison of Supplemental LED Top- and Interlighting for Year-Round Production of Cherry Tomato
    crop: cherry_tomato_Jun_Ama
    year: 2022
    use:
      - cherry_tomato_DLI_context
      - yield_response_to_supplemental_light

  cherry_tomato_full_spectrum_LED:
    title: Growth, Fruit Yield, and Bioactive Compounds of Cherry Tomato in Response to Specific White-Based Full-Spectrum Supplemental LED Lighting
    year: 2022
    use:
      - low_DLI_cherry_tomato_context
      - lighting_response

  cupid_2026:
    title: Growth and Yield Modeling of the Cherry Tomato 'Cupid' Based on Environmental Data and Model-Driven Nutrient Management in Spring Cropping
    year: 2026
    location: Jeonju_Korea
    use:
      - Korean_cherry_tomato_environmental_management
      - GDD
      - growth_stage_context

  tomato_supplemental_light:
    title: Effects of supplemental light on tomato growth and the mechanism of the photosystem II apparatus
    use:
      - general_tomato_DLI_reference_20_30
```

---

# 17. Field Validation, Calibration, and Practical Parameter Use

> This section defines how literature- and guide-based values should be treated after the prototype reaches field validation.
>
> Core principle:
>
> **Use literature/field-guide values as baseline operating references first, then calibrate only where field evidence shows a persistent and meaningful mismatch.**
>
> Do not treat field calibration as “discarding the literature values.”  
> Treat it as **adapting a literature-grounded baseline to the target greenhouse, crop stage, season, and actual actuator behavior.**

---

## 17.1 Parameter Interpretation Hierarchy

Use the following hierarchy when deciding how strongly a parameter may be changed.

```yaml
parameter_interpretation:
  level_1_crop_safety_or_biological_range:
    examples:
      - minimum_temperature
      - excessive_night_RH
      - acceptable_VPD_band
    adjustment_policy: conservative
    meaning: do_not_move_far_without_strong_crop_evidence

  level_2_operational_reference:
    examples:
      - 24h_mean_temperature_target
      - seasonal_temperature_schedule
      - instantaneous_light_reference
    adjustment_policy: moderate
    meaning: tune_with_field_response_and_crop_condition

  level_3_controller_parameter:
    examples:
      - screen_switch_threshold
      - vent_opening_gain
      - dwell_time
      - hysteresis
      - rate_limit
    adjustment_policy: actively_calibratable
    meaning: expected_to_be_site_specific

  level_4_physical_model_parameter:
    examples:
      - effective_heat_capacity
      - ventilation_coefficient
      - cover_U_value
      - screen_transmittance
    adjustment_policy: calibrate_from_measurement
    meaning: should_be_fitted_or_replaced_when_field_data_exists
```

Interpretation:

- **작물 안전범위**는 현장 데이터 몇 일만 보고 쉽게 바꾸지 않는다.
- **운영 목표값**은 실제 작물상태와 계절조건을 보면서 조정 가능하다.
- **제어기 파라미터**는 원래부터 현장별 차이가 크므로 적극적으로 튜닝한다.
- **물리모델 파라미터**는 실측 데이터가 들어오면 보정하는 것이 정상적인 절차다.

---

## 17.2 Baseline → Field-Calibrated Parameter Workflow

Recommended workflow:

```text
Literature / Field Guide
        ↓
Initial Working Parameter
        ↓
Offline Simulation
        ↓
Live Monitoring Only
        ↓
Prediction Error Analysis
        ↓
Parameter Calibration
        ↓
Field Validation
        ↓
Operational MPC Recommendation
```

Do not skip directly from literature values to autonomous control.

Current project scope should remain:

```text
MPC recommendation
→ dashboard display
→ human review

NOT

MPC
→ direct PLC write
```

until sufficient validation is completed.

---

## 17.3 What to Calibrate First

Calibration priority should follow sensitivity to control performance.

```yaml
calibration_priority:
  1:
    parameter: vent_effectiveness
    reason: roof_vent_control_depends_directly_on_actual_air_exchange
  2:
    parameter: screen_effect_on_radiation
    reason: screen_control_depends_on_actual_transmitted_solar_load
  3:
    parameter: effective_greenhouse_thermal_capacity
    reason: determines_temperature_response_speed
  4:
    parameter: cover_heat_loss_coefficient
    reason: important_in_autumn_and_winter
  5:
    parameter: humidity_or_transpiration_terms
    reason: add_after_temperature_model_is_stable
```

The first field model does **not** need every parameter calibrated simultaneously.

Prefer:

```text
temperature model first
→ vent response
→ screen/radiation response
→ humidity model
```

---

## 17.4 Practical Calibration of Roof Vent Parameters

The literature may provide the model structure, but the target greenhouse must determine the actual effectiveness.

Initial generic model:

```math
Vdot = f(vent_opening, wind_speed, wind_direction, Tin - Tout)
```

Field calibration should estimate:

```yaml
roof_vent_calibration:
  required_inputs:
    - timestamp
    - indoor_temperature
    - outdoor_temperature
    - vent_opening_percent
    - wind_speed
    - wind_direction
    - solar_radiation

  useful_events:
    - stable_weather_before_vent_change
    - clear_step_change_in_vent_opening
    - no_simultaneous_large_screen_change_if_possible

  estimated_quantities:
    - temperature_response_delay
    - effective_ventilation_gain
    - opening_percent_to_effect_relationship
```

Example:

```text
Vent 20% → 40%
↓
observe Tin trajectory for next 5–20 min
↓
compare prediction vs measurement
↓
update ventilation coefficient / response delay
```

Important:
- Do not assume `50% vent opening = 50% ventilation`.
- Actual response may be nonlinear.
- Wind direction can change effectiveness even at identical vent opening.

---

## 17.5 Practical Calibration of Screen Parameters

Before full ray tracing is available, use a temporary effective transmission model.

Example:

```math
I_eff = I_out * tau_screen_eff(u_screen)
```

Field calibration:

```yaml
screen_calibration:
  preferred_measurements:
    - outside_solar_radiation
    - inside_solar_or_PAR_if_available
    - screen_position_percent
    - solar_altitude
    - solar_azimuth

  estimate:
    - effective_transmission_by_screen_position
    - deployment_delay
    - partial_deployment_nonlinearity
```

If an inside radiation/PAR sensor is unavailable:

```text
Use screen transmission as a literature/manufacturer baseline
→ retain higher uncertainty
→ later replace with ray-tracing-derived response map
```

When ray tracing is completed:

```text
temporary screen surrogate
→ ray-derived transmission / effective crop radiation
```

MPC structure should not need to change.

---

## 17.6 Temperature Target Calibration

The current climate targets are literature/field-guide baselines.

Do not tune the crop target simply because the controller prediction is wrong.

Separate:

```text
MODEL ERROR
vs
TARGET ERROR
```

### Model error

Example:

```text
Target = 19°C
Prediction = 19°C
Measured = 21°C
```

Interpretation:
- prediction model likely needs calibration.

Do **not** immediately change target to 21°C.

### Target mismatch

Example:

```text
Temperature maintained near literature target
but crop observations repeatedly indicate:
- excessive vegetative growth
- slow truss development
- condensation issue
- poor fruit set
```

Then target scheduling may require agronomic adjustment.

Recommended rule:

```yaml
temperature_target_adjustment:
  first_check:
    - sensor_accuracy
    - model_prediction_error
    - spatial_temperature_variation
    - actuator_response
  then_check:
    - crop_growth_status
    - truss_development_rate
    - seasonal_light_condition
  only_then:
    action: modify_reference_schedule
```

---

## 17.7 VPD / Humidity Calibration

Use VPD primarily as a **working physiological band**, not a rigid single-value target.

Initial:

```yaml
VPD_working_band_kPa:
  lower: 0.5
  upper: 1.2
```

Field interpretation:

```text
VPD within range
+ no condensation
+ acceptable crop transpiration
→ keep baseline

Persistent high RH / condensation
→ strengthen moisture-removal priority

Persistent high VPD / wilting tendency
→ reduce excessive ventilation / shading-driven drying
```

Do not optimize VPD independently from temperature and radiation.

Preferred hierarchy:

```text
temperature safety
→ condensation / humidity risk
→ VPD quality
```

for the initial winter prototype.

---

## 17.8 DLI and Instantaneous Radiation Should Be Treated Differently

Do not use DLI and instantaneous radiation as interchangeable variables.

```yaml
light_control:
  instantaneous_radiation:
    timescale: minutes
    primary_use:
      - short_term_screen_decision
      - overheating_prevention

  DLI:
    timescale: daily
    primary_use:
      - preserve_daily_crop_light
      - penalize_unnecessary_winter_shading
```

Practical MPC interpretation:

```text
High instantaneous radiation
but daily DLI still low
→ avoid overly aggressive shading unless thermal risk is high

High instantaneous radiation
and sufficient accumulated light
and Tin rising
→ screen action becomes easier to justify
```

This distinction is especially important in winter.

---

## 17.9 Growth Stage and Seasonal Parameters

Do not create completely separate MPC models for every crop stage unless field evidence requires it.

Preferred design:

```text
same prediction model
+
different reference scheduler / weights / constraints
```

Example:

```yaml
stage_scheduler:
  establishment:
    light_priority: medium
    temperature_stability_priority: high

  flowering_fruit_set:
    light_priority: high
    humidity_control_priority: high

  fruit_development_harvest:
    light_priority: high
    condensation_control_priority: high
```

Season may matter as much as biological stage.

For the target crop:

```text
September transplant
→ October active establishment / flowering
→ November transition
→ December–winter low-light control
```

Therefore scheduler inputs may eventually include both:

```yaml
scheduler_inputs:
  - growth_stage
  - month_or_season
  - current_light_condition
```

---

## 17.10 How to Judge Whether a Parameter Needs Adjustment

Do not adjust parameters from a single unusual day.

Recommended minimum evidence:

```yaml
parameter_update_rule:
  require:
    - repeated_error_under_similar_conditions
    - physically_consistent_error_direction
    - sufficient_sensor_quality
  avoid:
    - tuning_from_single_outlier
    - tuning_during_sensor_fault
    - tuning_during_unrecorded_manual_operation
```

Examples:

```text
Same solar / wind region
vent model repeatedly underpredicts cooling
→ increase effective ventilation response

Only one day differs due to sudden cloud/rain/manual operation
→ do not recalibrate immediately
```

---

## 17.11 Prediction Error Metrics

At minimum track:

```yaml
validation_metrics:
  temperature:
    - RMSE
    - MAE
    - bias
  humidity:
    - RMSE
    - MAE
    - bias
  radiation:
    - RMSE
    - relative_error
```

Also record control-oriented errors:

```text
peak temperature error
time-to-peak error
response delay error
overshoot
```

These are often more useful for MPC than RMSE alone.

---

## 17.12 Field Validation Levels

```yaml
validation_levels:

  level_0:
    name: offline_sanity_check
    data: mock_or_public
    goal: check_direction_and_stability

  level_1:
    name: passive_live_validation
    data: real_sensor_data
    control: existing_farm_control
    goal: validate_prediction_model

  level_2:
    name: recommendation_shadow_mode
    control: MPC_recommendation_not_applied
    goal: compare_MPC_vs_existing_rule

  level_3:
    name: supervised_field_trial
    control: human_approved_actions
    goal: test_real_response

  level_4:
    name: autonomous_control
    status: out_of_current_scope
```

Current project target should primarily reach:

```text
Level 1 → Level 2
```

and optionally limited Level 3 if field conditions and approval permit.

---

## 17.13 Recommended Comparison During Field Validation

For every decision timestamp, store:

```yaml
validation_record:
  measured_state:
    Tin:
    RH:
    Tout:
    solar:
    wind:
  actual_farm_control:
    vent_percent:
    screen_percent:
  MPC_recommendation:
    vent_percent:
    screen_percent:
  predicted_future:
    Tin:
    RH:
    effective_radiation:
  measured_future:
    Tin:
    RH:
```

This allows three separate evaluations:

```text
1. Was the prediction model accurate?
2. Was the MPC recommendation different from the farm rule?
3. Would the recommendation likely improve the target objective?
```

Do not collapse all three into one metric.

---

## 17.14 Practical Treatment of Literature Values

Use this default policy:

```yaml
literature_parameter_policy:

  crop_reference:
    initial_use: yes
    calibration: limited
    validation: required

  field_guide_operational_rule:
    initial_use: yes
    use_as_baseline_controller: yes
    replacement_by_MPC: allowed_after_validation

  physical_coefficient:
    initial_use: yes_if_needed
    calibration: strongly_recommended

  actuator_limit:
    literature_substitution: avoid
    target_site_confirmation: required
```

In practical terms:

```text
Use literature values to START.
Use field data to CALIBRATE.
Use repeated validation to JUSTIFY changes.
Do not wait for perfect parameters before building the prototype.
```

---

## 17.15 Recommended Parameter Status Labels

For implementation, replace overly binary `valid/invalid` logic with:

```yaml
parameter_status:
  literature_baseline:
    meaning: directly adopted as initial literature value

  field_guide_baseline:
    meaning: practical operating value from cultivation guide

  calibrated:
    meaning: adjusted using target-site data

  field_verified:
    meaning: tested and shown acceptable at target site

  provisional:
    meaning: usable for prototype but uncertain

  unknown:
    meaning: not available
```

Example:

```yaml
ventilation_coefficient:
  value: 0.XX
  status: provisional
  source: literature_baseline
  calibration_required: true
```

After field fitting:

```yaml
ventilation_coefficient:
  value: 0.YY
  status: calibrated
  source: target_site_data
  validation_required: true
```

---

## 17.16 Practical Research Principle

For this project, the preferred philosophy is:

```text
NOT:
"Do not use a parameter until it is perfectly verified."

BUT:
"Use the best literature-grounded value available,
label its confidence,
build the model,
then improve it with field evidence."
```

This is especially appropriate because the current system is intended first as:

```text
prediction + recommendation + monitoring
```

rather than immediate autonomous actuator control.

---

## 17.17 Recommended Next Development Sequence

```text
Stage 1
Literature-based climate references
[CURRENT DOCUMENT]

↓
Stage 2
MPC skeleton
x / u / d / y / J / constraints

↓
Stage 3
Simple greenhouse prediction model
temporary screen + vent response

↓
Stage 4
Offline simulation

↓
Stage 5
Passive live-data validation

↓
Stage 6
Parameter calibration

↓
Stage 7
MPC shadow-mode recommendation

↓
Stage 8
Compare:
existing farm rule
vs
literature baseline
vs
MPC recommendation
```

The model should remain modular so that:

```text
simple radiation model
→ ray-tracing model

simple vent model
→ calibrated natural ventilation model

literature parameter
→ target-site calibrated parameter
```

can be replaced without rewriting the MPC architecture.




---

# Appendix B — Detailed Vent / Screen Control-Logic Reference

The following embedded section preserves the previous detailed control-logic extraction as supporting material.


# MPC Stage 2 — Roof Vent & Screen Control Logic Reference

> 목적: 방울토마토 온실의 `roof vent + screen` MPC를 설계하기 전에, 문헌에서 **제어 로직만 분리하여** 최소 필수 로직과 향후 설계 시 참고할 수 있는 확장 로직/수식을 정리한다.
>
> 원칙:
> - 논문 전체 제어기를 그대로 채택하지 않는다.
> - `MANDATORY_BASELINE`과 `DESIGN_REFERENCE`를 구분한다.
> - 논문 고유 수치와 구조는 그대로 복사하지 않고, **전이 가능한 논리만** MPC 구조에 반영한다.
> - 현장 안전 한계(강풍, 우천, 실제 개도율-각도 관계)는 반드시 대상 농가/제어기/제조사 값으로 대체한다.
> - `thermal screen`, `shade screen`, `diffuse screen`은 같은 장치로 취급하지 않는다.

---

# 1. Source Role Registry

```yaml
sources:

  FAO_2013:
    title: Good Agricultural Practices for greenhouse vegetable crops
    role:
      - practical_control_sequence
      - ventilation_vs_shading_priority
      - humidity_control
      - thermal_screen_timing
      - energy_efficiency
    transferability: high_for_logic

  Campen_2009:
    title: Mechanically controlled moisture removal from greenhouses
    role:
      - thermal_screen_humidity_interaction
      - small_screen_opening_risk
      - dehumidification_sequence
    transferability: high_for_humidity_logic

  Bailey_1988:
    title: Control Strategies to Enhance the Performance of Greenhouse Thermal Screens
    role:
      - thermal_screen_open_close_logic
      - solar_threshold_control
      - energy_vs_light_tradeoff
      - screen_heat_loss_model
    transferability: high_for_logic_moderate_for_parameters

  Liu_2023:
    title: A Two-Factor Thermal Screen Control Strategy for Chinese Solar Greenhouses in High-Latitude Areas
    role:
      - screen_timing_based_on_solar_and_deltaT
      - energy_balance_open_close_condition
    transferability: logic_only

  Jung_2020:
    title: Model Predictive Control via Output Feedback Neural Network for Improved Multi-Window Greenhouse Ventilation Control
    role:
      - vent_control_input_definition
      - prediction_based_ventilation_control
      - 0_to_100_percent_window_control
    transferability: architecture_only

  Hahn_2011:
    title: Fuzzy controller decreases tomato cracking in greenhouses
    role:
      - anti_chattering_logic
      - persistence_logic
      - radiation_based_screen_operation
    transferability: logic_only

  Su_Xu_2022:
    title: Setpoint Decision Support Strategy and Adaptive Hybrid Control of Greenhouse Climate
    role:
      - controller_layer_separation
      - separate_vent_and_screen_flux_terms
      - gray_box_state_structure
    transferability: architecture_and_model_structure
```

---

# 2. Minimum Mandatory Control Logic

The following logic should be present in the first MPC/baseline implementation even if the detailed parameter values are still provisional.

## 2.1 Roof Vent — Minimum Logic

### VENT-M1 — Temperature-driven ventilation

```text
IF indoor temperature exceeds the dynamic temperature reference
AND outside conditions can provide useful cooling
THEN increase roof-vent opening.
```

```yaml
VENT_M1:
  trigger:
    - Tin > Tref
  modifiers:
    - Tout
    - wind_speed
    - wind_direction
    - solar_radiation
  action:
    - increase_roof_vent_opening
```

Important:
- Ventilation should not be based on `Tin` alone.
- Wind and outdoor temperature modify actual ventilation effectiveness.
- Vent opening should be continuous/proportional where hardware permits.

## 2.2 Roof Vent — Humidity override

### VENT-M2 — Moisture removal

```text
IF humidity/condensation risk becomes unacceptable
THEN ventilation may be required even when cooling demand is small.
```

```yaml
VENT_M2:
  trigger:
    - RH_high
    - VPD_too_low
    - condensation_risk
  action:
    - allow_minimum_or_limited_ventilation
  penalty:
    - winter_heat_loss
```

The MPC must therefore treat ventilation as:

```text
temperature control
+
moisture removal
-
heat-loss penalty
```

not simply as a cooling actuator.

## 2.3 Screen — Light preservation priority

### SCREEN-M1 — Do not shade unnecessarily

```text
IF crop light is already limited
THEN screen deployment for shading should receive a high penalty.
```

```yaml
SCREEN_M1:
  autumn_winter:
    light_preservation_priority: high
  low_DLI_day:
    shading_penalty: very_high
```

This implements the crop-management principle:

```text
use ventilation first for removable sensible heat
before sacrificing useful crop light,
unless ventilation alone is insufficient.
```

## 2.4 Screen — Excess radiation / temperature condition

### SCREEN-M2 — Shade when ventilation alone is insufficient

```text
IF:
  radiation is excessive
  AND Tin is rising toward/above the upper reference
  AND ventilation cannot maintain climate adequately
THEN:
  allow/increase shade-screen deployment
```

Recommended structure:

```yaml
SCREEN_M2:
  inputs:
    - solar_radiation
    - Tin
    - Tref
    - vent_state
    - predicted_temperature
    - accumulated_light_or_DLI
```

## 2.5 Thermal screen — Night heat-retention logic

### SCREEN-M3 — Thermal screen closure

```text
IF solar gain becomes insufficient
AND outside temperature is low
AND heat-retention benefit exceeds light benefit
THEN close/deploy the thermal screen.
```

For thermal screens, opening/closing should ultimately depend on:

```text
solar gain
vs
greenhouse heat loss
```

rather than clock time alone.

Clock-based sunrise/sunset rules may be retained only as a fallback.

## 2.6 Morning thermal-screen opening

### SCREEN-M4 — Delay opening until useful solar gain exists

Do not automatically open the thermal screen exactly at sunrise.

```yaml
SCREEN_M4:
  conditions:
    - solar_radiation_above_low_threshold
    - outdoor_temperature_effect
    - greenhouse_heat_balance_positive_or_improving
```

Literature gives `50–150 W/m²` as a useful reference range for delayed morning opening, but this should be treated as a **design reference**, not an immediate hard threshold.

## 2.7 Humidity when thermal screen is closed

### SCREEN-M5 — Screen-first humidity relief

A practical rule found in greenhouse energy-management literature is:

```text
IF thermal screen is closed
AND humidity becomes too high
THEN first create a small controlled screen opening
before fully increasing ventilation.
```

However, this must be constrained because small screen gaps can generate strong cold-air downdrafts and spatial gradients.

```yaml
SCREEN_M5:
  action:
    - controlled_small_screen_crack
  constraints:
    - maximum_small_opening
    - minimum_dwell_time
    - monitor_Tin_and_RH_response
  fallback:
    - limited_ventilation
```

This is **not** equivalent to "always open the screen first."

## 2.8 Anti-chattering / actuator protection

### CTRL-M1 — Persistence / hysteresis / dwell

No vent or screen actuator should react to every short fluctuation.

```yaml
CTRL_M1:
  include:
    - hysteresis
    - minimum_dwell_time
    - rate_limit
    - persistence_check
```

Conceptual rule:

```text
A control condition must persist for a defined time
before a large actuator state change is accepted.
```

Exact durations should be tuned later.

## 2.9 Safety override layer

### CTRL-M2 — Hard override

The MPC must never override field safety rules.

```yaml
CTRL_M2:
  hard_overrides:
    - rain
    - excessive_wind
    - actuator_fault
    - communication_fault
    - emergency_manual_override
```

Values must come from:

```text
target farm controller
manufacturer
field operator
```

not from literature extrapolation.

---

# 3. Recommended Priority Sequence

For the target project, the first baseline priority should be:

```text
1. Safety override
2. Crop temperature protection
3. Condensation / extreme humidity protection
4. Preserve useful light
5. Reduce unnecessary heat loss
6. Reduce actuator movement
```

This is not yet the final MPC weight order, but it is the preferred control hierarchy for the first prototype.

---

# 4. Day-Phase Control Logic

## 4.1 Dawn / Morning Transition

```text
thermal screen closed overnight
        ↓
check Tin / RH / condensation risk
        ↓
check outside radiation
        ↓
if humidity excessive:
    controlled screen crack / humidity relief
        ↓
if useful solar gain becomes sufficient:
    progressively open thermal screen
        ↓
if Tin rises above reference:
    begin roof ventilation
```

Important:
- do not force simultaneous full screen opening + large vent opening;
- transition should be progressive.

## 4.2 Daytime

```text
Tin below reference
→ keep vent low
→ preserve solar gain

Tin rising
→ increase roof ventilation

Tin still rising
+ radiation excessive
+ sufficient daily light
→ deploy shading screen

humidity high
→ ventilation may be increased even if Tin is acceptable
```

Preferred control sequence for cool-season production:

```text
ventilation
→ evaluate response
→ shading if necessary
```

not:

```text
high solar
→ immediately close screen
```

## 4.3 Evening

```text
solar radiation decreases
        ↓
ventilation demand decreases
        ↓
evaluate thermal benefit of screen closure
        ↓
progressively close thermal screen
        ↓
monitor RH rise
```

Do not close the screen without checking humidity trajectory.

## 4.4 Night

```text
thermal screen mostly/fully closed
        ↓
monitor Tin / RH / VPD
        ↓
if humidity risk increases:
    small controlled screen opening
    or minimum ventilation
        ↓
avoid unnecessary heat loss
```

---

# 5. Vent–Screen Interaction Rules

The two actuators must not be treated as independent.

## 5.1 Internal screen reduces ventilation effectiveness

```text
screen deployment
→ lower internal air speed
→ reduced roof-vent effectiveness
→ stronger vertical/spatial gradients possible
```

```yaml
vent_effectiveness:
  function_of:
    - roof_vent_opening
    - screen_deployment
    - wind_speed
    - wind_direction
```

Future MPC model should avoid:

```math
Vdot = f(u_vent)
```

and prefer:

```math
Vdot = f(u_vent, u_screen, wind, DeltaT)
```

## 5.2 Screen changes both radiation and thermal loss

A screen is not only a light actuator.

```text
screen deployment
→ solar transmission changes
→ convective/radiative heat loss changes
→ humidity dynamics change
```

```yaml
screen_effect:
  radiation: true
  heat_loss: true
  airflow: true
  humidity_indirectly: true
```

---

# 6. Control Logic References for Later Design

These are useful but are **not mandatory in MPC v1**.

## 6.1 FAO simplified ventilation requirement

Reference equation:

```math
V_a = 0.0003 * tau * R_s,o,max / DeltaT
```

where:

```yaml
Va:
  meaning: ventilation_flow_per_greenhouse_area
tau:
  meaning: greenhouse_solar_transmission
Rs_o_max:
  meaning: maximum_outside_solar_radiation
DeltaT:
  meaning: greenhouse_minus_outside_air_temperature
```

Use:
- sanity check for ventilation demand,
- not the final natural-ventilation model.

## 6.2 Bailey heat-loss coefficient

```math
U = alpha + beta * w
```

Thermal screen effect:

```math
U_screened = (1 - delta) * U
```

where:

```yaml
w: wind_speed
delta: fractional_heat_loss_reduction_due_to_screen
```

Potential future use:
- thermal-screen energy term,
- winter screen benefit estimation.

Do not adopt Bailey's coefficients directly.

## 6.3 Bailey screen economic/biophysical switching concept

Concept:

```text
close screen
IF value_of_energy_saved > value_of_crop_light_lost
```

Project translation:

```math
J_screen =
w_heat * predicted_heat_loss
+
w_light * predicted_light_loss
```

This is a strong conceptual basis for MPC screen cost design.

## 6.4 Liu screen timing concept

Thermal screen should open when:

```text
solar/roof energy gain > heat loss
```

and close when the heat-retention benefit becomes dominant.

Project translation:

```text
screen timing
= f(solar radiation, Tin - Tout, time-of-day)
```

Use logic only.

Do not transfer:
- Chinese solar greenhouse wall model,
- front-roof geometry,
- fitted empirical coefficients.

## 6.5 Jung predictive ventilation concept

Jung et al. predicts:

```text
inside temperature after 30 min
```

and adjusts six window openings in the range:

```text
0–100%
```

to reduce target-temperature prediction error.

Relevant MPC concept:

```math
J_T = (T_pred - T_ref)^2
```

Useful later for:
- prediction horizon discussion,
- vent movement optimization,
- comparison with current P-band logic.

## 6.6 Hahn anti-chattering reference

Hahn's screen controller used practical persistence logic such as:

```text
same-direction response repeated within 15 min
or
state maintained for 15 min
```

before control actions.

Project translation:

```yaml
anti_chatter:
  persistence_time: configurable
  minimum_dwell_time: configurable
  contradictory_signal_cancellation: optional
```

Do not copy 15 min automatically.

---

# 7. Humidity / Thermal-Screen Interaction — Strong Caution

Campen et al. provides an important warning.

The conventional method:

```text
high RH under thermal screen
→ slightly open thermal screen
```

can remove moisture, but small gaps may create strong cold-air downdrafts.

Their modeled case used approximately:

```text
2.5% screen opening
```

and produced large spatial temperature gradients.

Therefore in this project:

```yaml
small_screen_opening_for_humidity:
  allowed: yes
  type: controlled_fallback
  not_default_solution: true

  required_monitoring:
    - Tin
    - RH
    - spatial_variability_if_available

  future_constraint:
    - limit_opening_rate
    - limit_opening_fraction
    - minimum_dwell
```

This logic is especially relevant for night and early morning.

---

# 8. Minimum Baseline Rule Controller

Before MPC, create a simple rule controller for comparison.

```yaml
baseline_controller:

  roof_vent:
    if_Tin_above_Tref:
      action: proportional_opening

    if_RH_high_or_condensation_risk:
      action: allow_minimum_ventilation

    if_rain_or_high_wind:
      action: safety_override

  shade_screen:
    if_low_light_or_low_DLI:
      action: open_preserve_light

    if_high_solar_and_Tin_rising_and_vent_insufficient:
      action: deploy_progressively

  thermal_screen:
    night:
      action: close_for_heat_retention

    morning:
      action: delay_open_until_useful_solar_gain

    high_humidity_when_closed:
      action: small_controlled_opening_before_large_vent_action
```

This baseline will later be used against:

```text
existing farm rule
vs
literature baseline
vs
MPC recommendation
```

---

# 9. MPC Translation

The logic above should not be coded only as if-statements.

Translate them into:

```yaml
MPC_translation:

  references:
    - Tref
    - VPD_or_RH_band
    - light_target
    - DLI_target

  soft_constraints:
    - temperature_band
    - humidity_or_VPD_band

  hard_constraints:
    - actuator_limits
    - safety_overrides

  penalties:
    - temperature_error
    - humidity_risk
    - light_loss
    - heat_loss
    - actuator_movement
    - excessive_screen_vent_conflict
```

Conceptual cost:

```math
J =
wT * temperature_error
+ wH * humidity_risk
+ wL * light_loss
+ wQ * heat_loss
+ wV * delta_vent^2
+ wS * delta_screen^2
```

Exact weights are intentionally not defined yet.

---

# 10. Control-State Machine Reference

Useful for implementation around MPC:

```text
STATE 1 — NIGHT_INSULATION
screen closed
vent minimal

STATE 2 — DAWN_HUMIDITY_RELIEF
screen small opening if needed
vent limited

STATE 3 — MORNING_SOLAR_GAIN
screen opening progressively
vent initially low

STATE 4 — DAY_VENTILATION
roof vent primary cooling

STATE 5 — DAY_SHADE_ASSIST
ventilation insufficient
→ screen assists cooling

STATE 6 — EVENING_TRANSITION
vent decreases
screen closes progressively

STATE 7 — SAFETY_OVERRIDE
rain / wind / fault
```

The state machine is not the MPC itself.
It is a supervisory layer that constrains what the MPC is allowed to do.

---

# 11. Values That Must NOT Be Hard-Coded Yet

```yaml
do_not_hardcode:

  - thermal_screen_opening_at_50_to_150_W_m2
  - Hahn_15_min_persistence
  - Campen_2_5_percent_screen_crack
  - Bailey_heat_loss_coefficients
  - Liu_empirical_screen_formula
  - Jung_30_min_prediction_horizon
  - generic_rain_or_wind_thresholds
```

Use them as:

```text
initial design references
→ sensitivity analysis
→ target-site calibration
```

---

# 12. Field Parameters Required Later

```yaml
field_required:

  roof_vent:
    - opening_percent_to_angle
    - opening_percent_to_effective_area
    - maximum_safe_wind
    - rain_override_logic
    - actuator_speed
    - minimum_step
    - full_open_close_time

  screen:
    - screen_type
    - shade_vs_thermal_function
    - transmittance
    - deployment_semantics
    - actuator_speed
    - minimum_step
    - physical_gap_behavior

  sensors:
    - indoor_temperature
    - indoor_RH
    - outdoor_temperature
    - solar_radiation
    - wind_speed
    - wind_direction
    - rain_state
```

---

# 13. Stage-2 Control Logic Completion Status

```yaml
control_logic_completion:

  roof_vent_temperature_logic: 0.90
  roof_vent_humidity_logic: 0.80
  screen_light_logic: 0.90
  thermal_screen_timing_logic: 0.90
  screen_humidity_interaction: 0.85
  anti_chattering_logic: 0.85
  vent_screen_interaction: 0.75
  site_specific_safety_logic: 0.30
```

Interpretation:

```text
The conceptual control logic is sufficiently mature
to proceed with MPC skeleton design.

Remaining uncertainty is mainly:
- target-site actuator mapping
- screen type/specification
- safety limits
- calibrated ventilation effectiveness
```

---

# 14. Next Design Step

Proceed to:

```text
Stage 2-1:
finalize x / u / d / y

Stage 2-2:
define prediction model equations

Stage 2-3:
define reference scheduler

Stage 2-4:
convert control logic into:
constraints + objective terms + supervisory rules
```

Recommended first control vector:

```yaml
u:
  - roof_vent_opening_percent
  - screen_opening_or_deployment_percent
```

Recommended preliminary state:

```yaml
x:
  - indoor_air_temperature
  - indoor_humidity_state
```

Recommended disturbances:

```yaml
d:
  - outdoor_temperature
  - outdoor_humidity
  - solar_radiation
  - wind_speed
  - wind_direction
  - rain_state
```

---

# 15. Final Design Rule

```text
Literature control logic
→ baseline supervisory rules

Physics/model equations
→ prediction model

Crop references
→ setpoint scheduler

MPC
→ optimized actuator trajectory

Field data
→ calibration + validation
```

Do not merge these four layers into one controller.



---

# Appendix C — Source-to-Module Mapping

| Source | `reference_scheduler` | `thermal` | `moisture` | `ventilation` | `screen` | `radiation` | `supervisor` | `mpc` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1997 Korean report | △ | ✅ structure | ✅ structure | △ | △ | △ | ✅ structure | ❌ direct |
| de Jong 1990 | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | △ | ❌ |
| Agronomy ventilation review | ❌ | △ | ❌ | ✅ | ❌ | ❌ | △ | ❌ |
| Kittas 2008 | ❌ | ❌ | △ | ✅ evidence | ✅ interaction | ❌ | ✅ interaction | ❌ |
| FAO 2013 | ✅ | △ | ✅ logic | ✅ logic | ✅ logic | ❌ | ✅ | △ |
| Bailey 1988 | △ | ✅ | ❌ | ❌ | ✅ | △ | ✅ | ✅ cost idea |
| Liu 2023 | △ | ✅ context | ❌ | ❌ | ✅ timing | ✅ solar context | ✅ | ❌ |
| Campen 2009 | ❌ | △ | ✅ | ✅ dehumidification | ✅ gap behavior | ❌ | ✅ | △ |
| Jung 2020 | ❌ | ❌ | ❌ | ✅ control architecture | ❌ | ❌ | △ | ✅ architecture |
| Su & Xu 2022 | ✅ architecture | ✅ structure | ✅ structure | ✅ rules | ✅ rules | △ | ✅ | ✅ architecture |
| Hahn 2011 | ❌ | ❌ | ❌ | ❌ | ✅ | △ | ✅ anti-chatter | △ |
| Zhang 2020 radiation | ❌ | △ | ❌ | ❌ | △ | ✅ | ❌ | △ |
| Field guides | ✅ PRIMARY | ❌ | ✅ constraints | ✅ timing | ✅ timing | ✅ target context | ✅ | ✅ references |

Legend:
- `✅` direct reference value/logic source
- `△` supporting/context only
- `❌` not used for that module

---

# Appendix D — Minimum Configuration Example

```yaml
project:
  crop: cherry_tomato
  mode: recommendation_only
  timezone: Asia/Seoul

control:
  sample_minutes: 5
  prediction_horizon_minutes: 60
  control_horizon_minutes: 20
  status: provisional_design_candidate

state:
  use_temperature: true
  use_humidity_ratio: true

actuators:
  roof_vent:
    min_percent: 0
    max_percent: 100
    rate_limit_percent_per_step: null

  screen:
    min_percent: 0
    max_percent: 100
    semantics: 100_open_retracted_0_deployed
    rate_limit_percent_per_step: null

references:
  crop_reference_file: crop_reference.yaml
  scheduler_mode: growth_stage_plus_season

safety:
  rain_override: field_required
  wind_override: field_required

validation:
  first_mode: passive_live
  second_mode: shadow_mpc
```

The `5 / 60 / 20 min` values above are intentionally marked **provisional engineering candidates** and must not be cited as literature-derived values.
