# Scope Revision (2026-10-12)

Decision by the user, for the project deadline: the temperature/humidity physics MPC with actuation is
**out of the current scope**. The project delivers **GHI-forecast-based control recommendations** plus a
richer web interface on the 3D digital twin.

## 1. In scope

| Item | Basis (existing) | New work |
|---|---|---|
| Live field data in the 3D twin | field collector, `field_collector` live source | field PC setup (waiting for the operator) |
| GHI forecast 5–60 min | XGBoost + CC, weekly update, `/api/forecast/ghi/` | forecast chart in the UI |
| Screen recommendation (shade + diffuse) | forecast, screen transmittances (provisional 0.30 / 0.90), radiation_v1 crop-plane grid | recommendation logic (rule-based or light-only optimisation, user choice), API, UI card with reasons |
| Roof-vent guidance | live indoor temperature, CONTROL_LOGIC.md §3/§7 rules | rule-based, reactive (no thermal prediction); coupled to screen timing, see §3 |
| Extra information | QC flags, DLI, evaluation results | sensor-health alerts, DLI today/forecast, model-performance panel, recommendation-vs-actual log |
| Demo without field link | 2026-07-28 – 10-09 exports | replay mode feeding the same live pipeline |

## 2. Out of scope (kept, not deleted)

- Vanthoor-based T/VP prediction model (`physics/`, `dynamics/`), open questions Q-1..Q-13 — future work.
- CasADi temperature/humidity MPC, actuation of any device (recommendation only, `mode: recommendation_only`).
- Claims about control performance; only forecast accuracy (measured) and recommendation logs are reported.

## 3. Screen–vent coupling handled without a thermal model

Screens and roof vents interact (CONTROL_LOGIC.md §5): deployed screens reduce vent effectiveness; full
screen opening together with a large vent opening is avoided in the morning (§3, BL-B §4.1). Without a
thermal model this is handled by the supervisor state machine and rules (CONTROL_LOGIC.md §3, §7):

| Coupling | How (simplified) | Uses the forecast |
|---|---|---|
| Morning: retract screen before large vent opening | sequence rule in `MORNING_SOLAR_GAIN` | timing of the solar rise |
| Midday: shade only when venting is not enough | vent already high **and** measured T_in above threshold **and** forecast GHI stays high | persistence of high GHI over the next 15–30 min |
| Passing clouds | hold the screen position when a drop/rise is forecast within 10–15 min (anti-chatter) | 5–15 min forecast (best skill) |
| Evening: vents down, screen closing | `EVENING_TRANSITION` with RH check | timing of the solar fall |
| Rain / strong wind | close vents (safety override), live `status` 감우/강풍 | — |
| Vent effect under a deployed screen | shown as a qualitative warning only (airflow factor unknown) | — |

Needed from the field: vent temperature threshold, shade radiation threshold, RH limits, actuator travel
times, the existing controller's rules (for the recommendation-vs-actual comparison).
