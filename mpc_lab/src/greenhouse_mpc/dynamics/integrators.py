"""Numerical integration of dx/dt = f(t, x) over one interval. No clamping, no correction terms.

Methods (see docs/TIME_DISCRETIZATION.md for the selection rationale):
- ``radau`` (default): adaptive implicit Radau IIA, order 5 (scipy.integrate.solve_ivp). L-stable,
  so robust if the exchange time constants are shorter than the interval (stiffness) and across the
  switching terms (Eq. 8.43, 8.71). Internal step size is chosen by the error controller from
  ``rtol`` / ``atol_*``; no step size is fixed in code.
- ``rk4``: classical fixed-step Runge-Kutta 4 with ``n_substeps`` equal substeps per interval. For
  future MPC formulations that need a fixed, differentiable map. ``n_substeps`` must be chosen
  explicitly, e.g. from ``stability_diagnostic``.

All numerical settings are required inputs (None -> MissingParameterError).
"""

import math
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from ..physics._validation import MissingParameterError, PhysicsInputError

METHODS = ("radau", "rk4")
RK4_REAL_AXIS_STABILITY_LIMIT = 2.785   # |h*lambda| bound of classical RK4 on the negative real axis


class IntegrationError(RuntimeError):
    """The integrator failed (solver failure, or a physics domain error inside the interval)."""


@dataclass(frozen=True)
class IntegratorSettings:
    method: str
    rtol: float | None = None          # radau: relative tolerance [-]
    atol_T_air: float | None = None    # radau: absolute tolerance on T_air [K]
    atol_VP_air: float | None = None   # radau: absolute tolerance on VP_air [Pa]
    n_substeps: int | None = None      # rk4: equal substeps per control interval [-]

    def __post_init__(self):
        if self.method not in METHODS:
            raise PhysicsInputError(f"method must be one of {METHODS}, got {self.method!r}")
        if self.method == "radau":
            for name in ("rtol", "atol_T_air", "atol_VP_air"):
                value = getattr(self, name)
                if value is None:
                    raise MissingParameterError(f"radau requires {name}")
                if not (isinstance(value, (int, float)) and value > 0 and math.isfinite(value)):
                    raise PhysicsInputError(f"{name} must be a positive finite number")
        if self.method == "rk4":
            if self.n_substeps is None:
                raise MissingParameterError("rk4 requires n_substeps")
            if isinstance(self.n_substeps, bool) or not isinstance(self.n_substeps, int) or self.n_substeps < 1:
                raise PhysicsInputError("n_substeps must be a positive integer")


@dataclass(frozen=True)
class IntervalResult:
    x_end: tuple                 # (T_air [degC], VP_air [Pa]) at t_end
    t_internal: tuple            # internal time points used by the integrator [s]
    x_internal: tuple            # states at those points
    n_rhs_evaluations: int


def _call(rhs, t, x):
    try:
        return np.asarray(rhs(t, (float(x[0]), float(x[1]))), dtype=float)
    except MissingParameterError:
        raise                                        # a configuration gap, not a numerical failure
    except (ValueError, ArithmeticError) as exc:     # physics domain errors are ValueError subclasses
        raise IntegrationError(f"physics evaluation failed at t = {t} s, x = {tuple(map(float, x))}: {exc}") from exc


def integrate_interval(rhs, x0, t_start, t_end, settings):
    """Integrate dx/dt = rhs(t, x) from t_start to t_end [s]. rhs returns (dT_air/dt, dVP_air/dt)."""
    if not t_end > t_start:
        raise PhysicsInputError("t_end must be greater than t_start")
    x0 = np.asarray(x0, dtype=float)
    if x0.shape != (2,) or not np.all(np.isfinite(x0)):
        raise PhysicsInputError("x0 must be finite (T_air, VP_air)")
    if settings.method == "radau":
        return _radau(rhs, x0, t_start, t_end, settings)
    return _rk4(rhs, x0, t_start, t_end, settings.n_substeps)


def _radau(rhs, x0, t_start, t_end, settings):
    count = [0]

    def f(t, x):
        count[0] += 1
        return _call(rhs, t, x)

    solution = solve_ivp(f, (t_start, t_end), x0, method="Radau", rtol=settings.rtol,
                         atol=[settings.atol_T_air, settings.atol_VP_air])
    if not solution.success:
        raise IntegrationError(f"Radau failed on [{t_start}, {t_end}] s: {solution.message}")
    states = tuple(tuple(map(float, column)) for column in solution.y.T)
    return IntervalResult(states[-1], tuple(map(float, solution.t)), states, count[0])


def _rk4(rhs, x0, t_start, t_end, n_substeps):
    h = (t_end - t_start) / n_substeps
    x, t = x0, t_start
    times, states = [t], [tuple(map(float, x))]
    for i in range(n_substeps):
        k1 = _call(rhs, t, x)
        k2 = _call(rhs, t + h / 2, x + h / 2 * k1)
        k3 = _call(rhs, t + h / 2, x + h / 2 * k2)
        k4 = _call(rhs, t + h, x + h * k3)
        x = x + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t = t_start + (i + 1) * h
        if not np.all(np.isfinite(x)):
            raise IntegrationError(f"RK4 produced a non-finite state at t = {t} s")
        times.append(t)
        states.append(tuple(map(float, x)))
    return IntervalResult(states[-1], tuple(times), tuple(states), 4 * n_substeps)


def jacobian(rhs, t, x):
    """Finite-difference Jacobian of rhs at (t, x), 2x2 [1/s, mixed units]. Central differences with
    perturbation sqrt(eps)-scaled to each state's magnitude (standard numerical choice)."""
    x = np.asarray(x, dtype=float)
    J = np.empty((2, 2))
    for j in range(2):
        delta = math.sqrt(np.finfo(float).eps) * max(1.0, abs(x[j]))
        e = np.zeros(2)
        e[j] = delta
        J[:, j] = (_call(rhs, t, x + e) - _call(rhs, t, x - e)) / (2 * delta)
    return J


def stability_diagnostic(rhs, t, x, interval_s):
    """Local stiffness check at (t, x): eigenvalues of the Jacobian, the fastest time constant, and the
    smallest RK4 substep count keeping |h*lambda| inside the real-axis stability bound. This is a
    local, linearised indicator to *inform* the choice of n_substeps; it is not a guarantee, and it
    is a stability minimum only: accuracy at that count can still be poor (|R(h*lambda)| near 1), so
    the final count must also be checked against a Radau reference."""
    eigenvalues = np.linalg.eigvals(jacobian(rhs, t, x))
    fastest = float(max(abs(eigenvalues))) if len(eigenvalues) else 0.0
    min_substeps = 1 if fastest == 0 else max(1, math.ceil(interval_s * fastest / RK4_REAL_AXIS_STABILITY_LIMIT))
    return {
        "eigenvalues_per_s": tuple(complex(v) for v in eigenvalues),
        "fastest_time_constant_s": math.inf if fastest == 0 else 1.0 / fastest,
        "rk4_min_substeps_for_stability": min_substeps,
    }
