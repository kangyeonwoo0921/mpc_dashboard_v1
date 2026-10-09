"""How controls and disturbances are evaluated inside a prediction interval.

Controls: zero-order hold (ZOH) — u is constant over [t_k, t_k + dt_control). This is the MPC
sampled-control convention; the actuator command is issued once per interval.

Disturbances (sampled weather records at known times):
- ``ZeroOrderHoldWeather`` (default): the latest sample at or before t is held.
- ``LinearInterpolationWeather`` (option): continuous fields T_out, VP_out, wind_speed and
  solar_radiation are linearly interpolated between samples; wind_direction (angle) and rain
  (categorical) are held as in ZOH, because linear interpolation is not meaningful for them.
Neither scheme extrapolates: t outside the sample range raises an error. These are numerical input
reconstructions, not physics equations.
"""

import bisect
from dataclasses import dataclass

from ..physics._validation import PhysicsInputError
from ..physics.structures import ControlInput, WeatherInput

INTERPOLATED_FIELDS = ("T_out", "VP_out", "wind_speed", "solar_radiation")
HELD_FIELDS = ("wind_direction", "rain")


@dataclass(frozen=True)
class ZeroOrderHoldControl:
    control: ControlInput

    def __call__(self, t):
        return self.control


class _SampledWeather:
    def __init__(self, times_s, samples):
        times, samples = list(times_s), list(samples)
        if not times or len(times) != len(samples):
            raise PhysicsInputError("weather times and samples must be non-empty and of equal length")
        if any(b <= a for a, b in zip(times, times[1:])):
            raise PhysicsInputError("weather sample times must be strictly increasing")
        if not all(isinstance(s, WeatherInput) for s in samples):
            raise PhysicsInputError("weather samples must be WeatherInput")
        self.times, self.samples = times, samples

    def _index(self, t):
        if t < self.times[0] or t > self.times[-1]:
            raise PhysicsInputError(f"t = {t} s outside the weather sample range "
                                    f"[{self.times[0]}, {self.times[-1]}] (no extrapolation)")
        return bisect.bisect_right(self.times, t) - 1


class ZeroOrderHoldWeather(_SampledWeather):
    def __call__(self, t):
        return self.samples[self._index(t)]

    def for_interval(self, t_start, t_end):
        """Disturbance used inside [t_start, t_end]: the sample valid at t_start, held constant.
        (Avoids a switch to the next sample when the integrator evaluates exactly at t_end.)"""
        self._index(t_end)                         # the interval must lie inside the sample range
        held = self(t_start)
        return lambda t: held


class LinearInterpolationWeather(_SampledWeather):
    def for_interval(self, t_start, t_end):
        self._index(t_start), self._index(t_end)
        return self

    def __call__(self, t):
        i = self._index(t)
        if i == len(self.times) - 1 or t == self.times[i]:
            return self.samples[i]
        a, b = self.samples[i], self.samples[i + 1]
        w = (t - self.times[i]) / (self.times[i + 1] - self.times[i])
        values = {}
        for name in INTERPOLATED_FIELDS:
            va, vb = getattr(a, name), getattr(b, name)
            if va is None or vb is None:
                raise PhysicsInputError(f"cannot interpolate {name}: missing sample value")
            values[name] = va + w * (vb - va)
        for name in HELD_FIELDS:
            values[name] = getattr(a, name)
        return WeatherInput(**values)
