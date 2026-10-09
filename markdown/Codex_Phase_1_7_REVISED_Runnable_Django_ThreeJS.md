# Codex Implementation Brief — Phase 1.7 Revised
## Runnable Django + Three.js LIVE Digital Twin Foundation

> **Context**
> - Phase 1.6 is complete and produces `dist/greenhouse.blend`, `dist/greenhouse.glb`, and validation outputs.
> - The Phase 1.6 GLB already preserves controllable node names, parent relationships, custom properties, and motion contracts.
> - A Phase 1.7 scaffold has already been partially created: Growlink-compatible fixture, raw→normalized adapter, mock static/dynamic source, Django app boundary, frontend polling/state/actuator helper modules, and tests.
> - However, the repository does **not** yet contain a runnable Django project shell or an actual Three.js viewer entrypoint.
>
> **Primary goal**
> Finish Phase 1.7 as a runnable local web application. The absence of Django project files and the viewer is part of this phase, not a blocker.

---

# 1. Final target

```text
dist/greenhouse.glb
        ↓
Django static serving
        ↓
Three.js GLTFLoader
        ↓
3D greenhouse viewer

Growlink-compatible mock data
        ↓
adapter
        ↓
GET /api/digital-twin/live/
        ↓
frontend polling
        ↓
LIVE panel
        ↓
roof vent / screen motion
```

The user must be able to run:

```powershell
python manage.py runserver 127.0.0.1:8010
```

and open:

```text
http://127.0.0.1:8010/
```

to see the 3D greenhouse with mock LIVE values and actuator animation.

---

# 2. Do not stop because Django/viewer is missing

If these are missing:

```text
manage.py
settings.py
urls.py
templates
viewer entrypoint
Three.js bootstrap
```

create the smallest coherent Django project shell necessary to run the existing `digital_twin` app and 3D viewer.

Do not ask the user for another project path unless integrating a project shell would overwrite substantial existing code.

---

# 3. Preserve Phase 1.6 contracts

Read the current README first and preserve:

```text
dist/greenhouse.glb
```

Important node patterns:

```text
GH_VENT_Sxx_01_PIVOT
GH_VENT_Sxx_01
GH_SHADE_SCREEN_Sxx_PIVOT
GH_SHADE_SCREEN_Sxx
GH_DIFFUSE_SCREEN_Sxx_PIVOT
GH_DIFFUSE_SCREEN_Sxx
GH_SIDE_CURTAIN_LEFT
GH_SIDE_CURTAIN_RIGHT
GH_SENSOR_*_ANCHOR
```

Motion semantics:

```text
Roof vent:
local X rotation
angle = percent/100 × max_open_angle_deg

Shade/diffuse screen:
local X scale = max(1 - percent/100, 1e-6)
```

Use imported glTF node-local transforms. Do not invent different motion semantics.

---

# 4. Reuse existing Phase 1.7 scaffold

Inspect and reuse existing modules where valid.

Expected pieces may include:

```text
live_data/
digital_twin/
digital_twin/static/digital_twin/js/
digital_twin/static/digital_twin/css/
tests/frontend_phase17.test.mjs
```

Do not duplicate working code with a second implementation.

---

# 5. Create runnable Django project shell

If none exists, create one in the current repository.

Use a project package name that does not conflict with the existing greenhouse `config/` directory, for example:

```text
webconfig/
```

Minimal structure:

```text
manage.py
webconfig/
    __init__.py
    settings.py
    urls.py
    wsgi.py
digital_twin/
    ...
```

Do not name the Django package `config`.

---

# 6. Django requirements

Minimal local-development setup only.

Required:

```text
INSTALLED_APPS
- minimal Django defaults
- digital_twin

TEMPLATES
- app_dirs enabled

STATIC_URL
- configured

database
- SQLite only if Django requires config
- no model dependency
```

No authentication, admin customization, production deployment, database persistence, Celery, Redis, REST framework, or WebSockets.

---

# 7. Routes

Required:

```text
GET /
GET /api/digital-twin/live/
```

The root route should render the 3D viewer.

---

# 8. Viewer template

Create an actual template, e.g.:

```text
digital_twin/templates/digital_twin/viewer.html
```

It must include:

```text
3D canvas/container
loading/status message
LIVE information panel
MOCK DATA badge
```

Keep the layout simple and 3D-first.

---

# 9. Three.js integration

If the repository does not already use npm/Vite/Webpack, do not introduce a build system.

Use browser ES modules/import map or a stable module CDN for:

```text
three
GLTFLoader
OrbitControls
```

Create one real viewer entrypoint, e.g.:

```text
digital_twin/static/digital_twin/js/viewer.mjs
```

Responsibilities:

```text
1. create scene
2. create camera
3. create renderer
4. add OrbitControls
5. add neutral lighting
6. load greenhouse.glb
7. frame camera to bounds
8. build controllable-node registry
9. initialize LIVE polling
10. apply actuator targets
11. render continuously
```

---

# 10. GLB sync

Canonical generated asset:

```text
dist/greenhouse.glb
```

Web asset:

```text
digital_twin/static/digital_twin/models/greenhouse.glb
```

Create:

```text
scripts/sync_web_assets.py
```

It must copy source → destination, fail clearly if the source is missing, create destination folders, overwrite deterministically, and print both paths.

Do not duplicate Blender generation logic.

---

# 11. Camera and controls

After GLB load:

```text
compute Box3
compute center
compute max dimension
position perspective camera from bounds
set OrbitControls target to center
```

The default view must fit the full greenhouse.

Enable:

```text
orbit
zoom
pan
```

Do not hardcode a fragile camera position.

---

# 12. Lighting

Use simple neutral inspection lighting:

```text
HemisphereLight
DirectionalLight
```

No HDRI, ray tracing, or solar simulation.

---

# 13. GLB metadata and object registry

Use both node names and `object.userData` exported from Blender.

Prefer metadata such as:

```text
asset_type
controllable
control_variable
span_index
opening_percent
max_open_angle_deg
side
```

Build a registry such as:

```javascript
{
  roofVents: [],
  shadeScreens: [],
  diffuseScreens: [],
  sideCurtains: []
}
```

Missing nodes must warn once and not crash the viewer.

---

# 14. Provisional roof-vent mapping

The real Growlink source has:

```text
천창 좌(L)
천창 우(R)
```

The Phase 1.6 model currently has one representative vent per span, not verified physical L/R pairs.

Use this temporary visualization mapping:

```text
roof_vent_left_pct
→ GH_VENT_S01_01_PIVOT
→ GH_VENT_S02_01_PIVOT

roof_vent_right_pct
→ GH_VENT_S03_01_PIVOT
→ GH_VENT_S04_01_PIVOT
```

Mark it explicitly as provisional.

Do not rename GLB nodes to imply physical certainty.

---

# 15. Screen mapping

Use:

```text
shade_screen_1_pct
→ GH_SHADE_SCREEN_S01_PIVOT ... S04

shade_screen_2_pct
→ GH_DIFFUSE_SCREEN_S01_PIVOT ... S04
```

Also mark the second mapping as provisional until the physical meaning of Growlink `차광커튼2` is confirmed.

---

# 16. Motion implementation

Roof vents:

```javascript
rotation.x = baseClosedRotation + sign * openingFraction * maxAngleRad;
```

Read `max_open_angle_deg` and `side` from userData where available.

Screens:

```javascript
scale.x = Math.max(1 - openingFraction, 1e-6);
```

Use imported local axes.

Do not manually convert Blender source coordinates for already-exported node transforms.

---

# 17. LIVE data pipeline

Reuse the existing pipeline:

```text
Growlink-shaped mock fixture
→ normalize_growlink_live()
→ get_live_snapshot()
→ GET /api/digital-twin/live/
→ frontend live client
→ state
→ UI + actuator targets
```

Frontend must use normalized English keys only.

---

# 18. Mock modes

Support:

```text
LIVE_DATA_SOURCE=mock_static
LIVE_DATA_SOURCE=mock_dynamic
```

Default:

```text
mock_dynamic
```

Dynamic mode is only for visual verification.

It is not a greenhouse model, physics model, or MPC.

---

# 19. LIVE panel

At minimum:

```text
MOCK DATA

Indoor
- Temperature
- RH
- VPD
- CO2

Outdoor
- Temperature
- Solar
- Wind speed
- Wind direction

Actuators
- Roof Vent L
- Roof Vent R
- Shade Screen 1
- Shade Screen 2

Connection
- connected / stale / disconnected
- last update
```

Null values display as `—`.

---

# 20. Polling/error handling

Poll approximately every 2 seconds.

Requirements:

```text
no overlapping requests
retain last valid state on failure
do not reset actuator positions on one failed request
stale after ~10 seconds without success
do not spam console
viewer remains interactive when API is unavailable
```

Prefer recursive `setTimeout` after each completed request.

---

# 21. Motion smoothing

Use current vs target actuator values and interpolate in the render loop.

Example:

```javascript
current += (target - current) * factor;
```

No animation library.

---

# 22. Side vents/curtains are not blockers

Priority:

```text
P0 runnable Django app
P0 working Three.js viewer
P0 GLB load
P0 roof vent motion
P0 shade/diffuse screen motion
P1 LIVE panel
P1 polling/stale logic
P2 side vents/side curtains
P3 fan/boiler visualization
```

Do not delay completion for unfinished Blender details.

---

# 23. Development commands

Ensure these work from repository root.

Typical PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/sync_web_assets.py
python -m unittest discover -s tests -v
node --test tests/frontend_phase17.test.mjs
python manage.py runserver 127.0.0.1:8010
```

Create/update `requirements.txt` with the minimum required Django dependency.

---

# 24. HTTP/browser acceptance

Verify:

```text
GET / → 200
GET /api/digital-twin/live/ → 200 JSON
GET greenhouse.glb static asset → 200
```

If browser automation is available, use it.

Otherwise verify HTTP/static behavior programmatically and document the manual browser check.

Required visual result:

```text
greenhouse GLB visible
full greenhouse framed
OrbitControls working
MOCK DATA visible
LIVE values updating
roof vents moving in mock_dynamic
screens retracting/deploying in mock_dynamic
```

---

# 25. README update

Update the existing README only.

Document:

```text
Phase 1.7 runnable status
Django/web project structure
run commands
viewer URL
LIVE endpoint
mock source modes
GLB sync command
Blender → generate → sync → browser workflow
current provisional actuator mapping
known uncertainties
```

Do not paste this entire specification into README.

---

# 26. Safety

Still forbidden:

```text
192.168.0.2 access
port 2004 access
PLC client
PLC read/write
real field Growlink request
Growlink POST/PUT/PATCH/DELETE
session cookie
credential hardcoding
actual equipment control
```

This phase is local and mock-only.

---

# 27. Phase 1.8 boundary

Phase 1.8 will replace only the raw source:

```text
FIELD PC
Growlink GET /api/live
→ read-only bridge
→ network
→ GrowlinkBridgeSource
→ same normalized DTO
→ same Django endpoint
→ same viewer
```

Frontend must not need to change.

---

# 28. Implementation order

```text
1. inspect current Phase 1.7 scaffold
2. inspect Phase 1.6 GLB contracts
3. create/fix manage.py
4. create Django project settings/root URLs
5. integrate digital_twin app
6. create root viewer template
7. create GLB sync script
8. load GLB in real Three.js viewer
9. frame camera / OrbitControls
10. build node registry
11. connect existing LIVE client/state
12. map roof vents
13. map shade/diffuse screens
14. connect LIVE panel
15. verify smoothing/error handling
16. run Python/frontend tests
17. verify HTTP/static endpoints
18. update README
```

Do not stop because the viewer did not previously exist.

---

# 29. Stop conditions

Only ask the user for input if:

```text
- there are two conflicting real Django project roots
- creating the project shell would overwrite substantial user code
- dist/greenhouse.glb does not exist and cannot be generated
- the GLB is corrupt/unreadable
```

For missing/unfinished Blender nodes:

```text
continue all unblocked work
report exact missing node/pivot issue
```

---

# 30. Acceptance criteria

```text
[ ] manage.py is runnable and non-empty
[ ] Django settings/root URLs exist
[ ] GET / renders the viewer
[ ] GLB sync works
[ ] actual Phase 1.6 greenhouse.glb loads in Three.js
[ ] OrbitControls work
[ ] camera auto-frames model
[ ] normalized mock API works
[ ] LIVE panel updates
[ ] mock_dynamic changes over time
[ ] actual GLB vent pivots are found
[ ] provisional L/R vent mapping moves real GLB nodes
[ ] shade-screen mapping moves real GLB nodes
[ ] diffuse-screen mapping moves real GLB nodes
[ ] actuator motion is smoothed
[ ] missing node does not crash viewer
[ ] API failure retains last valid state
[ ] stale/disconnected status works
[ ] MOCK DATA is visibly identified
[ ] existing Python tests pass
[ ] existing frontend tests pass
[ ] no real Growlink/PLC connection exists
[ ] README contains exact run workflow
```

---

# 31. Token-efficient Codex behavior

Before editing, output only:

```text
Relevant files
Plan
Files to create/modify
```

Then implement.

Do not:
- repeat this specification
- print the full repository tree
- narrate every command
- propose multiple architectures
- ask for a viewer path that does not exist
- pause for permission to create normal project files

---

# 32. Final report format

```text
Phase 1.7 revised — result

Created
- ...

Modified
- ...

Run
- GLB sync:
- tests:
- server:

Verified
- root page:
- live API:
- GLB static asset:
- Python tests:
- frontend tests:

3D runtime
- vents found:
- shade screens found:
- diffuse screens found:
- side curtains found:

Provisional mappings
- ...

Manual Blender fixes still needed
- ...

Phase 1.8 handoff
- exact source module/function to replace
```

---

# Final instruction

Finish Phase 1.7 as a **runnable local Django + Three.js application**, not only reusable modules.

The absence of a Django project shell and Three.js viewer is part of the work to complete.

Preserve the Phase 1.6 GLB contracts and reuse the already-created Phase 1.7 adapter/mock/runtime modules.

Do not connect to the real field system yet.
