# Greenhouse MPC Prediction Model — Final Equation Set
## Literature-faithful baseline, no ad-hoc equations

**Project:** 4-span tomato greenhouse MPC / 3D monitoring  
**Purpose:** Fix the prediction-model equations before implementation.  
**Primary reference:** Bram H. E. Vanthoor (2011), *A model-based greenhouse design method*, Chapter 8.  
**Supplementary references used only where Vanthoor is insufficient:** Cabrera et al. (2009) for direct/diffuse radiation partitioning; previously confirmed psychrometric equations; literature-supported wind-direction dependency is retained only as a parameter dependency, not as an invented analytical correction.

---

# 0. Non-negotiable modelling rule

This document deliberately does **not** create a new “project equation” by rearranging or blending published equations.

The rules are:

1. **Source equations are reproduced without changing their functional form.**
2. If the project does not contain a device that appears in a source equation, the device-specific submodel is simply **not instantiated**.  
   - We do not invent a replacement term.
   - We do not invent a coefficient equal to zero and claim it is a literature value.
3. If a relationship is missing in the literature reviewed so far, it is explicitly marked **UNRESOLVED / FIELD REQUIRED / NOT ACTIVATED**.
4. Parameter values from a different greenhouse are **not copied as if they were universal**.
5. Universal physical constants may be used directly.
6. The current field system is recommendation-only. None of the following equations authorizes a direct PLC write.
7. The final physical model is kept in **continuous-time form**, because Vanthoor’s model is continuous and was solved numerically.  
   A 5-min MPC discretization method is **not invented in this document**. It must be selected explicitly at the implementation stage.

---

# 1. Final state and signal convention

## 1.1 Dynamic states used in the source-faithful core

To avoid rewriting Vanthoor’s moisture balance into another state variable, the dynamic states of the core climate model are:

\[
x =
\begin{bmatrix}
T_{Air} \\
VP_{Air}
\end{bmatrix}
\]

where:

- \(T_{Air}\): greenhouse air temperature [°C]
- \(VP_{Air}\): greenhouse air vapour pressure [Pa]

This is a deliberate change from the earlier tentative idea of using humidity ratio \(X_i\) directly as the moisture state.

### Why \(VP_{Air}\), not \(X_i\), is selected as the dynamic moisture state

Vanthoor’s published moisture balance is written directly for \(VP_{Air}\) in Eq. (8.10).  
Converting that ODE into an \(X_i\)-state ODE would require an additional variable transformation and derivative operation that is **not given in the source**.

Therefore:

- **dynamic moisture state:** \(VP_{Air}\)
- **derived/output moisture variable:** \(X_i\) (humidity ratio)
- **measurement conversion:** RH ↔ \(VP\) ↔ \(X_i\)

This preserves the source equation exactly.

---

## 1.2 Control inputs

The project control candidates remain:

\[
u =
\begin{bmatrix}
U_{Roof} \\
U_{Diffuse} \\
U_{Shade}
\end{bmatrix}
\]

with:

- \(U_{Roof}\): roof vent control
- \(U_{Diffuse}\): diffuse-screen state/control
- \(U_{Shade}\): shade-screen control

Important source limitations:

- \(U_{Roof}\) is directly supported by Vanthoor Eq. (8.65), (8.68).
- movable shade-screen control is directly supported by Vanthoor Eq. (8.16)–(8.17).
- no literature equation has yet been secured that maps **partial movable diffuse-screen opening** continuously to direct-to-direct/direct-to-diffuse coefficients.
- therefore the diffuse-screen optical model must **not** use an invented continuous interpolation law.

---

## 1.3 Disturbances / exogenous inputs

At minimum:

\[
d =
\{
T_{Out},
VP_{Out},
v_{Wind},
\theta_{Wind},
I_{solar},
\text{rain},
t
\}
\]

Additional inputs required by specific source equations may include:

- mean air temperature \(\bar T\)
- canopy temperature \(T_{Can}\)
- LAI
- screen material optical/thermal coefficients
- greenhouse geometry
- vent dimensions and maximum vent area
- atmospheric pressure \(P_{atm}\)

No coefficient is to be guessed.

---

# 2. Psychrometric conversion block

This block is used to convert measured RH and temperature into the vapour-pressure state and humidity-ratio output.

## 2.1 Saturation vapour pressure

Previously selected Magnus-type equation:

\[
\boxed{
e_s(T)
=
6.112
\exp\left(
\frac{17.67T}{T+243.5}
\right)
}
\qquad [hPa]
\]

where \(T\) is in °C.

For Pa:

\[
\boxed{
P_{sat}(T)
=
100
\cdot
6.112
\exp\left(
\frac{17.67T}{T+243.5}
\right)
}
\qquad [Pa]
\]

The multiplication by 100 is a unit conversion only.

---

## 2.2 Relative humidity → actual vapour pressure

From the definition of relative humidity:

\[
\boxed{
RH
=
\frac{P_v}{P_{vs}}\times100
}
\]

therefore:

\[
\boxed{
P_v
=
\frac{RH}{100}P_{sat}(T)
}
\]

For indoor air:

\[
VP_{Air}
=
\frac{RH_{Air}}{100}P_{sat}(T_{Air})
\]

---

## 2.3 Vapour pressure → humidity ratio

Previously confirmed psychrometric relationship:

\[
\boxed{
X
=
0.622
\frac{P_v}{P_{atm}-P_v}
}
\]

where:

- \(X\): humidity ratio [kg water / kg dry air]
- \(P_v\): vapour pressure
- \(P_{atm}\): atmospheric pressure

Thus:

\[
\boxed{
X_i
=
0.622
\frac{VP_{Air}}
{P_{atm}-VP_{Air}}
}
\]

No fixed atmospheric-pressure value is inserted here.  
Use measured/local pressure when available, or explicitly define the pressure assumption in configuration.

---

## 2.4 Humidity ratio → vapour pressure

Algebraic inversion of the selected humidity-ratio equation:

\[
\boxed{
P_v
=
\frac{X P_{atm}}
{0.622+X}
}
\]

This is not a new empirical equation; it is the exact algebraic inverse of the previous relationship.

---

## 2.5 Vapour pressure → RH

\[
\boxed{
RH
=
100
\frac{P_v}
{P_{sat}(T)}
}
\]

---

## 2.6 Vapour pressure deficit

\[
\boxed{
VPD
=
P_{sat}(T)-P_v
}
\]

For greenhouse air:

\[
VPD_{Air}
=
P_{sat}(T_{Air})-VP_{Air}
\]

For canopy-to-air vapour pressure difference in the Vanthoor transpiration equation:

\[
VPCan - VPAir
\]

is retained exactly as used by Vanthoor.

---

## 2.7 Dew point

The dew point is obtained by algebraic inversion of the selected Magnus saturation-vapour-pressure equation.

Define:

\[
\gamma =
\ln\left(
\frac{e}{6.112}
\right)
\]

where \(e\) is actual vapour pressure in hPa.

Then:

\[
\boxed{
T_{dew}
=
\frac{243.5\gamma}
{17.67-\gamma}
}
\]

This is an algebraic inverse of the selected Magnus equation and introduces no new empirical coefficients.

---

# 3. Core temperature-state equation

## 3.1 Vanthoor Eq. (8.2) — greenhouse air temperature

**Source:** Vanthoor (2011), Chapter 8, Eq. (8.2).

\[
\boxed{
\begin{aligned}
cap_{Air}\dot T_{Air}
={}&
H_{CanAir}
+
H_{PadAir}
+
H_{MechAir}
+
H_{PipeAir}
+
H_{PasAir}
+
H_{BlowAir}
+
R_{Glob\_SunAir}
\\
&-
H_{AirFlr}
-
H_{AirThScr}
-
H_{AirOut}
-
H_{AirTop}
-
H_{AirOut\_Pad}
-
L_{AirFog}
\end{aligned}
}
\]

Unit of both sides:

\[
[W\,m^{-2}]
\]

This equation is the **authoritative top-level temperature balance**.

### Source interpretation

The terms are:

- \(H_{CanAir}\): sensible heat exchange canopy → air
- \(H_{PadAir}\): cooling-pad outlet air → greenhouse air
- \(H_{MechAir}\): mechanical cooling → greenhouse air
- \(H_{PipeAir}\): heating pipes → greenhouse air
- \(H_{PasAir}\): passive energy buffer → greenhouse air
- \(H_{BlowAir}\): direct air heater → greenhouse air
- \(R_{Glob\_SunAir}\): global radiation absorbed by construction and released to air
- \(H_{AirFlr}\): greenhouse air → floor
- \(H_{AirThScr}\): greenhouse air → thermal screen
- \(H_{AirOut}\): greenhouse air → outside air
- \(H_{AirTop}\): greenhouse air → top compartment
- \(H_{AirOut\_Pad}\): air exchange caused by pad/fan
- \(L_{AirFog}\): latent heat used by fog evaporation

### Project activation rule

The equation itself is **not rewritten**.

For the current farm:

- pad/fan cooling: not confirmed → do not instantiate until confirmed
- mechanical cooling: not confirmed → do not instantiate until confirmed
- heating pipe: do not instantiate unless field hardware/operation is confirmed
- passive buffer: not confirmed → do not instantiate
- direct air heater: not confirmed → do not instantiate
- fogging: not confirmed → do not instantiate

The physically relevant source modules expected to remain are:

- canopy ↔ air heat exchange
- air ↔ floor heat exchange
- air ↔ outdoor air through ventilation/leakage
- screen-related heat transfer if the shade screen is validated as a thermal screen
- radiation-related heat inputs

No new reduced balance is declared here, because that would be a project rewrite of Eq. (8.2).

---

# 4. Core moisture-state equation

## 4.1 Vanthoor Eq. (8.10) — greenhouse air vapour pressure

**Source:** Vanthoor (2011), Chapter 8, Eq. (8.10).

\[
\boxed{
\begin{aligned}
cap_{VPAir}\dot{VP}_{Air}
={}&
MV_{CanAir}
+
MV_{PadAir}
+
MV_{FogAir}
+
MV_{BlowAir}
\\
&-
MV_{AirThScr}
-
MV_{AirTop}
-
MV_{AirOut}
-
MV_{AirOut\_Pad}
-
MV_{AirMech}
\end{aligned}
}
\]

Unit of both sides:

\[
[kg\,m^{-2}\,s^{-1}]
\]

This is the **authoritative moisture balance**.

### Project activation rule

The balance is kept in vapour-pressure form.

Expected relevant terms:

- \(MV_{CanAir}\): crop transpiration
- \(MV_{AirOut}\): moisture transport by ventilation
- \(MV_{AirThScr}\): condensation/exchange with a screen, only if applicable to the actual screen
- condensation at other surfaces through the corresponding source equations

Device-specific fluxes for equipment not present at the site are not instantiated.

---

# 5. General sensible heat transfer equation

## 5.1 Vanthoor Eq. (8.40)

\[
\boxed{
H_{12}
=
HEC_{12}
(T_1-T_2)
}
\qquad [W\,m^{-2}]
\]

where:

- \(H_{12}\): heat flux from object/location 1 to 2
- \(HEC_{12}\): heat exchange coefficient
- \(T_1,T_2\): temperatures

This equation is used by Vanthoor for convective/conductive heat fluxes.

### Important rule

The function form is secured.  
The actual \(HEC_{12}\) coefficients must come from the relevant source equation/table or calibration.

Do not invent \(HEC\) values.

---

# 6. Long-wave radiation

## 6.1 Vanthoor Eq. (8.38)

\[
\boxed{
FIR_{ij}
=
A_i\epsilon_i\epsilon_jF_{ij}\sigma
\left[
(T_i+273.15)^4-(T_j+273.15)^4
\right]
}
\]

\[
[W\,m^{-2}]
\]

where:

- \(A_i\): surface area of object \(i\) per greenhouse floor area
- \(\epsilon_i,\epsilon_j\): thermal-infrared emission coefficients
- \(F_{ij}\): view factor
- \(\sigma\): Stefan–Boltzmann constant

This is retained if long-wave radiative exchange between canopy/floor/screen/cover/sky is represented.

---

# 7. Latent heat

## 7.1 Vanthoor Eq. (8.42)

\[
\boxed{
L_{12}
=
\Delta H\cdot MV_{12}
}
\qquad [W\,m^{-2}]
\]

where:

- \(\Delta H\): latent heat of evaporation
- \(MV_{12}\): vapour flux

No separate project-specific latent-heat equation is introduced.

---

# 8. Condensation

## 8.1 Vanthoor Eq. (8.43)

\[
\boxed{
MV_{12}
=
\begin{cases}
0,
&
VP_1 < VP_2
\\[4pt]
6.4\times 10^{-9}
HEC_{12}
(VP_1-VP_2),
&
VP_1 > VP_2
\end{cases}
}
\]

\[
[kg\,m^{-2}\,s^{-1}]
\]

where:

- \(VP_1\): vapour pressure of air at location 1
- \(VP_2\): saturated vapour pressure of object 2 at its temperature
- \(HEC_{12}\): heat-exchange coefficient

The conversion factor in the original thesis is:

\[
\boxed{6.4\times10^{-9}}
\]

not \(4.6\times10^{-9}\).

The OCR text of the PDF can misread this coefficient; the rendered original page shows \(6.4\times10^{-9}\).

### Differentiable version

Vanthoor also gives a smoothed differentiable form in Eq. (8.44):

\[
\boxed{
MV_{12}
=
\frac{1}
{1+\exp\left(s_{MV_{12}}(VP_1-VP_2)\right)}
\;
6.4\times10^{-9}
HEC_{12}(VP_1-VP_2)
}
\]

Use Eq. (8.44) only if a differentiable model is required and the switch-slope parameter is defined from the source/configuration.

Do not guess \(s_{MV_{12}}\).

---

# 9. Moisture transport by airflow

## 9.1 Vanthoor Eq. (8.45)

\[
\boxed{
MV_{12}
=
\frac{M_{Water}}{R}
f_{12}
\left(
\frac{VP_1}{T_1+273.15}
-
\frac{VP_2}{T_2+273.15}
\right)
}
\]

\[
[kg\,m^{-2}\,s^{-1}]
\]

where:

- \(f_{12}\): air flux [m³ m⁻² s⁻¹]
- \(M_{Water}\): molar mass of water
- \(R\): universal gas constant
- \(VP_1,VP_2\): vapour pressures
- \(T_1,T_2\): temperatures [°C]

Vanthoor explicitly applies this general form to:

- greenhouse air ↔ top compartment
- greenhouse air ↔ outside
- top compartment ↔ outside

with the corresponding airflow terms.

For our roof-vent-dominant system, this equation directly supplies the moisture flux associated with the selected ventilation airflow model.

---

# 10. Crop transpiration

## 10.1 Vanthoor Eq. (8.47)

\[
\boxed{
MV_{CanAir}
=
VEC_{CanAir}
(VP_{Can}-VP_{Air})
}
\]

\[
[kg\,m^{-2}\,s^{-1}]
\]

where \(VP_{Can}\) is the saturated vapour pressure at canopy temperature.

---

## 10.2 Vanthoor Eq. (8.48)

\[
\boxed{
VEC_{CanAir}
=
\frac{
2\rho_{Air}c_{p,Air}LAI
}{
\Delta H\,\gamma\,(r_b+r_s)
}
}
\]

\[
[kg\,m^{-2}\,Pa^{-1}\,s^{-1}]
\]

where:

- \(\rho_{Air}\): greenhouse-air density
- \(c_{p,Air}\): specific heat capacity of greenhouse air
- \(LAI\): leaf area index
- \(\Delta H\): latent heat of evaporation
- \(\gamma\): psychrometric constant
- \(r_b\): canopy boundary-layer resistance
- \(r_s\): canopy stomatal resistance

---

## 10.3 Vanthoor Eq. (8.49)

Vanthoor defines canopy stomatal resistance as:

\[
\boxed{
r_s
=
r_{s,min}
\cdot
rf(R_{Can})
\cdot
rf(CO_{2,Air})
\cdot
rf(VP_{Can}-VP_{Air})
}
\]

The detailed resistance-factor functions are provided in Vanthoor Eq. (8.50).

### Project decision

For a first implementation, do **not** replace this with an invented simplified transpiration coefficient.

If the complete Stanghellini/Vanthoor resistance submodel is postponed:

- keep \(MV_{CanAir}\) as an explicitly unresolved model term, or
- use a separately validated published transpiration model.

Do not silently replace Eq. (8.47)–(8.50) with an arbitrary constant.

---

# 11. Natural ventilation through roof vents

## 11.1 Vanthoor Eq. (8.65), based on Boulard & Baille (1995)

For roof ventilation:

\[
\boxed{
f''_{VentRoof}
=
\frac{
U_{Roof}A_{Roof}C_d
}{
2A_{Flr}
}
\sqrt{
\frac{
g h_{Vent}
}{
2
}
\frac{
T_{Air}-T_{Out}
}{
\bar{T}+273.15
}
+
C_w v_{Wind}^{2}
}
}
\]

\[
[m^3\,m^{-2}\,s^{-1}]
\]

where:

- \(U_{Roof}\): roof-vent aperture control
- \(A_{Roof}\): maximum roof-vent area
- \(A_{Flr}\): greenhouse floor area
- \(C_d\): discharge coefficient
- \(g\): gravitational acceleration
- \(h_{Vent}\): vertical dimension of one vent opening
- \(T_{Air},T_{Out}\): greenhouse/outdoor temperature
- \(\bar T\): mean greenhouse/outdoor air temperature
- \(C_w\): global wind-pressure coefficient
- \(v_{Wind}\): wind speed

This equation directly contains:

- vent opening
- buoyancy / temperature difference
- wind-speed effect

No different roof-vent formula is introduced.

---

## 11.2 Vent aperture

Vanthoor Eq. (8.68):

\[
\boxed{
A_{Roof}^{U}
=
U_{Roof}A_{Roof}
}
\qquad [m^2]
\]

This relation is consistent with the aperture-control variable used in Eq. (8.65).

---

# 12. Greenhouse leakage / infiltration

## 12.1 Vanthoor Eq. (8.71)

Vanthoor includes greenhouse leakage as a wind-speed-dependent airflow:

\[
\boxed{
f_{leakage}
=
\begin{cases}
c_{leakage},
&
v_{Wind}<0.25
\\[4pt]
c_{leakage}v_{Wind},
&
v_{Wind}\ge 0.25
\end{cases}
}
\]

\[
[m^3\,m^{-2}\,s^{-1}]
\]

where \(c_{leakage}\) depends on greenhouse type.

### Project decision

The equation is valid as a source candidate.

However:

\[
c_{leakage} = \text{FIELD/CALIBRATION REQUIRED}
\]

No literature coefficient from a different greenhouse is copied automatically.

---

# 13. Wind direction

## 13.1 What is secured

The literature reviewed confirms that greenhouse ventilation and pressure coefficients vary with wind direction.

## 13.2 What is not secured

Vanthoor Eq. (8.65) does **not** contain an explicit wind-direction angle.

No universal published equation of the form

\[
C_w=f(\theta)
\]

has yet been selected and validated for the present 4-span greenhouse geometry.

## 13.3 Final no-invention decision

Therefore this document does **not** multiply Eq. (8.65) by an invented cosine term, empirical modifier, or fabricated interpolation function.

Instead:

\[
\boxed{
C_w = \text{angle/geometry-dependent parameter to be supplied from literature data or calibration}
}
\]

If a wind-direction lookup table is later adopted, the table values must come from a cited wind-pressure/ventilation study and must retain its geometry and angle definition.

Until then:

- Eq. (8.65) remains unchanged.
- wind direction is stored as an exogenous input for future coefficient selection.
- no analytical \(f_\theta\) is invented.

---

# 14. Shade-screen optical model

The movable shade-screen optical model is directly available in Vanthoor.

## 14.1 Two-layer transmission, Vanthoor Eq. (8.14)

\[
\boxed{
\tau_{12}
=
\frac{\tau_1\tau_2}
{1-\rho_1\rho_2}
}
\]

---

## 14.2 Two-layer reflection, Vanthoor Eq. (8.15)

\[
\boxed{
\rho_{12}
=
\rho_1
+
\frac{\tau_1^2\rho_2}
{1-\rho_1\rho_2}
}
\]

These are based on the EN 410 double-layer formulation used by Vanthoor.

---

## 14.3 Movable shade screen + semi-permanent shade layer, Vanthoor Eq. (8.16)

\[
\boxed{
\tau_{ShScr\_ShScrPerPAR}
=
\frac{
\left(1-U_{ShScr}(1-\tau_{ShScrPAR})\right)
\left(1-U_{ShScrPer}(1-\tau_{ShScrPerPAR})\right)
}{
1-
U_{ShScr}\rho_{ShScrPAR}
U_{ShScrPer}\rho_{ShScrPerPAR}
}
}
\]

---

## 14.4 Reflection, Vanthoor Eq. (8.17)

\[
\boxed{
\rho_{ShScr\_ShScrPerPAR}
=
U_{ShScr}\rho_{ShScrPAR}
+
\frac{
\left(1-U_{ShScr}(1-\tau_{ShScrPAR})\right)^2
U_{ShScrPer}\rho_{ShScrPerPAR}
}{
1-
U_{ShScr}\rho_{ShScrPAR}
U_{ShScrPer}\rho_{ShScrPerPAR}
}
}
\]

Vanthoor states that NIR optical properties are calculated similarly.

### Project decision

These equations are the selected source equations for the **shade screen’s opening/control-dependent optical effect**.

Required material parameters:

- \(\tau_{ShScrPAR}\)
- \(\rho_{ShScrPAR}\)
- corresponding NIR/FIR properties if those wavebands are represented

These parameters must come from:

1. manufacturer data,
2. direct measurement, or
3. a clearly matched material source.

No generic shade-screen transmittance is inserted.

---

# 15. Shade screen as night insulation / thermal screen

The actual field shade screen is also used as a practical heat-retention screen at night.

Vanthoor separates “shading screen” and “thermal screen” as physical design elements.  
Therefore using Vanthoor’s thermal-screen equations for the field shade screen is a **hardware-role mapping**, not proof that the field material has the same coefficients.

The following equations may be activated only when the actual shade-screen material’s thermal properties are available.

---

## 15.1 FIR transmission of thermal screen — Vanthoor Eq. (8.39)

\[
\boxed{
\tau_{ThScrTIR}^{U}
=
1-U_{ThScr}(1-\tau_{ThScrTIR})
}
\]

No thermal-screen coefficient is guessed.

---

## 15.2 Airflow through thermal screen — Vanthoor Eq. (8.41)

\[
\boxed{
\begin{aligned}
f_{ThScr}
={}&
U_{ThScr}K_{ThScr}
|T_{Air}-T_{Out}|^{0.66}
\\
&+
\frac{1-U_{ThScr}}
{\rho_{Air}^{Mean}}
\left[
0.5\rho_{Air}^{Mean}
(1-U_{ThScr})
g
|\rho_{Air}-\rho_{Out}|
\right]^{0.5}
\end{aligned}
}
\]

\[
[m^3\,m^{-2}\,s^{-1}]
\]

where \(K_{ThScr}\) is the screen-flux coefficient determining screen permeability.

### Project decision

This equation is **not automatically assigned** to the actual shade screen.

Activation requirements:

- actual screen material confirmed to serve as a thermal/energy screen
- \(K_{ThScr}\) available or calibrated
- thermal/FIR properties available

Otherwise this submodel stays disabled.

---

# 16. Cover conduction / heat loss

## 16.1 Vanthoor Eq. (8.19)

For the lumped cover, Vanthoor gives:

\[
\boxed{
HEC_{Cov,in\,Cov,e}
=
\frac{1}{
\dfrac{h_{Rf}}{\lambda_{Rf}}
+
\dfrac{
U_{ShScrPer}h_{ShScrPer}
}{
\lambda_{ShScrPer}
}
}
}
\]

\[
[W\,m^{-2}\,K^{-1}]
\]

where:

- \(h_{Rf}\): roof thickness
- \(\lambda_{Rf}\): roof thermal conductivity
- \(h_{ShScrPer}\): semi-permanent shading-screen thickness
- \(\lambda_{ShScrPer}\): corresponding thermal conductivity

### Project applicability

Use only for matching layer architecture.

The present greenhouse construction must be mapped to actual cover layers before activation.

Do not copy a semi-permanent-screen layer into the current greenhouse if it does not exist.

---

# 17. Diffuse-screen optical physics

The missing direct/diffuse radiation partitioning is supplied by:

**Cabrera, F.J., Baille, A., López, J.C., González-Real, M.M., Pérez-Parra, J. (2009).  
“Effects of cover diffusive properties on the components of greenhouse solar radiation.”  
Biosystems Engineering 103, 344–356.**

Important limitation: the tested material is a **highly diffusing greenhouse cover film**, not a movable diffuse screen.

Therefore these equations provide **diffusive-material optics**, not a continuous screen-opening law.

---

## 17.1 Direct-to-direct transmittance

Cabrera definition:

\[
\boxed{
\tau_{b-b}
=
\frac{I_i}{I_o}
}
\]

where:

- \(I_o\): outside direct radiation
- \(I_i\): inside direct radiation

---

## 17.2 Direct radiation converted into diffuse radiation

Cabrera Eq. (6):

\[
\boxed{
D^*
=
D_i-\tau_dD_o
}
\]

where:

- \(D_o\): outside diffuse radiation
- \(D_i\): total inside diffuse radiation
- \(\tau_d\): diffuse transmittance determined under overcast conditions
- \(D^*\): direct radiation converted into diffuse radiation

---

## 17.3 Direct-to-diffuse transmittance

Cabrera Eq. (7):

\[
\boxed{
\tau_{b-d}
=
\frac{D^*}{I_o}
=
\frac{D_i-\tau_dD_o}{I_o}
}
\]

---

## 17.4 Total direct transmittance

Cabrera Eq. (8):

\[
\boxed{
\tau_b
=
\tau_{b-b}
+
\tau_{b-d}
}
\]

---

## 17.5 Diffuse-ratio relation

Cabrera defines:

\[
\rho
=
\frac{D_i}{D_o}
\]

and reports an empirical power relationship for their specific greenhouse/material.

**Do not use Cabrera’s fitted coefficients as field coefficients for the present diffuse screen.**

---

## 17.6 Final diffuse-screen implementation restriction

No reviewed source directly provides:

\[
U_{Diffuse}
\rightarrow
\tau_{b-b},\tau_{b-d},\tau_d
\]

for a partially opened **movable diffuse screen**.

Therefore:

- no linear interpolation is introduced,
- no custom opening-dependent transmission formula is introduced,
- no Cabrera fitted coefficient is transferred to the current screen.

For V1, the source-faithful optical model may only use Cabrera-type coefficients when a physical screen state/material characterization exists.

Intermediate opening behaviour remains:

\[
\boxed{\text{UNRESOLVED / FIELD OR MANUFACTURER CHARACTERIZATION REQUIRED}}
\]

---

# 18. Solar-radiation interface with the existing 3D ray model

The project already has an upstream solar-position / 3D ray-tracing module.

This document does **not** replace that module with an invented radiation equation.

Vanthoor’s temperature/canopy balances accept radiation fluxes such as:

- \(R_{PAR\_SunCan}\)
- \(R_{NIR\_SunCan}\)
- \(R_{Glob\_SunAir}\)

The existing ray model may provide the radiative inputs to those physical terms, provided:

1. units are consistent,
2. direct/diffuse treatment is documented,
3. shade-screen optical equations are source-based,
4. diffuse-screen effects are not interpolated using an invented law.

The 3D ray module is therefore treated as an **upstream radiation-input module**, not as a modification of Vanthoor’s state equations.

---

# 19. Final model architecture

The final source-faithful prediction pipeline is:

```text
Measured / weather inputs
        │
        ├── T, RH
        │      │
        │      └── psychrometric equations
        │              ├── VP
        │              ├── Xi
        │              ├── VPD
        │              └── dew point
        │
        ├── solar position / radiation
        │      │
        │      └── existing 3D ray model
        │              ├── shade-screen optics: Vanthoor 8.14–8.17
        │              └── diffuse optics: Cabrera 6–8
        │                  (no invented partial-opening law)
        │
        └── wind / outdoor climate
               │
               └── roof ventilation: Vanthoor 8.65
                       ├── vent control
                       ├── buoyancy
                       ├── wind speed
                       └── Cw angle dependence reserved;
                           no invented wind-direction function
                                │
                                ▼
                    airflow fVentRoof
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
     sensible heat flux      vapour transport
       Vanthoor 8.40          Vanthoor 8.45
              │                     │
              └──────────┬──────────┘
                         ▼
               climate-state ODEs
             Vanthoor 8.2 and 8.10
                         │
                         ▼
               predicted TAir, VPAir
                         │
                         ▼
               RH, Xi, VPD, dew point
```

---

# 20. Final selected equation registry

| ID | Purpose | Source | Equation | Status |
|---|---|---|---|---|
| PSY-01 | Saturation vapour pressure | previously selected Magnus relation | Magnus \(e_s(T)\) | FIXED |
| PSY-02 | RH ↔ vapour pressure | psychrometric definition | \(RH=100P_v/P_{sat}\) | FIXED |
| PSY-03 | humidity ratio | previously confirmed psychrometric relation | \(X=0.622P_v/(P_{atm}-P_v)\) | FIXED |
| PSY-04 | VPD | vapour-pressure definition | \(P_{sat}-P_v\) | FIXED |
| PSY-05 | dew point | algebraic inverse of PSY-01 | Magnus inverse | FIXED |
| TEMP-01 | greenhouse air T balance | Vanthoor 2011 | Eq. 8.2 | FIXED |
| HUM-01 | greenhouse air vapour balance | Vanthoor 2011 | Eq. 8.10 | FIXED |
| HEAT-01 | convection/conduction | Vanthoor 2011 | Eq. 8.40 | FIXED |
| FIR-01 | long-wave exchange | Vanthoor 2011 | Eq. 8.38 | FIXED |
| LAT-01 | latent heat | Vanthoor 2011 | Eq. 8.42 | FIXED |
| COND-01 | condensation | Vanthoor 2011 | Eq. 8.43 | FIXED |
| COND-02 | differentiable condensation | Vanthoor 2011 | Eq. 8.44 | OPTIONAL |
| MV-01 | moisture carried by airflow | Vanthoor 2011 | Eq. 8.45 | FIXED |
| CROP-01 | canopy transpiration | Vanthoor 2011 | Eq. 8.47 | FIXED |
| CROP-02 | canopy vapour-exchange coefficient | Vanthoor 2011 / Stanghellini | Eq. 8.48 | FIXED |
| CROP-03 | stomatal resistance structure | Vanthoor 2011 | Eq. 8.49–8.50 | FIXED / PARAMS REQUIRED |
| VENT-01 | roof natural ventilation | Vanthoor 2011 / Boulard & Baille | Eq. 8.65 | FIXED |
| VENT-02 | roof aperture | Vanthoor 2011 | Eq. 8.68 | FIXED |
| LEAK-01 | leakage | Vanthoor 2011 | Eq. 8.71 | FIXED / CALIBRATION REQUIRED |
| WINDDIR-01 | wind-direction dependency | literature evidence | no universal closed form selected | UNRESOLVED FUNCTION |
| SHADE-01 | double-layer optics | Vanthoor 2011 | Eq. 8.14–8.15 | FIXED |
| SHADE-02 | movable shade optical control | Vanthoor 2011 | Eq. 8.16–8.17 | FIXED |
| THERMAL-01 | thermal-screen FIR | Vanthoor 2011 | Eq. 8.39 | CONDITIONAL |
| THERMAL-02 | thermal-screen airflow | Vanthoor 2011 | Eq. 8.41 | CONDITIONAL |
| COVER-01 | cover conduction coefficient | Vanthoor 2011 | Eq. 8.19 | CONDITIONAL TO LAYER MATCH |
| DIFF-01 | direct→direct optics | Cabrera 2009 | \(\tau_{b-b}=I_i/I_o\) | FIXED PHYSICS |
| DIFF-02 | direct→diffuse optics | Cabrera 2009 | Eq. 6–7 | FIXED PHYSICS |
| DIFF-03 | total direct transmittance | Cabrera 2009 | Eq. 8 | FIXED PHYSICS |
| DIFF-OPEN | movable diffuse screen partial opening | not secured | — | **DO NOT INVENT** |
| DISC-01 | 5-min discretization | not fixed by selected literature | — | IMPLEMENTATION DECISION LATER |

---

# 21. Parameters that must remain blank until verified

The following should **not** receive guessed values:

```yaml
greenhouse:
  A_Flr: field_required
  A_Roof: field_required
  h_Vent: field_required
  cover_layer_thickness: field_required
  cover_thermal_conductivity: manufacturer_or_calibration

ventilation:
  C_d: calibration_or_geometry_matched_source
  C_w: calibration_or_geometry_matched_source
  c_leakage: calibration_required
  wind_direction_table: literature_or_calibration_required

shade_screen:
  tau_PAR: manufacturer_or_measurement
  rho_PAR: manufacturer_or_measurement
  tau_NIR: manufacturer_or_measurement
  rho_NIR: manufacturer_or_measurement
  tau_TIR: manufacturer_or_measurement_if_used_as_thermal_screen
  K_ThScr: calibration_required_if_thermal_airflow_model_activated

diffuse_screen:
  tau_bb: manufacturer_or_measurement
  tau_bd: manufacturer_or_measurement
  tau_d: manufacturer_or_measurement
  partial_opening_relation: unresolved

crop:
  LAI: measurement_or_crop_schedule
  r_b: source_or_calibration
  r_s_min: source_or_calibration
  stomatal_model_parameters: source_or_calibration
```

---

# 22. Things explicitly excluded from the final equation set

The following must **not** enter the implementation unless a new cited source is added:

1. An arbitrary linear interpolation between open and closed diffuse-screen optical coefficients.
2. A cosine/sine wind-direction multiplier invented for \(C_w\).
3. A generic “screen efficiency” multiplier without a cited definition.
4. A guessed shade-screen thermal resistance.
5. A guessed infiltration/ACH constant.
6. A guessed crop transpiration coefficient replacing Vanthoor/Stanghellini.
7. A custom reduced heat balance that is presented as if it were Vanthoor Eq. (8.2).
8. A custom reduced moisture balance presented as if it were Vanthoor Eq. (8.10).
9. A 5-min Euler equation presented as literature-derived when no selected source has been fixed for that discretization.
10. Coefficients copied from a greenhouse with a different geometry/material without an explicit calibration label.

---

# 23. Implementation policy

For coding, equations should be represented as source-owned modules rather than one hand-written merged equation.

Recommended module boundaries:

```text
psychrometrics.py
  saturation_vapor_pressure()
  rh_to_vp()
  vp_to_rh()
  vp_to_humidity_ratio()
  humidity_ratio_to_vp()
  vpd()
  dew_point()

vanthoor_temperature.py
  eq_8_2_temperature_balance()

vanthoor_moisture.py
  eq_8_10_vapour_balance()
  eq_8_43_condensation()
  eq_8_45_airflow_vapour_flux()
  eq_8_47_transpiration()

vanthoor_heat.py
  eq_8_38_fir_flux()
  eq_8_40_heat_flux()
  eq_8_42_latent_heat()

vanthoor_ventilation.py
  eq_8_65_roof_ventilation()
  eq_8_68_roof_aperture()
  eq_8_71_leakage()

vanthoor_screens.py
  eq_8_14_double_layer_tau()
  eq_8_15_double_layer_rho()
  eq_8_16_shade_tau()
  eq_8_17_shade_rho()
  eq_8_39_thermal_screen_fir()
  eq_8_41_thermal_screen_airflow()

cabrera_diffuse_optics.py
  direct_to_direct()
  direct_to_diffuse()
  total_direct_transmittance()

radiation_adapter.py
  # data interface only
  # no invented optical law
  ray_model_output_to_source_flux_inputs()
```

Each function should carry a docstring containing:

- source
- equation number
- units
- required parameters
- whether coefficients are field-specific

---

# 24. Model state at the end of this equation-selection stage

## Fixed enough to implement

- psychrometric conversion
- temperature balance
- vapour-pressure balance
- convective/conductive heat exchange
- FIR heat exchange
- latent heat
- condensation
- ventilation moisture transport
- crop transpiration structure
- roof-vent natural ventilation
- leakage structure
- shade-screen optical control
- diffusive-material direct/direct-diffuse partitioning

## Still requiring parameters, but not new equations

- \(C_d\)
- \(C_w\)
- leakage coefficient
- actual cover properties
- shade-screen optical and thermal properties
- crop resistance parameters
- diffuse-screen optical coefficients

## Still missing a source equation

1. continuous **partial-opening diffuse-screen** relation for direct/direct-diffuse optical coefficients
2. explicit greenhouse-geometry-matched **wind-direction function** if a continuous analytical function is required
3. selected **5-min discretization method**

These gaps must not be filled by arbitrary equations.

---

# 25. Final decision

The prediction-model physics is anchored to Vanthoor Chapter 8 without rewriting its core balances.

The final core dynamic state is:

\[
\boxed{
x=[T_{Air},VP_{Air}]^T
}
\]

and the measured/derived humidity variables are obtained through the psychrometric block:

\[
(T,RH)
\leftrightarrow
VP
\leftrightarrow
X_i
\]

with VPD and dew point derived from the same vapour-pressure representation.

The principal controlled physical pathway is:

\[
U_{Roof}
\overset{\text{Vanthoor 8.65}}{\longrightarrow}
f_{VentRoof}
\longrightarrow
\begin{cases}
\text{heat transport} & \text{Vanthoor 8.40}\\
\text{vapour transport} & \text{Vanthoor 8.45}
\end{cases}
\longrightarrow
(T_{Air},VP_{Air})
\]

Shade-screen optics use Vanthoor Eq. (8.14)–(8.17).

Diffuse optical partitioning uses Cabrera direct-to-direct / direct-to-diffuse definitions, while **partial movable diffuse-screen opening remains intentionally unmodelled until a valid source or field characterization is available**.

This is the final equation baseline to use before numerical discretization, parameter identification, and MPC solver construction.

---

# References

1. Vanthoor, B. H. E. (2011). *A model-based greenhouse design method*. PhD thesis, Wageningen University. Especially Chapter 8, “Detailed description of greenhouse climate model.”
2. Boulard, T. & Baille, A. (1995). Source of the roof natural-ventilation formulation cited by Vanthoor Eq. (8.65).
3. Stanghellini, C. (1987). Source of the canopy vapour-transfer / stomatal-resistance formulation used by Vanthoor Eq. (8.47)–(8.50).
4. Cabrera, F. J., Baille, A., López, J. C., González-Real, M. M., & Pérez-Parra, J. (2009). “Effects of cover diffusive properties on the components of greenhouse solar radiation.” *Biosystems Engineering*, 103, 344–356.
