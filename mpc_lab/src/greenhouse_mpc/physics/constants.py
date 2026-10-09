"""Universal physical constants (equation baseline §0 rule 5: may be used directly).

Only universal/defined constants live here. Equation-specific literal coefficients (Magnus 6.112,
17.67, 243.5; the 0.622 of PSY-03; 6.4e-9 of Eq. 8.43) stay inside the function that reproduces
the source equation, so the source form remains visible.

Thermophysical air/water properties (c_p,Air, Delta_H, gamma, rho_Air) are NOT here: they are state-
or condition-dependent and are supplied through ``structures.ThermophysicalProperties``.
"""

SIGMA = 5.670374419e-8      # Stefan-Boltzmann constant [W m-2 K-4], CODATA 2018
R_GAS = 8.314462618         # universal gas constant [J mol-1 K-1], exact (SI 2019)
M_WATER = 18.01528e-3       # molar mass of water [kg mol-1]
G = 9.80665                 # standard gravitational acceleration [m s-2], defined value
KELVIN_OFFSET = 273.15      # degC -> K offset, as written in Vanthoor (T + 273.15) [K]
