"""Discrete-time map x_{k+1} = F(x_k, u_k, d[t_k, t_k+1]) and multi-interval propagation.

One control interval (target 300 s, from controller.yaml ``sampling_minutes``):
  1. u_k is held constant (ZOH) over [t_k, t_k + dt].
  2. d(t) inside the interval comes from the disturbance signal (ZOH default, linear option).
  3. dx/dt = ClimateODE.derivatives(t, x, u_k, d(t)) is integrated with the chosen integrator; the
     integrator's internal steps are independent of dt.
  4. The end state is the next discrete state; derived humidity variables are computed from it.
Each interval restarts from the previous end state, so the MPC can re-anchor on a measurement.
"""

from dataclasses import dataclass

from ..physics import psychrometrics as psy
from ..physics._validation import PhysicsInputError, positive
from ..physics.structures import ClimateState, ControlInput
from .integrators import integrate_interval
from .signals import ZeroOrderHoldControl


@dataclass(frozen=True)
class DerivedHumidity:
    """Derived psychrometric outputs (PSY-02..05) of one state. Not states."""
    RH_air: float          # [%]
    X_air: float | None    # [kg water / kg dry air]; None when P_atm is not supplied
    VPD_air: float         # [Pa]
    T_dew_air: float | None  # [degC]; None when VP_air == 0 (dew point undefined)


def derived_humidity(state, P_atm_Pa=None):
    return DerivedHumidity(
        RH_air=psy.vp_to_rh(state.VP_air, state.T_air),
        X_air=None if P_atm_Pa is None else psy.vp_to_humidity_ratio(state.VP_air, P_atm_Pa),
        VPD_air=psy.vpd(state.T_air, state.VP_air),
        T_dew_air=psy.dew_point(state.VP_air) if state.VP_air > 0 else None,
    )


@dataclass(frozen=True)
class StepResult:
    t_start: float
    t_end: float
    control: ControlInput
    state_start: ClimateState
    state_end: ClimateState
    t_internal: tuple
    n_rhs_evaluations: int


def step(model, state, control, t_start, interval_s, weather_signal, settings):
    """One control interval: returns StepResult with the next state (no clamping)."""
    interval_s = positive("interval_s", interval_s)
    if not isinstance(state, ClimateState) or not isinstance(control, ControlInput):
        raise PhysicsInputError("state must be ClimateState and control ControlInput")
    t_end = t_start + interval_s
    u = ZeroOrderHoldControl(control)
    d = weather_signal.for_interval(t_start, t_end)

    def rhs(t, x):
        return model.derivatives(t, ClimateState(T_air=x[0], VP_air=x[1]), u(t), d(t))

    result = integrate_interval(rhs, (state.T_air, state.VP_air), t_start, t_end, settings)
    end = ClimateState(T_air=result.x_end[0], VP_air=result.x_end[1])
    return StepResult(t_start, t_end, control, state, end, result.t_internal, result.n_rhs_evaluations)


@dataclass(frozen=True)
class Trajectory:
    times_s: tuple             # t_0 .. t_N
    states: tuple              # ClimateState at t_0 .. t_N
    controls: tuple            # u_0 .. u_{N-1}
    steps: tuple               # StepResult per interval

    def derived(self, P_atm_Pa=None):
        return tuple(derived_humidity(s, P_atm_Pa) for s in self.states)


def propagate(model, initial_state, controls, t_start, interval_s, weather_signal, settings):
    """Apply ``step`` for each control in sequence (open-loop prediction over len(controls) intervals)."""
    controls = tuple(controls)
    if not controls:
        raise PhysicsInputError("at least one control interval is required")
    state, t = initial_state, t_start
    times, states, steps = [t], [state], []
    for control in controls:
        result = step(model, state, control, t, interval_s, weather_signal, settings)
        steps.append(result)
        state, t = result.state_end, result.t_end
        times.append(t)
        states.append(state)
    return Trajectory(tuple(times), tuple(states), controls, tuple(steps))
