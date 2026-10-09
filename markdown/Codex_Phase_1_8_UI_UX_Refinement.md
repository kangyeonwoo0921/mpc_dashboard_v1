# Codex Implementation Brief — Phase 1.8
## 3D Digital Twin Viewer & Dashboard UI/UX Refinement

> **Project status**
> - Phase 1.6: Blender/GLB operational greenhouse geometry complete.
> - Phase 1.7: Runnable local Django + Three.js viewer complete.
> - Current viewer loads the greenhouse GLB, polls mock LIVE data, and animates roof vents/screens.
> - The current interface is functionally correct but visually rough and hard to read as a presentation/demo-quality digital twin.
>
> **Primary Phase 1.8 goal**
> Refine the existing viewer into a clear, polished, desktop-first digital twin dashboard without changing the underlying data contracts, GLB contracts, mock pipeline, or control semantics.

---

# 0. Codex behavior

To reduce token waste and keep implementation focused:

1. Do not restate this specification.
2. Do not print the full repository tree.
3. First inspect only:
   - current Phase 1.7 viewer template
   - current viewer JS entrypoint
   - current CSS
   - LIVE panel partial/module
   - actuator runtime
   - live config
   - README Phase 1.7 section
   - GLB visibility/preset metadata handling
4. Before editing, output only:
   - `Relevant files`
   - `Implementation plan`
   - `Files to modify/create`
5. Then implement directly.
6. Do not refactor backend/live-data code unless required for UI integration.
7. Do not introduce React/Vue/Next/Vite/Webpack if not already used.
8. Do not add dependencies unless absolutely necessary.
9. Preserve all Phase 1.7 tests and runtime behavior.
10. At the end, report only the requested final summary format.

---

# 1. Scope

Phase 1.8 is **visual/UI/UX refinement only**.

Implement:

```text
existing Django + Three.js viewer
        ↓
better scene framing
        ↓
better dashboard layout
        ↓
camera presets
        ↓
visibility presets
        ↓
object highlight / tooltip
        ↓
collapsible live panel
        ↓
developer/debug drawer
        ↓
responsive desktop-first polish
```

Do NOT implement:

```text
actual Growlink bridge
Tailscale
remote networking
PLC access
PLC read/write
MPC
thermal model
grey-box model
solar ray tracing
radiation heatmap
weather forecast
database logging
historical charts
3D geometry regeneration logic
new physical assumptions
```

---

# 2. Preserve existing contracts

Do not break:

```text
GET /
GET /api/digital-twin/live/
LIVE_DATA_SOURCE=mock_static|mock_dynamic
normalized DTO structure
2-second polling
stale/disconnected handling
actuator smoothing
Phase 1.6 GLB node naming
Phase 1.6 GLB userData metadata
roof vent motion semantics
screen motion semantics
```

The current backend and mock source are considered working.

---

# 3. Current visual problems to solve

The current screenshot shows:

- greenhouse occupies too little of the viewport
- too much empty dark space
- title block consumes unnecessary vertical area
- right LIVE panel is text-heavy and visually flat
- 3D mapping/debug text is always visible and looks unfinished
- 3D object state is hard to inspect
- no camera presets
- no visibility layer controls
- no hover/select feedback
- hierarchy between LIVE status, environment, and actuator data is weak
- desktop demo/presentation feel is insufficient

Treat these as the primary design problems.

---

# 4. Design direction

Target style:

```text
technical
minimal
clean
dark UI
high information density
3D-first
engineering dashboard
not decorative
not game-like
not sci-fi neon
```

Avoid:

```text
excessive gradients
glowing neon
heavy shadows
huge typography
large empty panels
over-animation
visual gimmicks
```

The interface should look credible for:

```text
research presentation
engineering demo
academic poster/demo booth
lab meeting
project review
```

---

# 5. Desktop-first layout

Primary target resolutions:

```text
1920×1080
1440×900
1366×768
```

Mobile only needs to remain usable; it is not the primary design target.

Recommended desktop structure:

```text
┌──────────────────────────────────────────────────────────────┐
│ Header: Greenhouse Digital Twin     LIVE / MOCK / connection │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                    3D VIEWPORT                               │
│                                           ┌──────────────┐   │
│                                           │ LIVE PANEL   │   │
│                                           │ Indoor       │   │
│                                           │ Outdoor      │   │
│                                           │ Actuators    │   │
│                                           └──────────────┘   │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ View: Overview Front Rear Roof Interior Equipment Control    │
└──────────────────────────────────────────────────────────────┘
```

The 3D viewport should dominate the screen.

---

# 6. Header redesign

Replace the current large title treatment with a compact top bar.

Recommended content:

```text
Greenhouse Digital Twin
Phase 1.8

[MOCK DATA] [CONNECTED]
Last update 18:24:01
```

Requirements:

- header height approximately 48–64 px
- title size modest
- status badges aligned right
- no large empty hero-title area
- no oversized subtitle
- preserve dark theme

---

# 7. Initial camera framing

The current greenhouse appears too small.

Improve auto-framing so the greenhouse occupies approximately:

```text
60–75% of viewport width
and
55–70% of viewport height
```

Use actual Box3 bounds.

Do not hardcode a single camera position.

Recommended approach:

```text
model bounds
→ center
→ bounding sphere or max dimension
→ camera distance from FOV
→ apply framing multiplier
```

Add a configurable constant:

```javascript
CAMERA_FIT_MARGIN = ...
```

Tune it visually.

The greenhouse should feel close enough to inspect while preserving the full structure.

---

# 8. Camera transition behavior

When switching presets, do not teleport abruptly.

Implement smooth camera transition:

```text
current camera position
→ target camera position
current OrbitControls target
→ target model target
```

Duration:

```text
~400–700 ms
```

Do not add an animation library.

Use `requestAnimationFrame` with time-based interpolation.

---

# 9. Camera preset toolbar

Add visible view controls.

Required presets:

```text
Overview
Front
Rear
Roof
Interior
Equipment
Control
```

Use buttons or a segmented toolbar.

---

# 10. Camera preset definitions

Use Phase 1.6 orientation contract:

```text
Front = X1 / negative X end, looking +X
Rear = X23 / positive X end, looking -X
```

For each preset:

- **Overview**: elevated 3/4 perspective, full greenhouse visible.
- **Front**: centered from front end, looking +X.
- **Rear**: centered from rear end, looking -X.
- **Roof**: high oblique view emphasizing roof vents/screens.
- **Interior**: camera inside greenhouse; crops visible; roof/cover may be hidden.
- **Equipment**: focus service/fertigation zone; crops may be hidden/de-emphasized.
- **Control**: focus vents, screens, side curtains, sensors.

Do not reinterpret front/rear based on the current camera.

---

# 11. Visibility preset integration

Phase 1.6 already defines visibility concepts:

```text
exterior
interior
equipment
control_devices
```

Reuse these semantics in the web viewer.

Suggested mapping:

```text
Overview → exterior
Interior → interior
Equipment → equipment
Control → control_devices
```

Use node names and `userData`/extras.

Do not reproduce Blender's full visibility system.

---

# 12. Visibility runtime

Create a small module if useful, e.g.:

```text
visibility-runtime.mjs
```

Responsibilities:

```text
capture initial visibility
cache relevant nodes
apply named preset
restore default
```

Scene traversal should happen once after GLB load.

Do not traverse 6,000+ nodes for every click.

---

# 13. LIVE panel redesign

Replace the current text-heavy panel with compact sections/cards.

Target:

```text
┌───────────────────────┐
│ LIVE — MOCK DATA      │
│ ● CONNECTED           │
├───────────────────────┤
│ INDOOR                │
│ 28.4 °C      74 %RH   │
│ VPD 0.88     CO₂ 412  │
├───────────────────────┤
│ OUTDOOR               │
│ 24.1 °C      432 W/m² │
│ Wind 1.6 m/s   NE     │
├───────────────────────┤
│ ACTUATORS             │
│ Vent L   42%          │
│ Vent R   38%          │
│ Screen 1 65%          │
│ Screen 2 20%          │
├───────────────────────┤
│ Updated 18:24:01      │
└───────────────────────┘
```

---

# 14. LIVE panel hierarchy

Primary values:

```text
Indoor temperature
Indoor RH
Outdoor temperature
Solar radiation
Roof vent L/R
Shade screen 1/2
```

Secondary values:

```text
VPD
CO2
Wind speed
Wind direction
dew point
setpoint temperature
```

Primary values should have stronger typography.

---

# 15. Loading/null/stale states

Use:

```text
—
```

for unavailable values.

Before first fetch:

```text
Waiting for data…
```

For stale:

```text
STALE
Last valid update ...
```

For disconnected:

```text
DISCONNECTED
```

Keep last valid values visible unless there has never been a successful fetch.

---

# 16. Status badges

Use compact badges:

```text
MOCK DATA
CONNECTED
STALE
DISCONNECTED
```

Do not classify environmental values as good/bad in this phase.

---

# 17. Collapsible LIVE panel

Add collapse/expand control.

Desktop default: expanded.

Collapsed state: narrow tab/badge so the 3D area feels larger.

Use a simple 150–250 ms CSS transition.

---

# 18. Debug information cleanup

Remove permanent bottom debug text from normal view.

Move mapping information such as:

```text
RoofVent_L 2/2 provisional
RoofVent_R 2/2 provisional
ShadeScreen_01 4/4
ShadeScreen_02 4/4 provisional
```

to a developer/debug drawer.

---

# 19. Developer drawer

Add a hidden-by-default Developer drawer showing:

```text
GLB load status
scene node count
matched roof vents
matched shade screens
matched diffuse screens
matched side curtains
current data source
connection state
provisional mappings
current camera preset
last API success time
```

Do not expose credentials or secrets.

---

# 20. Object hover/select

Add lightweight inspection for:

```text
roof vents
shade screens
diffuse screens
side curtains
sensor anchors
```

Use raycasting.

On hover:

```text
pointer cursor
lightweight highlight
tooltip
```

On click:

```text
persistent selection
compact detail panel
```

---

# 21. Highlight implementation

Avoid permanent material mutation.

Preferred:

```text
temporary emissive change if supported
temporary color intensity
```

Do not add heavy post-processing or EffectComposer unless already present.

Store and restore original material state.

---

# 22. Tooltip content

Examples:

Roof vent:

```text
Roof Vent — Span 1
Opening 42%
Status: Provisional L mapping
```

Shade screen:

```text
Shade Screen — Span 2
Opening 65%
```

Sensor:

```text
T/RH Sensor
Position: unverified
```

Use actual userData fields where present.

Do not invent verified physical meaning.

---

# 23. Selection details

Selected-object panel may show:

```text
name
asset type
span index
control variable
opening percent
verified/unverified
source confidence
```

Only show fields that exist.

---

# 24. Background and ground

Keep dark background but not pure black.

Ensure ground plane is visible enough to give scale.

Optional subtle grid is allowed, but must not dominate.

---

# 25. Material/readability refinements

Do not replace Blender materials wholesale.

Allowed:

```text
renderer tone mapping if useful
output color space
neutral lighting
transparent-material corrections
```

Check cover/screen transparency artifacts.

If necessary, adjust only affected materials:

```javascript
material.transparent = true;
material.depthWrite = false;
```

Do not globally disable depthWrite.

---

# 26. Renderer quality

Use sensible settings:

```text
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
renderer.outputColorSpace = THREE.SRGBColorSpace
```

Use antialiasing if already available.

Avoid expensive real-time shadows unless performance remains clearly acceptable.

---

# 27. Resize handling

On window resize update:

```text
renderer size
camera aspect
camera projection matrix
```

The LIVE panel must not obscure most of the model.

---

# 28. Performance rules

The model contains thousands of nodes.

Rules:

```text
scene.traverse → once after load
raycast → interactable targets only
DOM updates → live data updates only
render loop → controls + camera interpolation + actuator interpolation + render
visibility → cached nodes
```

Do not rebuild registries each frame.

---

# 29. OrbitControls

Use damping.

Set reasonable:

```text
minDistance
maxDistance
maxPolarAngle
```

Prevent accidental below-ground navigation if practical.

Do not over-constrain.

---

# 30. Reset View

Add a Reset View control.

It should:

```text
restore Overview
restore default visibility
clear selection
```

No page reload.

---

# 31. Fullscreen

If dependency-free and easy, add a Fullscreen control via browser Fullscreen API.

Keep it optional if it would destabilize the viewer.

---

# 32. Layer controls

Add compact high-level layer toggles if feasible:

```text
Cover
Crops
Equipment
Sensors
Controls
```

Use cached references.

Do not expose individual thousands of nodes.

If a category does not exist, hide or disable the toggle.

---

# 33. Text/typography

Use concise English labels consistently:

```text
Greenhouse Digital Twin
Indoor
Outdoor
Actuators
Overview
Front
Rear
Roof
Interior
Equipment
Control
Reset
Developer
```

Use system fonts only.

Recommended hierarchy:

```text
header title
section label
primary metric
secondary metric
caption
```

---

# 34. Spacing/color system

Use CSS variables.

Suggested semantic tokens:

```text
--bg
--panel
--panel-border
--text
--text-muted
--accent
--success
--warning
--danger
```

Use a consistent spacing scale:

```text
4 / 8 / 12 / 16 / 24 / 32
```

Avoid scattered arbitrary values.

No excessive green tint or neon.

---

# 35. Responsive behavior

Desktop:
- LIVE panel floats right.
- toolbar sits bottom or lower center.

Narrow viewport:
- LIVE panel becomes overlay/collapsible.
- toolbar wraps or horizontal-scrolls.
- header compacts.

Do not over-invest in mobile polish.

---

# 36. Loading experience

During GLB load:

```text
Loading greenhouse model…
```

Use progress percentage if available.

On failure:

```text
Failed to load greenhouse model
```

Put technical details in Developer drawer.

---

# 37. Mock-only wording

Normal UI must make this explicit:

```text
MOCK DATA
LOCAL
NO FIELD CONTROL
```

Do not imply actual farm connectivity.

Keep this clear but visually subdued.

---

# 38. Mapping uncertainty

Normal dashboard should not show implementation uncertainty clutter.

Keep these in Developer drawer/selection details:

```text
RoofVent_L → S01/S02
RoofVent_R → S03/S04
ShadeScreen_02 → diffuse layer
35° max vent angle is visual placeholder
```

---

# 39. Config centralization

Create or extend:

```text
live-config.mjs
viewer-config.mjs
```

for:

```text
camera fit margin
transition duration
camera presets
object groups
UI thresholds
```

Do not duplicate constants across files.

---

# 40. Suggested module organization

Use only where useful:

```text
viewer.mjs
viewer-config.mjs
camera-runtime.mjs
visibility-runtime.mjs
interaction-runtime.mjs
live-panel.mjs
actuator-runtime.mjs
```

Do not over-split tiny logic.

---

# 41. Tests

Preserve all existing tests.

Add focused frontend tests for pure logic where possible:

```text
camera preset config exists
visibility preset mapping
registry classification
tooltip formatting
status badge mapping
null formatting
```

Continue using the existing Node test runner.

Do not introduce Jest/Vitest.

---

# 42. Browser acceptance

Verify:

```text
GET / → 200
GLB loads
viewer renders
LIVE panel visible
camera presets clickable
Reset View works
Developer drawer opens/closes
mock values still update
roof vents still move
screens still move
no console error loop
```

If browser automation is available, use it.

Otherwise do HTTP/static checks and document the manual visual verification.

---

# 43. Manual visual acceptance checklist

At 1440×900:

```text
[ ] greenhouse occupies most of viewport
[ ] greenhouse is not tiny
[ ] LIVE panel does not dominate
[ ] header is compact
[ ] no permanent debug block
[ ] camera buttons are readable
[ ] Overview looks balanced
[ ] Front orientation is correct
[ ] Rear orientation is correct
[ ] Interior reveals crops
[ ] Equipment reveals service zone
[ ] Control emphasizes controllable nodes
[ ] hover/select is understandable
[ ] mock status is obvious
[ ] overall interface looks presentation-ready
```

---

# 44. README update

Rename/document:

```text
Phase 1.8 — 3D Viewer & Dashboard UI/UX Refinement
```

Document only:

```text
camera presets
visibility presets
LIVE panel behavior
developer drawer
object hover/select
layer controls
reset/fullscreen
desktop-first target
known provisional mappings
run commands
```

Do not copy this entire spec into README.

---

# 45. No backend expansion

Do not add:

```text
database models
new control endpoints
new authentication
logging database
new API fields unless strictly required
```

If a value is not in the normalized DTO, omit it rather than expanding backend scope casually.

---

# 46. No network phase creep

Source remains:

```text
mock_static
or
mock_dynamic
```

Actual read-only Growlink bridge is the next phase.

---

# 47. Implementation order

Follow:

```text
1. inspect current viewer/template/CSS
2. inspect live panel and actuator runtime
3. improve base layout/header
4. improve initial camera auto-fit
5. add camera preset runtime
6. add visibility preset runtime
7. redesign LIVE panel
8. move debug info to Developer drawer
9. add Reset View
10. add object raycast hover/select
11. add tooltip/selection detail
12. add optional layer toggles
13. refine renderer/material readability
14. refine responsive behavior
15. run tests
16. perform browser acceptance
17. update README
```

Do not start with decorative CSS before camera/layout fundamentals.

---

# 48. Acceptance criteria

Phase 1.8 is complete only when:

```text
[ ] Phase 1.7 server still runs
[ ] API still works
[ ] mock_dynamic still updates
[ ] greenhouse fills viewport much better
[ ] header is compact
[ ] LIVE panel is visually structured
[ ] panel can collapse
[ ] debug mapping text is hidden by default
[ ] Developer drawer exists
[ ] camera presets exist
[ ] Front/Rear follow Phase 1.6 orientation
[ ] Interior/Equipment/Control views work
[ ] Reset View works
[ ] visibility presets work
[ ] hover/select works for key assets
[ ] tooltip/detail uses actual metadata
[ ] actuator animation still works
[ ] no per-frame scene traversal
[ ] no major console errors
[ ] tests pass
[ ] README updated
[ ] no real field connection code added
```

---

# 49. Stop conditions

Do not stop for rough CSS, missing camera presets, missing tooltip, or missing Developer drawer; those are the tasks.

Only ask for user input if:

```text
viewer files are missing/corrupt
GLB no longer loads
project structure conflicts with Phase 1.7 README
```

For visual ambiguity, choose a conservative engineering-dashboard design and continue.

---

# 50. Final Codex report

Return only:

```text
Phase 1.8 — UI/UX refinement result

Created
- ...

Modified
- ...

Viewer
- initial framing:
- camera presets:
- visibility presets:
- hover/select:
- live panel:
- developer drawer:
- layer controls:

Performance
- scene traversal strategy:
- raycast target strategy:
- render-loop responsibilities:

Verified
- root page:
- API:
- GLB:
- mock updates:
- actuator animation:
- frontend tests:
- Python tests:

Known provisional items
- ...

Manual visual checks still recommended
- ...

Next phase handoff
- actual read-only Growlink bridge
```

---

# Final instruction

Implement Phase 1.8 as a **presentation-ready 3D digital twin viewer refinement**.

Do not change the working data architecture.
Do not add real field connectivity.

Make the 3D greenhouse visually dominant, improve camera/navigation, make LIVE information easy to scan, hide developer noise by default, and make the interface look deliberate rather than prototype-like.
