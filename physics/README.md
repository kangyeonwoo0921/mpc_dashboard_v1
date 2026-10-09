# Phase 1.9 — Physics Data Contract

This package is a local, read-only boundary for future models. It does not load
Blender materials, call a data source, or execute solar/radiation/thermal models.
The existing Django LIVE endpoint and Three.js viewer have no dependency on it.

> Phase 1.9 defines the physics interface but does not yet claim physically validated greenhouse radiation or thermal predictions.

## Use

```python
from live_data.sources import get_live_snapshot
from physics import build_physics_input, RadiationOutput
from physics.parameters import load_physics_config

site, optics, radiation_options = load_physics_config()
snapshot = get_live_snapshot("mock_static")  # existing local fixture only
inputs = build_physics_input(snapshot, site, optics)
payload = inputs.to_dict()  # json.dumps(payload, allow_nan=False)
future_output = RadiationOutput(timestamp=inputs.timestamp).to_dict()
```

`build_physics_input(live_snapshot, site_config, optical_config, timestamp=None)`
accepts the existing **English normalized DTO**, not Growlink raw JSON. The
timestamp override may be an aware datetime or ISO string; otherwise the source
timestamp is required. It never replaces a missing timestamp with current time.
The builder neither mutates nor retains mutable references to input config/DTO.
Config accepts typed dataclasses or JSON dictionaries; unknown config keys fail.
No dependencies were added.

## Version 1 contracts

`contracts.py` defines validated dataclasses; `.to_dict()` produces a detached
JSON-compatible structure. Construct typed nested dataclasses for direct use.

| Contract | Fields / purpose |
|---|---|
| `PhysicsInput` | schema_version=1, timezone-aware timestamp, site, weather, greenhouse_state, actuators, optical_parameters, provenance, quality |
| `Weather` | outdoor_temperature_c, relative_humidity_pct, global_horizontal_irradiance_w_m2, direct_normal_irradiance_w_m2, diffuse_horizontal_irradiance_w_m2, wind_speed_m_s, wind_direction_deg |
| `GreenhouseState` | indoor_temperature_c, indoor_relative_humidity_pct; representative house-level state |
| `Actuators` | roof_vent_left_pct, roof_vent_right_pct, shade_screen_1_pct, shade_screen_2_pct, derived shade_screen_1/2_deployment_fraction |
| `SolarOutput` | sun: altitude_deg, azimuth_deg, zenith_deg, direction_physics {x,y,z} |
| `RadiationOutput` | schema_version=1, timestamp, sun, radiation, quality |
| `Radiation` | mean_inside_irradiance_w_m2, direct_mean_w_m2, diffuse_mean_w_m2, grid |
| `RadiationGrid` | cell_size_m, rows, cols, values_w_m2, sunlit_mask |

Future output defaults to `not_computed`, null scalars and empty arrays. Neither
output nor arrays are added to the public LIVE response. Grid arrays are flat
row-major; rows increase along physics +Y, columns along +X. `sunlit_mask` reserves
binary Phase 2.0 results (1=sunlit, 0=shaded, null=unknown). Future grid generation
uses greenhouse footprint bounds and configured reference height; no grid is
generated now. Irradiance arrays allow null cells and nonnegative measured zero.

All numeric values must be finite numbers (booleans/strings are rejected). Null
means missing, never zero. Validation raises `PhysicsValidationError` with field
path and invalid value. RH and opening are [0,100], transmittance [0,1], wind speed
and irradiance nonnegative, latitude [-90,90], longitude [-180,180]. Bearings are
[0,360). Null measurements/parameters remain accepted.

`InputQuality.missing_inputs` lists absent measurements and parameters;
`unverified_inputs` separately lists provenance and provisional mapping gaps.
Concurrent `statuses` are preserved; the primary `status` follows this order:

1. `missing_input`: no outdoor GHI, required site coordinates, or orientation.
2. `parameter_missing`: one or more optical coefficients absent.
3. `decomposition_required`: GHI exists but DNI and/or DHI absent, including GHI=0.
4. `disconnected`: source explicitly disconnected.
5. `unverified`: populated or missing values lack verification, or mapping is provisional/mock.
6. `not_computed`: no above condition; still **no model executed**.

Optional measurements are listed as missing without blocking solar preparation.
No decomposition, zero fill, physical estimation, or percentage clamp occurs in
this package. Existing LIVE adapter clamping remains unchanged upstream. Future
consumers must gate physical claims on all quality conditions, not just `status`.

## Coordinates and north

Canonical physics coordinates equal Blender world coordinates: X longitudinal,
Y lateral, Z up, meters, right-handed. Origin is footprint center at ground.
Front X1 is `(-length/2,0,0)` and Rear X23 is `(+length/2,0,0)`; +X runs Front→Rear.
Existing GH_ROOT orientation extras and all object names remain unchanged.

| Conversion | Formula |
|---|---|
| Blender ↔ physics | identity |
| physics/Blender → GLB/Three.js world | (x,y,z) → (x,z,-y) |
| GLB/Three.js world → physics/Blender | (x,y,z) → (x,-z,y) |

`coordinates.py` applies these transforms to world points or vectors. A local
GLB node point must first be transformed by its world matrix. GLB extras retain
their original Blender-coordinate numbers; do not convert these as though they
were GLB world points. Actuator rotations/scales remain in imported **local X**;
these helpers do not change the viewer's local motion contract.

`greenhouse_long_axis_azimuth_deg` describes physics **+X** (Front→Rear), clockwise
from geographic North: 0 North, 90 East, 180 South, 270 West. It is set to 284
from a field compass reading (ridge 104 deg, X1 at the east end) and remains
unverified; a magnetic reading would put it about 8-9 deg lower. Screenshots and model camera directions cannot establish north.
For a future geographic ENU transform at azimuth A, physics +X corresponds to
(sin A, cos A, 0), +Y to (-cos A, sin A, 0), and +Z to (0,0,1).

Sun altitude is -90..90 (0 horizon, 90 zenith), zenith=90-altitude. Sun azimuth
uses the same geographic convention. `direction_physics` is the unit vector
**from the greenhouse toward the sun**; incoming light travels along its negative.
All-null directions are unknown; partial, zero or non-unit vectors are invalid.
`normalized_direction` rejects zero/nonfinite input. No solar engine exists yet.

## Parameters, semantics and provenance

- `config/physics/site.json`: latitude 35.8370, longitude 126.7090, elevation 3 m
  (user-provided lookup) and azimuth 284 (compass reading) are set but unverified;
  timezone is Asia/Seoul. Coordinate provenance is keyed by coordinate name;
  orientation has its own verified/source/source_type fields.
- `optical_properties.json`: independent direct/diffuse roof transmittance and
  deployed screen-1/screen-2 transmittance. Operator-reported values are set
  (cover 0.85, screens 0.25/0.80); diffuse cover transmittance stays null. None is
  verified. Each supports
  value, unit, verified, source, source_type, notes. A verified parameter must have
  a value, source and non-unknown source_type.
- Source types: measured, manufacturer_spec, drawing, paper, estimated,
  operator_reported, temporary_test_fixture, unknown. Non-null does not imply verified.
- `radiation_model.json`: 1m cell size is a numerical model setting, **not a
  measured physical coefficient**. Reference height remains null. Enabled method
  flags specify future intent only; reflections/canopy attenuation remain disabled.
- Blender/Three.js opacity, alpha, roughness, color and display transmission are
  never solar transmittance. Existing visual config is neither read nor copied.
- Vents: 0% closed, 100% fully open. Screens: 0% fully deployed, 100% retracted;
  `deployment_fraction = 1 - opening_percent / 100`. Missing opening gives null
  deployment. Screen percentages in the contract always mean **opening**.

## Normalized boundary and variable dictionary

Existing `environment.solar_w_m2` maps provisionally to GHI. The fixture does not
prove sensor mounting, horizontal orientation or calibration; quality records
that mapping as unverified. Indoor RH is never used as outdoor RH. Current DTO
lacks DNI/DHI, outdoor RH and numeric wind direction; they stay null. The builder
does not guess degrees from `wind_direction_text`, or use accumulated solar as
instantaneous irradiance. Raw Korean keys remain exclusively in the LIVE adapter.

| Variable | Meaning | Unit | Type |
|---|---|---|---|
| Tin | Representative indoor temperature | °C | measured state (currently mock) |
| RHin | Representative indoor RH | % | measured state (currently mock) |
| Tout | Outdoor temperature | °C | disturbance |
| GHI | Global horizontal irradiance | W/m² | disturbance; provisional mapping |
| DNI | Direct normal irradiance | W/m² | disturbance / future derived |
| DHI | Diffuse horizontal irradiance | W/m² | disturbance / future derived |
| Wind | Outdoor wind speed | m/s | disturbance |
| VentL / VentR | Left/right vent opening | % | actuator |
| Shade1 / Shade2 | Screen opening | % | actuator |
| I_inside_mean | Mean effective internal irradiance | W/m² | future physics output |

Field-to-geometry mappings remain provisional: VentL all +Y leaves (`_01`),
VentR all -Y leaves (`_02`); Shade1 shade pivots, Shade2 diffuse pivots (the
Growlink API exposes only 차광커튼1/2, no separately named diffuse channel). The physics contract does not assert
these are independent actual field mechanisms. It preserves source and connection
status; no fake per-span measurement is generated.

## Phase 2.0 handoff and tests

Consume `build_physics_input`, `load_physics_config`, and the world-coordinate
helpers. Produce `SolarOutput` and `RadiationOutput` using the existing contracts.
Implement verified solar position / binary shadow separately. Do not silently
run with unknown site, north, reference height or optics. Any synthetic scenario
must use explicit `temporary_test_fixture` provenance, never production defaults.
Future normalized-field additions belong at the builder boundary; frontend raw
parsing is unnecessary. No Django route, network client, credentials or controls
were added in this phase.

From the project root in the existing sfes environment:

```powershell
python -m unittest discover -s tests
node --test tests/*.test.mjs
python manage.py check
python scripts/sync_web_assets.py --check
python manage.py runserver 127.0.0.1:8010
```

On this workstation the existing interpreter is
`C:/Users/user/anaconda3/envs/sfes/python.exe`; no new environment is required.

## Sample cross-section light model (framework, not validated)

`physics/light_sample.py` is a dependency-free sample that computes canopy-plane
irradiance across the house width for one timestamp. It follows Zhang et al.
(2020, Energies 13:1108) for solar geometry, Fresnel PO-film transmittance
(Z=1.535, scaled to the reported 0.85; diffuse uses the 60 deg value), beam ray
tracing and the 2-D isotropic diffuse view factor, and Miguel et al. (1994,
J. agric. Engng Res. 59:61-72) for screens as fully diffusing layers with a
screen/ground inter-reflection factor. The outside sensor value is converted to
a global equivalent (PAR = 0.47 x global, assumed) and split with Erbs.

```powershell
python -m physics.light_sample --time 2026-10-01T12:30+09:00 --irradiance 400 --basis par --shade 100 --diffuse 100
```

Not yet modelled: vents, structure shading, interior reflections, outside
ground reflection, canopy attenuation and the stepped front (infinite-length
section). Results are not wired into `RadiationOutput` or the LIVE API.

## 3-D light model (framework, not validated)

`physics/light_model.py` traces the viewer GLB with trimesh + Embree. Frame
members and sandwich end panels are opaque; cover, windbreak, side walls and
curtains are PO film. Vents and screens follow the actuator state analytically.
Diffuse sky paths (48 cosine-weighted directions per 1 m cell at canopy height)
are cached in `tmp/light_cache/`; beam light uses a 3x3 sub-grid per cell.
`shared_model().evaluate(when, actuators, irradiance=None|value)` returns the
canopy grid (rows along +Y, columns along +X, NaN outside the stepped
footprint) and means. `irradiance=None` uses the Zhang et al. (2020) clear-sky
model. The Django endpoint `/api/digital-twin/solar/` serves it to the viewer.

