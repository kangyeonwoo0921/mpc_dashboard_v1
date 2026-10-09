"""Continuous-time right-hand side f(t, x, u, d) assembled from source-equation outputs.

dT_air/dt  = Eq. 8.2  RHS / cap_Air      (balances.eq_8_2_temperature_rhs, eq_8_2_dT_air_dt)
dVP_air/dt = Eq. 8.10 RHS / cap_VPAir    (balances.eq_8_10_vapour_rhs, eq_8_10_dVP_air_dt)

Each active balance term is supplied as a *flux provider*: a callable
``provider(t, state, control, weather) -> flux`` that evaluates the term with the source functions
(e.g. Eq. 8.65 -> Eq. 8.45 for MV_air_out). Providers are not defined here because several
closures are not yet given by the equation baseline (HEC for H_air_out: Q-12; T_can: Q-7;
cap_Air / cap_VPAir: Q-8). The assembler only enforces that the provided terms match the site
component activation exactly; it never substitutes a missing term.
"""

from dataclasses import dataclass
from typing import Callable, Mapping

from ..physics import balances
from ..physics._validation import MissingParameterError, PhysicsInputError
from ..physics.structures import ClimateState, ControlInput, WeatherInput

TEMPERATURE_TERMS = balances.TEMPERATURE_GAIN_TERMS + balances.TEMPERATURE_LOSS_TERMS
MOISTURE_TERMS = balances.MOISTURE_GAIN_TERMS + balances.MOISTURE_LOSS_TERMS

FluxProvider = Callable[[float, ClimateState, ControlInput, WeatherInput], float]


@dataclass(frozen=True)
class ClimateODE:
    """f(t, x, u, d) for x = [T_air, VP_air].

    activation      site component activation (config/model_components.yaml)
    flux_providers  {term name: provider} for exactly the active terms
    cap_air         provider for cap_Air [J K-1 m-2]   (Eq. 8.2; definition Q-8)
    cap_VP_air      provider for cap_VPAir [kg m-2 Pa-1] (Eq. 8.10; definition Q-8)
    Capacities are providers because their definition may depend on the state; that is decided by
    whoever supplies them, not here.
    """
    activation: balances.ComponentActivation
    flux_providers: Mapping[str, FluxProvider]
    cap_air: FluxProvider
    cap_VP_air: FluxProvider

    def __post_init__(self):
        provided, active = set(self.flux_providers), set(self.activation.active)
        if provided - active:
            raise PhysicsInputError(f"providers given for inactive terms {sorted(provided - active)}")
        if active - provided:
            raise MissingParameterError(f"active terms without a flux provider {sorted(active - provided)}")
        for name, provider in self.flux_providers.items():
            if not callable(provider):
                raise PhysicsInputError(f"flux provider for {name} is not callable")
        if not callable(self.cap_air) or not callable(self.cap_VP_air):
            raise PhysicsInputError("cap_air and cap_VP_air must be providers")

    def _fluxes(self, names, t, state, control, weather):
        return {name: self.flux_providers[name](t, state, control, weather)
                for name in names if name in self.flux_providers}

    def derivatives(self, t, state, control, weather):
        """Return (dT_air/dt [K s-1], dVP_air/dt [Pa s-1])."""
        heat = self._fluxes(TEMPERATURE_TERMS, t, state, control, weather)
        vapour = self._fluxes(MOISTURE_TERMS, t, state, control, weather)
        rhs_T = balances.eq_8_2_temperature_rhs(self.activation, **heat)
        rhs_VP = balances.eq_8_10_vapour_rhs(self.activation, **vapour)
        return (balances.eq_8_2_dT_air_dt(rhs_T, self.cap_air(t, state, control, weather)),
                balances.eq_8_10_dVP_air_dt(rhs_VP, self.cap_VP_air(t, state, control, weather)))
