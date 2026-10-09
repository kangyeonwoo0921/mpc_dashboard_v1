# Control Logic — Roles, Supervisor, Baseline Rules (Phase 2.1)

Sources: BL (`greenhouse_mpc_integrated_design_baseline.md`) §5, §6, §10, §13, §16, §18, BL-B; DP
(`claude_codex_standalone_mpc_design_prompt.md`) §8–§15, §24–§25, §30. Conflicts: `SOURCE_RECONCILIATION.md`.

Literature thresholds listed here are **design references**, not hard-coded values (BL §27, BL-B §11).
Every numeric value carries its status from `MODEL_ASSUMPTIONS.md`.

---

## 1. Control hierarchy (fixed)

```text
1 safety
2 crop temperature protection
3 condensation / extreme humidity protection
4 preserve useful light
5 reduce heat loss
6 reduce actuator movement
```

(BL §5, BL-B §3, DP §9.) Seasonal emphasis (e.g., December heat-loss priority, BL-A §17.3) changes
**weights** through the scheduler, never this order (C-11).

---

## 2. Actuator roles

### 2.1 Literature → project mapping (DP §8.2, BL-B header rule)

```yaml
literature_mapping:
  thermal_screen:
    project_actuator: shade_screen
    usage: [night_insulation, dawn_opening, humidity_relief_logic]
    confidence: provisional
  shading_screen:
    project_actuator: shade_screen
    usage: [daytime_shading]
  diffuse_screen:
    project_actuator: diffuse_screen
  aluminum_thermal_screen (December guide):
    project_actuator: shade_screen        # site shade screen is aluminium and doubles as night screen
    confidence: provisional
```

`thermal screen`, `shade screen` and `diffuse screen` are not the same device (BL-B). Literature
thermal-screen logic is **not** automatically applicable to `u_diffuse` (DP §2.2).

### 2.2 Roof vent `u_vent`

| Function | Logic | Source |
|---|---|---|
| Cooling | `T_in > T_ref` → increase opening, modified by `T_out`, wind speed/direction, solar, predicted cooling effectiveness | VENT-M1 (BL §5.1, BL-B §2.1, DP §10) |
| Moisture removal | RH high / VPD low / condensation risk → minimum or limited ventilation even with small cooling demand, against winter heat-loss cost | VENT-M2 (BL §5.1, BL-B §2.2, DP §10) |
| Safety | rain, excessive wind, actuator/communication fault → field override | VENT-M3 (BL §5.1); values `field_required` |

Ventilation = temperature control + moisture removal − heat-loss penalty, not only cooling (BL-B §2.2).
Two field channels (left/right) vs one `u_vent`: OD-1 (default common command, provisional).

### 2.3 Shade screen `u_shade` — two roles

| Period | Role | Logic | Source |
|---|---|---|---|
| Day | shading | Keep retracted when light is limited (SHADE-M1). Deploy progressively only when radiation is excessive **and** `T_in` rises toward/above the upper reference **and** ventilation is predicted insufficient (SHADE-M2) | BL §5.2, BL-B §2.3–2.4, DP §11 |
| Evening | insulation onset | Solar gain falling → evaluate heat-retention benefit vs light → progressive closure, checking humidity trajectory | BL-B §2.5, §4.3; DP §13 |
| Night | heat retention | Low/no solar and low `T_out` → deploy for heat retention (THERMAL-M1); field-guide closure ≈ 80 % "when needed" kept as `field_guide_baseline` | BL §5.3, BL §4.3–4.4, DP §13 |
| Dawn | delayed opening | Check RH/condensation → check useful solar gain → progressive retraction (THERMAL-M2, SCREEN-M4). Decide on solar gain + `T_in − T_out` + humidity, not sunrise alone. FAO 50–150 W/m² is a design reference, not a threshold | BL §5.3, §10.1–10.2, BL-B §2.6, DP §13 |
| Night humidity | relief | First option: controlled small screen crack, with max opening change and dwell configurable, observe predicted humidity response; fallback: limited roof ventilation (THERMAL-M3, SCREEN-M5). Small gaps can cause cold downdrafts and gradients — controlled fallback, not default; Campen 2.5 % not hard-coded | BL §5.3, §10.3, BL-B §2.7, §7; DP §14 |

Clock rules (December aluminium screen sunset −1 h → sunrise +0.5 h) are kept only as fallback /
comparison baseline (BL-B §2.5).

### 2.4 Diffuse screen `u_diffuse` — conservative separate actuator

```yaml
diffuse_screen_control:
  mode: conservative                       # DP §12
  objectives: [improve_light_distribution, moderate_excess_direct_radiation]
  default_policy: {preserve_light: true}
  MPC_status:
    include_as_control_input: true
    strong_penalty_on_unnecessary_movement: true
  night_use: field_guide                   # OD-2 decided 2026-10-04: follow the December guide
  humidity_retention_role: field_guide     # OD-2: close when daytime absolute humidity < 8 g/kg
  enable_diffuse_screen_control: true      # false → held at its measured position, rest of MPC unchanged
```

Field-guide diffuse-screen rules adopted for this site (OD-2):

- Night: deploy sunset −2 h → sunrise +2 h when `T_out` < 15 °C (December guide; `field_guide_baseline`).
  Clock window is the baseline/fallback; the MPC treats it through the scheduler and admissible sets.
- Day humidity: if daytime absolute humidity < 8 g/kg → close (deploy) the diffuse screen if appropriate,
  with roof vent minimized (December guide).
- Its thermal effect `delta_diffuse` is `unknown` (no value in the sources).

---

## 3. Day-phase state machine (supervisor)

Restricts admissible MPC actions; does not replace the MPC (BL §6, BL-B §10).

| State | Entry (qualitative) | Admissible-set restriction |
|---|---|---|
| `NIGHT_INSULATION` | no useful solar, low `T_out` | `u_shade` mostly deployed; `u_vent` minimal; `u_diffuse` deployed in the guide window when `T_out` < 15 °C (OD-2) |
| `DAWN_HUMIDITY_RELIEF` | shade deployed, humidity risk high | `u_shade` small crack allowed (bounded change); limited `u_vent` if needed |
| `MORNING_SOLAR_GAIN` | useful solar gain rising | progressive `u_shade` retraction; large `u_vent` delayed until needed; no simultaneous full screen opening + large vent opening (BL-B §4.1) |
| `DAY_VENTILATION` | daytime | `u_vent` primary cooling; `u_shade` deployment allowed only via SHADE-M2 conditions |
| `DAY_SHADE_ASSIST` | vent insufficient + radiation high | progressive `u_shade` deployment |
| `EVENING_TRANSITION` | solar falling | `u_vent` decreasing; `u_shade` progressive closure with RH check |
| `SAFETY_OVERRIDE` | rain / wind / fault | highest priority; field rule applies |

Entry thresholds are `unknown`/`provisional`; the qualitative conditions above come from the sources,
numbers do not.

---

## 4. Supervisor rules (pre- and post-optimization)

```yaml
safety:                              # DP §25, BL §16.4 — no fake values
  rain:
    vent_max_percent: null           # field_required; 5 % field-guide rule is reference only (C-4)
    policy_while_unknown: vent_recommendation_unavailable   # OD-6, provisional
  wind:
    maximum_safe_speed_m_s: null     # field_required
  actuator_fault: {action: safe_state_from_field_controller}
  communication_failure: {action: recommendation_unavailable}  # existing farm controller continues (C-5)
  missing_sensor: {action: do_not_optimize}
  manual_override: {action: respect_field_state}

bounds:
  roof_vent_percent: [0, 100]
  diffuse_screen_open_percent: [0, 100]
  shade_screen_open_percent: [0, 100]

actuator_protection:                 # DP §15, BL-B §2.8 — values null until field speeds known
  roof_vent:      {minimum_dwell_time_s: null, maximum_rate_percent_per_step: null, movement_penalty: configurable}
  diffuse_screen: {minimum_dwell_time_s: null, maximum_rate_percent_per_step: null, movement_penalty: configurable}
  shade_screen:   {minimum_dwell_time_s: null, maximum_rate_percent_per_step: null, movement_penalty: configurable}
  persistence_time_s: null           # Hahn 15 min not hard-coded
  contradictory_signal_filter: true

input_validation:
  invalid_percent: validation_error  # DP §31
```

Critical sensors for optimization (missing → no recommendation): indoor temperature and RH (→ `T_air`,
`VP_air`), `T_out`, outdoor RH (→ `VP_out`), solar, wind speed, wind direction, rain state, current actuator positions. With current
live data, outdoor RH is absent (G-2), so live optimization is gated until it is provided.

Post-filter order: clip to bounds → apply rate/dwell (when configured) → re-apply safety → record
`overrides_applied` and `active_constraints`.

---

## 5. Vent–screen interaction (inputs to the model, not rules)

- Deployed screens reduce internal airflow and roof-vent effectiveness:
  `Vdot = f(u_vent, u_diffuse, u_shade, wind, ΔT)`, never `f(u_vent)` alone (BL-B §5.1, DP §20).
- Screens change radiation, heat loss, airflow and indirectly humidity (BL-B §5.2).
- Cool-season default preference: ventilate first, predict response, shade only if needed; may be
  overridden by excessive radiation, very high `T_in`, insufficient vent authority, safety restriction
  (BL §13.2).

---

## 6. MPC translation

| Logic | Becomes |
|---|---|
| `T_ref` tracking | `w_T Σ(T − T_ref)²` |
| VPD / RH band | band penalty, near zero inside 0.5–1.2 kPa (BL §15.2); night RH 90 % risk soft constraint |
| SHADE-M1 light preservation | light-loss term `w_L`, scaled by `screen_shading_penalty_multiplier` (higher with low DLI / autumn–winter) |
| VENT-M2 vs heat loss | `w_Q Σ Q_vent`, `Q_vent = ρ c_p Vdot (T_in − T_out)`, scaled by `vent_heat_loss_penalty_multiplier` (reduced when condensation risk is high, BL-A §18.10) |
| Bailey energy-vs-light screen switching | `w_heat · heat_loss + w_light · light_loss` (BL-B §6.3) |
| Anti-chatter | `w_v Σ(Δu_vent)² + w_d Σ(Δu_diffuse)² + w_s Σ(Δu_shade)²` plus supervisor dwell |
| Safety, bounds, day-phase restrictions | hard constraints from the supervisor |
| Screen/vent conflict | optional term, disabled by default (BL-B §9) |

Weights: configurable, no final values (DP §5, BL-B §9).

---

## 7. Baseline rule controller (Phase 2.7 — not the final controller)

Uses the same supervisor (DP §30, BL §18, BL-B §8):

```text
T_in > T_vent_threshold                → proportional roof-vent opening
RH high / condensation risk             → allow minimum ventilation
vent insufficient + solar excessive     → progressive shade-screen deployment
low winter light / low DLI              → keep shade screen retracted (preserve light)
night, cold                             → deploy shade screen (heat retention)
dawn                                    → delayed, progressive shade-screen opening
night high RH under deployed shade      → controlled small crack, then reassess; fallback limited vent
rain / wind / fault                     → supervisor override
diffuse screen                          → guide window at night (T_out < 15 °C); deploy when day abs. humidity < 8 g/kg; otherwise conservative (OD-2)
```

Comparison framework: existing farm rule vs this baseline vs MPC (BL §18).

---

## 8. Direction tests that encode this logic (DP §31, BL §25)

Higher `T_in` → vent demand not lower; higher wind at same `u_vent` → `Vdot` changes; lower winter
`T_out` → vent heat-loss penalty higher; more shade deployment → transmitted radiation lower; more
diffuse deployment → radiation model responds; low winter DLI → shading penalty higher; high RH / low
VPD → humidity-relief action possible; rain override blocks unsafe vent; missing critical sensor → no
recommendation; invalid % → validation error; rapid screen flip-flop reduced; every cycle re-anchors on
the latest measurement.
