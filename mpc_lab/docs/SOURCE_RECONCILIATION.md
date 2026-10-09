# Source Reconciliation — Baseline vs Design Prompt

Inputs (both in `markdown/`, read-only):

- **BL** = `greenhouse_mpc_integrated_design_baseline.md` — technical baseline: physics, references,
  source/equation registries, control logic. Sections cited as `BL §n`; appendices as `BL-A`, `BL-B`.
- **DP** = `claude_codex_standalone_mpc_design_prompt.md` — development specification and work order.
  Sections cited as `DP §n`.

Precedence used below:

1. User instruction for this phase: 3-input MPC (roof vent + diffuse screen + shade screen); shade
   screen = daytime shading + night heat retention; work only in `mpc_lab/`.
2. DP for structure, interfaces, folder layout and work order.
3. BL for physics, crop/climate references, control logic and provenance — including its
   `do_not_hardcode`, `unknown`, `provisional`, `field_required` labels, which DP does not override.
4. Within BL, the main body (§0–§31) over the older embedded appendices (BL-A, BL-B) when they differ.

Nothing below fixes a field value that neither document provides.

---

## 1. Conflicts and adopted resolutions

| ID | Topic | BL says | DP says | Adopted | Needs user confirmation |
|---|---|---|---|---|---|
| C-1 | Number of control inputs | One `screen_opening_percent` (BL §3, §15, §16.1, §23, BL-A §8/§14, BL-B §14, BL-D) | Three: `u_vent`, `u_diffuse`, `u_shade` (DP §2.2) | **Three inputs.** BL "screen" content is mapped by role: shading → `u_shade` (day), thermal screen → `u_shade` (night), diffuse → `u_diffuse` (see `CONTROL_LOGIC.md` §2) | No (user instruction) |
| C-2 | Diffuse-screen night / humidity role | December guide uses the diffuse screen sunset−2 h → sunrise+2 h when Tout < 15 °C, and "close diffuse screen if appropriate" when daytime absolute humidity < 8 g/kg (BL §4.5, BL-A §2, §6, §17.3) | Night insulation role: `assume: false` unless field-verified (DP §8.1); conservative diffuse control (DP §12) | **DP default** (no assumed insulation/humidity role). The guide rules are retained as `field_guide_reference` and excluded from the baseline rule controller until verified | **Yes** — is the target-site diffuse screen used at night / for humidity retention? (OD-2) |
| C-3 | Winter temperature numbers | Ranges: minimum [13, 14] °C, 24 h mean ≥ [17, 18] °C (BL §4.1, §4.5) | Single values: minimum 14, mean 18 (DP §7) | **Both kept:** BL range as the reference band, DP value as the initial working point (status `field_guide_baseline`) | No |
| C-4 | Rain vent limit 5 % | Main body: reference only, not a structural limit, in `do_not_hardcode` (BL §16.4, §27); BL-A table calls it "hard/override candidate" | `safety.rain.vent_max_percent: null` (DP §25) | **Not a hard limit.** Safety value stays `null / field_required`; 5 % kept as `field_guide_reference` for the baseline rule controller comparison only | No |
| C-5 | Communication fault | `fallback: existing_farm_rule_or_safe_state` (BL §16.4) | `action: recommendation_unavailable` (DP §25) | **Equivalent in recommendation-only mode:** MPC emits no recommendation; the existing farm controller keeps operating | No |
| C-6 | Module layout | `greenhouse_mpc/` with `estimation/`, `data/`, scheduler inside `control/` (BL §24) | `mpc_lab/src/greenhouse_mpc/` with `scheduler/`, `solver/`, `simulation/` (DP §27) | **DP §27 layout.** BL `estimation/psychrometrics` → `psychrometrics.py`; BL `data/` adapters and `state_estimator` are deferred to the live-data phase | No |
| C-7 | Objective movement terms | `wV·Σ(Δvent)² + wS·Σ(Δscreen)²` (BL §15) | separate `w_v`, `w_d`, `w_s` (DP §5) | **Three movement weights.** BL-B §9 "excessive_screen_vent_conflict" penalty kept as an optional, disabled term | No |
| C-8 | Screen airflow modifier | `Vdot_eff = Vdot_vent·f_screen_airflow(u_screen)` (BL §9.4) | `Vdot_vent·f_diffuse(u_diffuse)·f_shade(u_shade)` (DP §20) | **DP form**, two independent provisional modifiers; neither may be fixed at 1 permanently (BL §9.4) | No |
| C-9 | Screen term in the energy balance | `+ Q_screen_thermal` (BL §7.1) | `+ Q_screen_insulation` (DP §17) | **Represented as a reduction of the cover loss** `U_eff = (1 − δ)·U` (BL §9.2 structure), not as a positive heat source | No |
| C-10 | Parameter status vocabulary | `status ∈ {literature_baseline, field_guide_baseline, provisional, calibrated, field_verified, unknown}`; `source_type` includes `temporary_test_fixture` (BL §19, BL §17.15) | `status: temporary_test_fixture, verified: false` (DP §33) | **BL schema** (`status` + `source_type`) **plus DP's `verified` flag**. A test value is `source_type: temporary_test_fixture, status: provisional, verified: false` | No |
| C-11 | Priority ordering vs December priorities | Supervisor order: safety → temperature → condensation → light → heat loss → movement (BL §5, BL-B §3) ; December interpretation ranks heat loss above light (BL-A §17.3) | Same supervisor order (DP §9) | **Supervisor order is fixed** (admissibility). Seasonal emphasis (e.g., December heat loss) is expressed through scheduler weight modifiers, not by reordering the supervisor | No |
| C-12 | Temperature reference meaning | 24 h mean targets (18–20, 20–21, ≥17–18 °C) **and** December vent-opening temperature schedule (19 / 26–27 / 16.5 / 16 °C) (BL §4.5, BL-A §17.3) | `Tin > dynamic Tref → increase ventilation` (DP §10); scheduler outputs `Tref` (DP Phase 2.4) | **Kept as two different scheduler outputs:** `T_ref` (crop climate target) and `T_vent_threshold` (operational vent-opening temperature from the field guide). How a 24 h-mean target becomes an instantaneous `T_ref(t)` profile is **not defined by either document** | **Yes** (OD-3) |
| C-13 | Light reference location / sensor | 600–700 W/m² "as written"; sensor definition must be verified (BL-A §18.8) | `instantaneous_radiation_reference_W_m2: [600, 700]` (DP §7) | Kept as `field_guide_baseline` with `measurement_basis: unknown` (outside vs crop level, global vs PAR) | **Yes** (OD-4) |
| C-14 | DLI output | No universal W/m² ↔ PPFD conversion without stated assumptions (BL-A §18.8) | Output `DLI_accumulated_mol_m2_d` (DP §4) | Output kept in the contract; value is `None` with status `blocked:conversion_basis_unknown` until the sensor basis and conversion are defined | **Yes** (OD-4) |

## 2. Gaps (not contradictions) that block or limit the design

| ID | Gap | Effect | Status |
|---|---|---|---|
| G-1 | Site has **two roof-vent channels** (left / right, independent; known from the dashboard project's Growlink sample). Both documents define a single `u_vent` | Scalar `u_vent` must be mapped to two field channels | **Open decision OD-1** |
| G-2 | Outdoor RH is **not** in the current Growlink sample (outside: temperature, radiation, wind speed, wind direction text, accumulated radiation, rain text) | `VP_out` (required disturbance; former `Xi_out`, DP §3) cannot be computed from live data; with DP §25 `missing_sensor → do_not_optimize`, the MPC cannot run on current live data | `field_required` |
| G-3 | Rain is a text field; wind direction is text such as `"45° 북동"` | Adapter parsing needed (future live-data phase) | design note |
| G-4 | Crop transpiration model `E_crop`: DP §18 allows a "simplified model" but neither document specifies one | Moisture model cannot be completed without choosing one | **Open decision OD-5** |
| G-5 | Solar-to-air heat conversion (`Q_solar` from `I_eff`) has no coefficient in either document | Thermal model needs an absorbed-solar factor | `unknown`, calibration item |
| G-6 | Atmospheric pressure for psychrometrics is not given | Needed for VP ↔ X_air (PSY-03) | A-8: measured or explicitly configured, no fixed value (equation baseline §2.3) |
| G-7 | Side vents, vertical curtains, boiler and fans exist in the field data but are outside the control scope | Their effect is unmodelled disturbance | Logged as `Q_other` / unmodelled; documented in `MODEL_ASSUMPTIONS.md` |
| G-8 | Target transplant timing: BL says mid/late September; the October guide assumes late-August transplant | Month-only scheduling would misplace the growth stage | Scheduler uses growth stage + month (BL-A §17.4) |

## 3. Open decisions for the user

| ID | Decision | Options visible in the sources | Default until decided |
|---|---|---|---|
| OD-1 | How `u_vent` relates to the left/right vent channels | (a) one common command for both; (b) extend `u` to 4 inputs; (c) MPC on mean opening, supervisor splits by wind side | (a), marked provisional |
| OD-2 | Diffuse screen night/humidity role at the target site | DP default "no"; December guide "yes" | No role (C-2) |
| OD-3 | Instantaneous `T_ref(t)` from 24 h-mean targets | Not specified in either document | Scheduler outputs the band and leaves `T_ref(t)` shape `unknown` (no invented profile) |
| OD-4 | Radiation sensor basis and DLI conversion | Not specified; sensor type unknown | `measurement_basis: unknown`, DLI `None` |
| OD-5 | Simplified crop transpiration model | Not specified | Interface only; `E_crop` `unknown` |
| OD-6 | Rain handling while the field rule is unknown | BL/DP: field_required | Supervisor marks vent recommendation unavailable when `rain_state` is wet (conservative, no numeric limit) — needs confirmation |

## 4. User decisions (2026-10-04)

| ID | Decision | Effect |
|---|---|---|
| OD-1 | **Keep default**: one common `u_vent` command for the left and right vent channels | Status `provisional`; unchanged |
| OD-2 | **Follow the field guide**: the diffuse screen is used at night (December window sunset −2 h → sunrise +2 h when `T_out` < 15 °C) and for daytime humidity retention ("close diffuse screen if daytime absolute humidity < 8 g/kg") | Supersedes the DP §8.1 default for this site (C-2). Diffuse-screen night/humidity rules enter the scheduler and baseline rule controller. Its thermal effect `delta_diffuse` is no longer assumed 0: it becomes `unknown` (A-6 revised) |
| OD-4 | **Sensor = global (all-wave solar) radiation in W/m²**, most likely the radiation **reaching the screens** (i.e., measured below the cover, above the screens) | `measurement_basis: global_shortwave`, `measurement_location: screen_level_inside` (`provisional` — "probably"). Radiation V1 then does **not** apply `tau_cover` to the sensor value. DLI stays blocked: global → PAR conversion is still not given by the sources (C-14) |
| OD-5 | Crop transpiration model will be added after domain-knowledge review; **skip for now** | `E_crop` stays an interface placeholder; moisture model completeness is deferred |
| OD-3 | Not decided | `T_ref(t)` shape remains `unknown` |
| OD-6 | Not decided | Default policy (vent recommendation unavailable while raining) remains provisional |

## 5. User decisions (2026-10-05)

| Item | Decision | Effect |
|---|---|---|
| Screen transmittance | Keep operator-reported values (shade 0.25, diffuse 0.80) as provisional | Superseded on 2026-10-06 (§6) |

## 6. User decisions (2026-10-06)

| Item | Decision | Effect |
|---|---|---|
| Equation baseline | `greenhouse_mpc_final_equation_baseline.md` is the equation source of truth | `ARCHITECTURE.md` and `MODEL_ASSUMPTIONS.md` updated; former BL/DP equation registry superseded |
| Humidity state | Dynamic moisture state is `VP_air` (Vanthoor Eq. 8.10); `Xi` → derived `X_air` (PSY-03) | Replaces the `Xi_in` state of DP §2.1 |
| Screen transmittance 0.25 / 0.80 | **Not used in physics.** Kept as `provisional / unverified` metadata (`greenhouse.yaml` → `unverified_reference_values`); physics τ/ρ stay `null` (`field_required`) until manufacturer or measured data | Screen optical properties return to the stop list (DP §33, EQ §21) |

## 7. Field corrections (2026-10-07)

| Item | Correction | Effect |
|---|---|---|
| Radiation sensor location | Mounted **above the cover outside**, at the rear (X23) end of S01; supersedes OD-4 "screen level, below the cover" | `greenhouse.yaml` `sensor_location: above_cover_outside`; the sensor reads outside global radiation |
| Roof vent full opening | 100–120° between the vertical ridge post and the opened leaf (110° chosen); supersedes 100 % = 90° | Dashboard geometry derives about 40.5° leaf rotation; linearity still unverified |
| Footprint notch | The 9 m front notch is at S01–S02, not S03–S04 as drawn | Dashboard geometry mirrored; floor area unchanged |
| Screens | Shade and diffuse screens each run out from both gutters and meet at the span centre | Dashboard geometry: two halves per span per layer |

## 8. Field data received (operator report 2026-10-07)

| Item | Value | Effect |
|---|---|---|
| Screen channels | 차광커튼1 = 10 % 'Ultra' (diffuse layer, 4.55 m); 차광커튼2 = 70 % aluminium (shade layer, 4.8 m, night thermal screen) | Mapping reversed from the earlier provisional one; unverified optical metadata now 0.90 / 0.30 (not used in physics) |
| Atmospheric pressure, outdoor RH | Not measured | G-2 remains blocking (VP_out); P_atm must be configured (A-8) |
| Radiation sensor | Global shortwave, above the cover outside | See §7 |
| Leaf / floor temperature sensors | None | T_can, T_flr have no measurement (Q-7, structural decision pending) |
| Cover thickness | 0.15 mm PO film | Candidate h_roof (Eq. 8.19) |
| Heating | Hot-water boiler | Q-9 narrowed: distribution type still needed |
| Rain rule | Roof vents close | `safety.rain.vent_max_percent = 0` (provisional, operator report) |
| Transplant date | 2026-09-22 | `crop_reference.transplant_date` |

Open data gap unchanged: outdoor RH (G-2).
