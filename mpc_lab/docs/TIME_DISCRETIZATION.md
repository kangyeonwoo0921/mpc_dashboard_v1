# Time Discretization / Numerical Propagation (DISC-01)

The continuous-time model of `greenhouse_mpc_final_equation_baseline.md` (EQ) is unchanged. This
layer (`src/greenhouse_mpc/dynamics/`) only turns it into a discrete map for MPC prediction:

```text
x_{k+1} = F(x_k, u_k, d[t_k, t_k + Δt]),   x = [T_air (°C), VP_air (Pa)],   Δt = control interval (target 300 s)
```

No physics equation is added, simplified or corrected; no state is clamped. EQ §0 rule 7 and §22
item 9: the method below is a numerical implementation decision, not a literature-derived equation.

## 1. Model properties that drive the choice

| Property | Consequence |
|---|---|
| Nonlinear RHS (Eq. 8.45 VP/(T+273.15), Eq. 8.65 square root, Eq. 8.38 T⁴, Eq. 8.48–8.49) | linear/exact discretization not available |
| Exchange time constants ≈ capacity / exchange coefficient (e.g. `cap_Air / HEC`, `cap_VPAir` vs. ventilation and transpiration coefficients) can be **shorter than 300 s** depending on still-unknown parameters | potentially stiff at the control interval; explicit single step can be unstable |
| Switching terms (Eq. 8.43 condensation on/off, Eq. 8.71 wind branch) | RHS not smooth; adaptive step control helps |
| Only 2 states | implicit methods are cheap (2×2 Newton systems) |
| Future MPC | needs a reliable reference map now; may later need a fixed, differentiable map |

## 2. Candidates and choice

| Method | Pros | Cons | Fit |
|---|---|---|---|
| Forward Euler, one step of 300 s | trivial, differentiable | 1st order; unstable if Δt > 2τ | rejected as default |
| Fixed-step RK4 with substeps | 4th order, fixed cost, easy to embed in MPC (CasADi, multiple shooting) | explicit: stability needs h·|λ| ≲ 2.785; substep count must be justified | **secondary** (`rk4`) |
| Adaptive explicit RK45 | error control | very small steps if stiff | not selected |
| **Adaptive implicit Radau IIA (order 5)** | L-stable (robust to stiffness and switching), error-controlled internal steps, no step size in code | more work per step (negligible for 2 states); adaptive step makes F only piecewise smooth in u | **default** (`radau`) |

Selected: **Radau** as the default propagator and accuracy reference; **RK4** available for later MPC
formulations, with its substep count chosen from `stability_diagnostic` and then verified against
Radau. Implementation: `scipy.integrate.solve_ivp(method="Radau")`; RK4 in-house.

## 3. Interval convention

- **Control `u`:** zero-order hold over `[t_k, t_k + Δt]` (`ZeroOrderHoldControl`).
- **Disturbances `d`:** sampled `WeatherInput` records at known times.
  - `ZeroOrderHoldWeather` (default): the sample valid at `t_k` is held for the whole interval
    (the next sample is not used even when the integrator evaluates at `t_k + Δt`).
  - `LinearInterpolationWeather` (option): `T_out`, `VP_out`, `wind_speed`, `solar_radiation`
    interpolated linearly; `wind_direction` and `rain` held (angle / categorical).
  - No extrapolation: an interval outside the sample range raises an error.
- **Internal step vs control interval:** separate. Radau chooses internal steps from `rtol`,
  `atol_T_air`, `atol_VP_air`; RK4 uses `n_substeps`. No step size is hard-coded.
- **Re-anchoring:** each interval starts from the given state, so the MPC can restart from the
  latest measurement each cycle.
- **Derived outputs:** `RH_air`, `X_air` (needs `P_atm`), `VPD_air`, `T_dew_air` are computed from the
  propagated state (PSY-02..05); they are never integrated.

## 4. Failure handling (no clamping)

A physics domain error inside an interval (e.g. Eq. 8.65 negative radicand, temperature below
absolute zero after divergence) or a solver failure raises `IntegrationError` with time and state.
Missing parameters raise `MissingParameterError` unchanged.

## 5. Numerical parameters still to decide

| Parameter | Where | Basis to decide |
|---|---|---|
| `rtol`, `atol_T_air` [K], `atol_VP_air` [Pa] | `controller.yaml` → `numerical_integration` (null) | well below sensor resolution (T sensor, RH sensor via PSY-02) |
| `rk4_n_substeps` | same (null) | `stability_diagnostic` with calibrated parameters, then accuracy check vs Radau |
| disturbance hold (ZOH / linear) | same (ZOH, provisional) | weather data resolution and forecast format |
| control interval | `horizons.sampling_minutes` = 5 (provisional) | MPC design |

## 6. Interfaces for the MPC

```python
ClimateODE(activation, flux_providers, cap_air, cap_VP_air)   # f(t, x, u, d)
step(model, state, control, t_start, interval_s, weather_signal, settings) -> StepResult
propagate(model, x0, [u_0 … u_{N-1}], t_start, interval_s, weather_signal, settings) -> Trajectory
derived_humidity(state, P_atm_Pa) -> DerivedHumidity
stability_diagnostic(rhs, t, x, interval_s)                   # RK4 substep basis
```

Still needed before a real prediction can run: flux providers for the active terms (`H_can_air`,
`R_glob_sun_air`, `H_air_flr`, `H_air_out`, `MV_can_air`, `MV_air_out`) built from the source
functions once their closures are resolved (Q-6, Q-7, Q-12), `cap_Air` / `cap_VPAir` (Q-8), the field
% → U mapping (Q-1), the site parameters, and the numerical settings above.
