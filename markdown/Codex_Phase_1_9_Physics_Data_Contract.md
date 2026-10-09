# Phase 1.9 — Physics Data Contract & Solar/Radiation Model Foundation

## Purpose

Phase 1.9 prepares the greenhouse digital twin for the next physics stages without yet implementing full ray tracing, thermal prediction, MPC, or live PLC/Growlink integration.

The goal is to create a **stable physics-domain contract** between:

1. the existing 3D greenhouse / Three.js application,
2. future solar geometry and ray-casting modules,
3. future greenhouse thermal / gray-box models,
4. and later real field data.

Phase 1.9 must make physical assumptions explicit, separate visual parameters from physical parameters, and define a clean input/output schema before Phase 2.0 begins.

## 1. Current Project State

The project has completed Phase 1.8.1.

Existing capabilities include:

- Blender greenhouse model exported as GLB
- Django local application
- Three.js greenhouse viewer
- ALL / span spatial navigation
- 3D object selection
- context panel
- camera focus
- breadcrumb navigation
- layer / overlay controls
- mock live-state pipeline
- actuator animation
- normalized Growlink-style DTO adapter
- frontend polling/state handling
- presentation-oriented dark industrial UI

The current frontend and actuator behavior must continue to work.

Phase 1.9 must **not** break the existing 1.8.1 user experience.

## 2. Non-Goals

Do **not** implement the following in Phase 1.9:

- actual ray casting
- radiation heatmap
- sun-shadow visualization
- direct PLC communication
- Growlink network requests
- field bridge
- database logging
- thermal prediction
- gray-box model calibration
- MPC
- robust MPC
- automatic control
- actuator commands
- CFD
- leaf-level optical simulation
- multiple reflection
- spectral radiation modeling
- Monte Carlo radiative transfer
- cloud geometry prediction

Phase 1.9 is a **contract, parameter, coordinate, and validation foundation**.

## 3. Core Design Principles

### 3.1 Visual properties and physical properties must be separated

Do not reuse Blender/Three.js visual material values such as opacity, alpha, roughness, display transmission, or display colors as physical solar transmittance.

```text
Blender / Three.js material
    └── visual transparency

Physics model
    └── solar_transmittance
```

### 3.2 Unknown values must stay unknown

Do not invent physical constants.

If a real value is not known, represent it explicitly as:

```json
{
  "value": null,
  "verified": false
}
```

Temporary values used only in tests must be clearly marked as test fixtures and must never be presented as real greenhouse specifications.

### 3.3 Keep the field system isolated

Phase 1.9 must not contact:

```text
http://127.0.0.1:8000/api/live
192.168.x.x PLC addresses
Growlink
field PC
```

No credentials, cookies, PLC registers, network scans, or control endpoints may be added.

### 3.4 Prepare for future model re-anchoring

Later, the real greenhouse model will repeatedly initialize from actual measurements.

The contract should therefore distinguish:

```text
measured state
weather disturbance
actuator state
physics parameters
derived physics outputs
```

Do not mix them into one unstructured dictionary.

## 4. Target Architecture

```text
                    ┌─────────────────────────┐
                    │  Current / future data  │
                    │  mock → field bridge    │
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │ Physics Input Contract  │
                    └───────────┬─────────────┘
                                │
             ┌──────────────────┴──────────────────┐
             ▼                                     ▼
    Solar Geometry Model                  Optical Parameters
      (Phase 2.0)                          (Phase 1.9)
             │                                     │
             └──────────────────┬──────────────────┘
                                ▼
                       Ray / Radiation Model
                          (Phase 2.0–2.1)
                                │
                                ▼
                      Effective Irradiance
                                │
                                ▼
                    Greenhouse Thermal Model
                          (Phase 2.2+)
                                │
                                ▼
                              MPC
                          (Phase 3.0+)
```

## 5. Required Directory Structure

Recommended structure:

```text
physics/
├── __init__.py
├── contracts.py
├── coordinates.py
├── parameters.py
├── validation.py
└── README.md

config/
├── greenhouse.json
├── physics/
│   ├── site.json
│   ├── optical_properties.json
│   └── radiation_model.json
└── ...

tests/
├── test_physics_contracts.py
├── test_physics_coordinates.py
├── test_physics_parameters.py
└── ...
```

If the existing repository structure makes another location cleaner, preserve the architectural intent rather than forcing this exact path.

## 6. Physics Input Contract

Define one stable input model for later physics calculations.

Recommended conceptual schema:

```json
{
  "timestamp": "2026-09-28T13:00:00+09:00",
  "site": {
    "latitude_deg": null,
    "longitude_deg": null,
    "elevation_m": null,
    "timezone": "Asia/Seoul"
  },
  "weather": {
    "outdoor_temperature_c": null,
    "relative_humidity_pct": null,
    "global_horizontal_irradiance_w_m2": null,
    "direct_normal_irradiance_w_m2": null,
    "diffuse_horizontal_irradiance_w_m2": null,
    "wind_speed_m_s": null,
    "wind_direction_deg": null
  },
  "greenhouse_state": {
    "indoor_temperature_c": null,
    "indoor_relative_humidity_pct": null
  },
  "actuators": {
    "roof_vent_left_pct": null,
    "roof_vent_right_pct": null,
    "shade_screen_1_pct": null,
    "shade_screen_2_pct": null
  }
}
```

Rules:

- This is the physics-domain input, not necessarily the public frontend API.
- The contract must allow missing values.
- Missing data must not be silently converted to zero.
- Percent semantics must be documented.
- Timestamp must include timezone information.

## 7. Percent / Actuator Semantics

### Roof vents

Use:

```text
0%   = closed
100% = fully open
```

If future field data uses another convention, convert it in the adapter layer.

### Screens

Define two separate concepts:

```text
opening_percent
deployment_fraction
```

Recommended physical conversion:

```text
deployment_fraction = 1 - opening_percent / 100
```

Therefore:

```text
opening_percent = 100 → fully retracted → deployment_fraction = 0
opening_percent =   0 → fully deployed  → deployment_fraction = 1
```

Never rely on an ambiguous name such as `screen_percent`.

## 8. Site Configuration

Create a site configuration file.

```json
{
  "site_id": "greenhouse_01",
  "latitude_deg": null,
  "longitude_deg": null,
  "elevation_m": null,
  "timezone": "Asia/Seoul",
  "orientation": {
    "greenhouse_long_axis_azimuth_deg": null,
    "verified": false,
    "source": null
  }
}
```

Do not infer exact greenhouse orientation from screenshots.

Keep orientation unknown until a reliable source is available.

## 9. Coordinate-System Contract

This is one of the most important Phase 1.9 tasks.

Document all coordinate systems explicitly.

Current greenhouse model convention:

```text
Blender:
X = greenhouse length
Y = greenhouse width
Z = vertical
1 Blender unit = 1 meter
```

The GLB / web path may introduce Blender Z-up → glTF / Three.js Y-up conversion.

Define one canonical physics frame:

```text
X = greenhouse longitudinal axis
Y = greenhouse lateral axis
Z = vertical upward
units = meters
right-handed coordinate system
```

Create conversion helpers between:

```text
Blender coordinates
GLB / Three.js coordinates
physics coordinates
```

Do not allow future solar-ray code to guess axis conventions.

## 10. Orientation / North Reference

Ray casting requires a relation between the greenhouse model and geographic north.

Required variable:

```text
greenhouse_long_axis_azimuth_deg
```

Recommended convention:

```text
0°   = North
90°  = East
180° = South
270° = West
```

Document that azimuth is clockwise from North.

Do not assign a real number until verified.

## 11. Optical Properties Contract

Create `config/physics/optical_properties.json`.

```json
{
  "schema_version": 1,
  "roof_cover": {
    "solar_transmittance_direct": {
      "value": null,
      "unit": "fraction",
      "verified": false,
      "source": null
    },
    "solar_transmittance_diffuse": {
      "value": null,
      "unit": "fraction",
      "verified": false,
      "source": null
    }
  },
  "shade_screen_1": {
    "solar_transmittance_deployed": {
      "value": null,
      "unit": "fraction",
      "verified": false,
      "source": null
    }
  },
  "shade_screen_2": {
    "solar_transmittance_deployed": {
      "value": null,
      "unit": "fraction",
      "verified": false,
      "source": null
    }
  }
}
```

Validation range:

```text
0.0 ≤ transmittance ≤ 1.0
```

Do not require values to be present.

## 12. Radiation Model Configuration

Create a radiation-model configuration.

```json
{
  "schema_version": 1,
  "grid": {
    "cell_size_m": 1.0,
    "reference_height_m": null
  },
  "direct_radiation": {
    "enabled": true,
    "method": "ray_cast"
  },
  "diffuse_radiation": {
    "enabled": true,
    "method": "isotropic_initial"
  },
  "reflections": {
    "enabled": false
  },
  "canopy_attenuation": {
    "enabled": false
  }
}
```

This config does not yet execute a radiation model.

## 13. Future Solar Geometry Contract

Do not implement the full solar-position engine yet unless a tiny utility is useful for validation.

Define the future output schema:

```json
{
  "sun": {
    "altitude_deg": null,
    "azimuth_deg": null,
    "zenith_deg": null,
    "direction_physics": {
      "x": null,
      "y": null,
      "z": null
    }
  }
}
```

Conventions:

```text
altitude:
0°  = horizon
90° = zenith

azimuth:
0°   = North
90°  = East
180° = South
270° = West
```

Direction vector must be normalized.

## 14. Future Radiation Output Contract

Define the output structure for Phase 2.1 now.

```json
{
  "timestamp": "...",
  "sun": {
    "altitude_deg": 0.0,
    "azimuth_deg": 0.0
  },
  "radiation": {
    "mean_inside_irradiance_w_m2": null,
    "direct_mean_w_m2": null,
    "diffuse_mean_w_m2": null,
    "grid": {
      "cell_size_m": 1.0,
      "rows": null,
      "cols": null,
      "values_w_m2": []
    }
  },
  "quality": {
    "status": "not_computed",
    "missing_inputs": []
  }
}
```

Avoid adding large empty arrays to normal frontend responses before Phase 2.1.

## 15. Input Quality / Missing-Value Rules

### Missing outdoor solar

```text
radiation calculation cannot run
status = missing_input
```

Do not substitute `0 W/m²` unless the source explicitly measured zero.

### Missing DNI / DHI but GHI exists

Future behavior should be marked as:

```text
decomposition_required
```

Do not implement an arbitrary decomposition formula in Phase 1.9.

### Missing optical coefficient

Return or mark:

```text
parameter_missing
```

Never present a default research value as measured greenhouse data.

## 16. Parameter Provenance

Every physical parameter should eventually support provenance.

```json
{
  "value": 0.75,
  "unit": "fraction",
  "verified": true,
  "source_type": "manufacturer_spec",
  "source": "document/reference",
  "notes": null
}
```

Conceptual source types:

```text
measured
manufacturer_spec
drawing
paper
estimated
temporary_test_fixture
unknown
```

## 17. Variable Dictionary

Create a concise variable dictionary in `physics/README.md`.

| Variable | Meaning | Unit | Type |
|---|---|---:|---|
| `Tin` | Representative indoor air temperature | °C | measured state |
| `RHin` | Representative indoor RH | % | measured state |
| `Tout` | Outdoor air temperature | °C | disturbance |
| `GHI` | Global horizontal irradiance | W/m² | disturbance |
| `DNI` | Direct normal irradiance | W/m² | disturbance / derived |
| `DHI` | Diffuse horizontal irradiance | W/m² | disturbance / derived |
| `Wind` | Outdoor wind speed | m/s | disturbance |
| `VentL` | Left roof vent opening | % | actuator |
| `VentR` | Right roof vent opening | % | actuator |
| `Shade1` | Shade screen opening | % | actuator |
| `Shade2` | Second screen opening | % | actuator |
| `I_inside_mean` | Mean effective internal irradiance | W/m² | physics output |

Clearly state that exact field-variable mappings remain provisional until live integration.

## 18. Compatibility With Existing Growlink Adapter

Do not rewrite the existing normalized live-data pipeline.

Define one small adapter boundary:

```text
normalized live DTO
        ↓
physics input builder
        ↓
PhysicsInput
```

Recommended function shape:

```python
def build_physics_input(
    live_snapshot,
    site_config,
    optical_config,
    timestamp=None,
):
    ...
```

The function must:

- not perform network calls
- not mutate the source DTO
- preserve missing values
- validate units / expected ranges where possible
- return a stable physics-domain structure

## 19. Validation Rules

Implement lightweight validation.

```text
latitude      -90 ≤ value ≤ 90
longitude    -180 ≤ value ≤ 180
RH              0 ≤ value ≤ 100
percentage      0 ≤ value ≤ 100
transmittance   0 ≤ value ≤ 1
wind speed      value ≥ 0
irradiance      value ≥ 0
```

Unknown / null values are allowed where explicitly unresolved.

Differentiate:

```text
missing
invalid
unverified
```

## 20. Required Tests

At minimum add tests for:

### Contract tests

- valid minimal PhysicsInput
- missing optional values
- timezone-aware timestamp
- invalid RH
- invalid percentage
- invalid negative irradiance
- invalid transmittance
- null unverified optical values accepted

### Screen semantics

Verify:

```text
opening 100% → deployment 0.0
opening 50%  → deployment 0.5
opening 0%   → deployment 1.0
```

### Coordinate helpers

Verify:

- vectors maintain expected axes
- conversion functions are deterministic
- normalized direction helper returns magnitude ≈ 1
- no accidental axis swapping

### Adapter boundary

Use the existing Growlink fixture / normalized mock snapshot.

Verify that:

```text
live snapshot
→ physics input builder
```

does not change frontend live DTO behavior.

## 21. Frontend Changes

Keep frontend changes minimal.

Optional development metadata may show:

```text
PHYSICS
Contract: READY
Site orientation: UNVERIFIED
Optical properties: INCOMPLETE
Ray model: NOT ACTIVE
```

Do not add radiation maps yet.

Do not clutter the 3D UI.

## 22. Documentation

Update README with:

```text
Phase 1.9 — Physics Data Contract
```

Document:

- why physical and visual properties are separate
- coordinate convention
- orientation convention
- actuator semantics
- unknown parameter policy
- input/output contracts
- Phase 2.0 handoff

Include a clear warning:

> Phase 1.9 defines the physics interface but does not yet claim physically validated greenhouse radiation or thermal predictions.

## 23. Phase 2.0 Handoff Requirements

Phase 1.9 is complete only when Phase 2.0 can begin without redefining basic conventions.

Phase 2.0 should be able to consume:

```text
timestamp
site coordinates
greenhouse orientation
canonical geometry coordinate frame
solar/radiation input fields
optical parameter structure
screen deployment fraction
```

and produce:

```text
sun altitude
sun azimuth
sun direction
binary sunlit/shaded grid
```

without changing Phase 1.9 schemas.

## 24. Acceptance Criteria

- [ ] physics-domain package exists
- [ ] stable PhysicsInput contract exists
- [ ] stable future RadiationOutput contract exists
- [ ] canonical physics coordinate system is documented
- [ ] Blender / GLB / Three.js axis relationship is documented
- [ ] greenhouse geographic orientation is represented explicitly
- [ ] unknown orientation remains unverified rather than guessed
- [ ] optical parameters are separated from rendering materials
- [ ] unknown physical coefficients remain null/unverified
- [ ] actuator percentage semantics are explicit
- [ ] screen opening → deployment conversion is implemented and tested
- [ ] physics input builder can consume current mock/normalized live data
- [ ] no network / PLC / Growlink calls have been added
- [ ] no ray tracing has been implemented yet
- [ ] no thermal prediction has been implemented yet
- [ ] existing Phase 1.8.1 frontend behavior still works
- [ ] Python tests pass
- [ ] frontend tests still pass
- [ ] README contains Phase 1.9 documentation

## 25. Suggested Execution Order

```text
1. Inspect current Phase 1.8.1 architecture
2. Add physics package
3. Define coordinate conventions
4. Define config schemas
5. Define physics input/output contracts
6. Implement validation
7. Implement screen semantic conversion
8. Implement normalized-live → physics input builder
9. Add unit tests
10. Update README
11. Run full regression suite
```

Do not modify the 3D model unless a coordinate metadata issue requires a small documented change.

## 26. Verification Commands

Use the project's existing virtual environment.

```powershell
.\sfes\Scripts\Activate.ps1
python manage.py check
python -m unittest discover -s tests -v
node --test tests/frontend_phase17.test.mjs
node --test tests/frontend_phase18_1.test.mjs
```

If compatible with the repository:

```powershell
node --test tests/*.test.mjs
python scripts/sync_web_assets.py --check
```

Finally:

```powershell
python manage.py runserver 127.0.0.1:8010
```

Verify that the existing viewer still behaves normally.

## 27. Final Implementation Report

When implementation is complete, report only:

### Relevant files

List files created and modified.

### Implemented

Summarize:

- physics contracts
- coordinate convention
- parameter config
- validation
- physics-input builder
- tests
- documentation

### Verified

Report exact test results.

### Known unresolved physical inputs

Explicitly list values that remain unknown, for example:

```text
- exact latitude / longitude
- greenhouse geographic orientation
- roof-cover solar transmittance
- shade-screen optical properties
- exact crop reference height
- DNI/DHI availability or decomposition method
```

### Phase 2.0 readiness

State whether the codebase is ready for:

```text
Solar Geometry + Binary Ray / Shadow Model
```

Do not claim physical accuracy before validation.

## 28. Strict Safety / Scope Constraints

Do not:

- call the real field Growlink endpoint
- contact the PLC
- write any actuator value
- add control endpoints
- modify field-system code
- add credentials
- use captured cookies
- add auto-start services
- invent greenhouse specifications
- invent physical coefficients
- silently replace missing data with zero

Phase 1.9 is entirely local and read-only with respect to existing project fixtures.

## Completion Definition

The primary outcome of Phase 1.9 is not a visual feature.

It is a reliable statement that:

> The digital twin now has a documented and tested physical-data boundary, coordinate system, optical-parameter structure, and actuator semantics that Phase 2.0 can use without redefining the project architecture.

Only after this is stable should Phase 2.0 implement solar position and binary ray/shadow calculations.
