# Codex Implementation Brief — Phase 1.8.1
## Interactive Spatial Navigation, Context-Aware Digital Twin UI, and Visual Readability Refinement

> **Project stage**
> - Phase 1.6: Operational greenhouse geometry and GLB contract complete.
> - Phase 1.7: Runnable Django + Three.js local viewer complete.
> - Phase 1.8: Viewer/dashboard visual refinement complete enough to show a usable 3D dashboard.
>
> **This phase changes the interaction model.**
>
> The viewer should no longer feel like:
>
> `3D model + permanent status panel`
>
> It should behave like:
>
> `3D greenhouse → spatial selection → object selection → contextual data`
>
> The 3D greenhouse itself must become the primary interface.

---

# 0. Source of truth and implementation behavior

Use this document as the implementation source of truth for this phase.

Before editing:

1. Inspect the existing Phase 1.8 viewer implementation.
2. Inspect the current README Phase 1.7/1.8 sections.
3. Inspect the current Three.js scene structure, object registry, camera preset implementation, visibility controls, LIVE panel implementation, and GLB metadata usage.
4. Inspect the Phase 1.6 GLB object contract and existing `span_index`, `asset_type`, `controllable`, `control_variable`, and other `userData` fields.
5. Do not assume missing sensor or actuator mappings.

Before implementation, print only:

```text
Relevant files
Implementation plan
Files to create/modify
```

Then implement directly.

Do not stop for normal UI/design ambiguity. Use the conservative engineering-dashboard rules in this specification.

---

# 1. Main objective

Convert the current viewer from a passive monitoring screen into a spatially navigable Digital Twin interface.

The interaction hierarchy must be:

```text
GREENHOUSE
↓
SPAN
↓
ASSET
↓
CONTEXTUAL DATA
```

The user should be able to navigate primarily through the 3D model rather than through unrelated menus.

---

# 2. Core selection model

Implement one unified selection state.

Recommended structure:

```javascript
selectionState = {
  level: "greenhouse" | "span" | "asset",
  spanId: null | "S01" | "S02" | "S03" | "S04",
  assetId: null | string,
  assetType: null | string
}
```

This state must drive:

```text
span selector
3D highlight
camera focus
context panel
breadcrumb
floating label
Back / Overview navigation
developer information
```

Do not implement these systems as unrelated states.

---

# 3. Spatial selection — ALL / S1 / S2 / S3 / S4

Add a dedicated spatial selector.

Desktop UI:

```text
GREENHOUSE

[ ALL ] [ S1 ] [ S2 ] [ S3 ] [ S4 ]
```

Do not mix spatial selection with camera presets.

Meaning:

```text
Span selector = WHERE the user is looking
Camera preset = HOW the user is looking
```

Required behavior:

## ALL

```text
selection.level = greenhouse
selection.spanId = null
selection.assetId = null
```

- restore full greenhouse focus
- restore normal span emphasis
- context panel becomes GREENHOUSE OVERVIEW

## S1–S4

Example:

```text
S2
→ selection.level = span
→ spanId = S02
```

Then:

```text
selected span = emphasized
other spans = visually de-emphasized
camera = smooth fit to selected span
context panel = SPAN 02
breadcrumb = Greenhouse / Span 02
```

---

# 4. Span detection

Use the GLB metadata and naming contract.

Primary source:

```text
userData.span_index
```

Fallback only if required:

```text
object names containing S01 / S02 / S03 / S04
```

Do not create fake span membership for objects with no span information.

Create and cache:

```text
spanRegistry.S01
spanRegistry.S02
spanRegistry.S03
spanRegistry.S04
```

Each registry entry should contain references to relevant scene objects.

Scene traversal should occur once after GLB load.

Do not repeatedly traverse the full scene for each span click.

---

# 5. Span de-emphasis behavior

Do not simply make all non-selected spans fully transparent.

The greenhouse already contains transparent cover/screens, so excessive opacity manipulation may create depth-sorting artifacts.

Preferred behavior:

```text
selected span
→ normal brightness/material

non-selected spans
→ muted / darker / desaturated / lower visual emphasis
```

If opacity is used, apply it selectively and conservatively.

Do not destroy original materials.

Cache original material state.

---

# 6. Direct 3D span picking

The user must also be able to select a span directly from the 3D model.

Hover:

```text
span under pointer
→ subtle emphasis
→ pointer cursor
→ optional small "Span 02" label
```

Click:

```text
span selected
→ same result as S2 button
```

The button selection and 3D selection must remain synchronized.

---

# 7. 3D asset picking

Support clicking these asset categories:

```text
Roof Vent
Shade Screen
Diffuse Screen
Side Curtain
Sensor
Fertigation Equipment
```

Crop Zone should initially be treated as a focus/visibility target, not as a data-rich live asset unless real data exists.

Do not create fake crop metrics.

---

# 8. Asset registry

Create a cached interactable registry after GLB load.

Use:

```text
userData.asset_type
userData.controllable
userData.control_variable
userData.span_index
object names
known root groups
```

Do not raycast against the entire 6,000+ node scene if avoidable.

Build a reduced raycast target list.

---

# 9. Asset click behavior

When an asset is clicked:

```text
selection.level = asset
selection.spanId = asset span if known
selection.assetId = object id/name
selection.assetType = asset type
```

Then:

```text
object highlight
camera focus
context panel update
floating label
breadcrumb update
```

Example:

```text
Greenhouse / Span 02 / Roof Vent
```

---

# 10. Camera focus

Implement `fitSelected()`.

Use actual Three.js bounds:

```text
THREE.Box3
THREE.Sphere
```

Do not hardcode a camera location for every individual object.

Required flow:

```text
selected object/group bounds
→ center
→ radius/max extent
→ target camera position
→ smooth transition
```

Transition duration:

```text
~400–700 ms
```

Use requestAnimationFrame-based interpolation.

Do not add an animation library.

---

# 11. Camera presets remain separate

Keep:

```text
Overview
Front
Rear
Roof
Interior
Equipment
Control
```

These are camera/view presets only.

Do not convert these into span selection.

If S2 is selected and the user presses Roof:

```text
the Roof preset should orient the camera relative to the selected context
```

If this becomes too complex, preserve selected span and fit the selected span after applying the preset orientation.

---

# 12. Breadcrumb navigation

Add a compact breadcrumb in the Context Panel header.

Examples:

```text
Greenhouse

Greenhouse / Span 02

Greenhouse / Span 02 / Roof Vent
```

Clicking:

```text
Greenhouse
→ return to greenhouse level

Span 02
→ return to span level
```

Do not require the user to hunt for a separate menu.

---

# 13. Context Panel redesign

The right panel must become a Context Panel.

It must not permanently show the same full snapshot.

It should render different content depending on the selection level.

---

# 14. Greenhouse-level Context Panel

When nothing specific is selected:

```text
GREENHOUSE OVERVIEW
```

Show only high-level data:

```text
Indoor Temperature
Relative Humidity
Solar Radiation
System Status
Data Source
Last Update
```

Optional:

```text
Active Alert Count
```

However, do not fabricate alerts.

If no alert engine exists:

```text
Alerts: Not configured
```

or omit the field.

Do not show all actuator details at greenhouse level.

---

# 15. Span-level Context Panel

Example:

```text
SPAN 02
```

Show:

```text
ACTUATORS
Roof Vent
Shade Screen
Diffuse Screen
Side Curtain

REPRESENTATIVE ENVIRONMENT
Indoor Temperature
RH
VPD
```

Important:

The environment values are NOT span-specific unless a real span sensor exists.

Therefore clearly label:

```text
Representative Environment
House-level sensor
Not span-specific
```

Do not imply that each span has independent T/RH data.

If sensor ownership is unknown, do not list a span-specific sensor.

---

# 16. Asset-level Context Panel

Example:

```text
ROOF VENT — SPAN 02
```

Show only fields supported by current data/metadata:

```text
Opening
State
Control Variable
Span
Mapped Channel
Source
Last Update
Mapping Status
```

Example:

```text
Opening        74%
Control        opening_percent
Mapped channel RoofVent_L
Mapping        Provisional
Source         MOCK
```

Do not invent `OPENING`, `CLOSING`, or motor state unless such state is actually present.

If only opening percent exists, omit `State` or use only a clearly documented visualization classification.

---

# 17. History tab

Add the UI shell:

```text
LIVE | HISTORY | DETAILS
```

But do not implement fake historical data.

Current phase behavior:

```text
LIVE
→ functional

DETAILS
→ functional using metadata

HISTORY
→ disabled / empty state
```

Example:

```text
History is not available in the current mock-only phase.
Historical logging will be added with the live data bridge.
```

Do not generate mock trends that could be mistaken for real history.

---

# 18. Details tab

For selected asset, show metadata fields that exist:

```text
name
asset_type
span_index
control_variable
opening_percent
source_confidence
geometry_confidence
position_confidence
verified_position
plc_tag_verified
```

Only render existing fields.

Use `—` for unavailable values.

---

# 19. Layer UI

Split actual visibility layers from overlays.

Use:

```text
LAYERS
[ ] Cover
[ ] Crops
[ ] Equipment
[ ] Sensors

OVERLAYS
[ ] Control State
[ ] Labels
```

Do not treat `Control` as a normal mesh layer.

---

# 20. Floating labels / HUD

Labels are contextual, not permanent.

Priority:

```text
Selected object → always show
Hovered object → temporary
Alarm object → always show when alert system exists
Normal object → hidden
```

Example:

```text
Roof Vent S2
74%
```

Sensor example:

```text
T/RH Sensor
27.9°C / 66%
```

Only show the sensor value if it is actually mapped to that sensor.

---

# 21. Status color system

Keep normal UI calm.

Use:

```text
Normal   neutral
Selected cyan/teal
Offline  gray
```

Reserve:

```text
Warning amber
Critical red
```

for a later phase when actual alert rules exist.

Do not mark environmental values as warning/critical without defined thresholds.

---

# 22. No excessive futuristic neon UI

This is a research/engineering Digital Twin.

It must NOT look like a sci-fi cockpit.

Avoid:

```text
strong neon glow
bright cyan everywhere
large holographic outlines
animated grid backgrounds
scan lines
heavy bloom
excessive gradients
oversaturated panels
game-style HUD decoration
```

Preferred style:

```text
dark industrial
engineering UI
minimal
restrained
high-information
subtle glass
thin borders
clear hierarchy
```

---

# 23. Background redesign

Do not use pure black.

The current black background reduces roof-vent readability.

Use a dark charcoal / blue-gray background.

Create semantic variables:

```text
--bg-main
--bg-viewport
--panel-bg
--panel-border
--text-primary
--text-secondary
--accent
--selected
--offline
```

---

# 24. Roof vent readability — critical requirement

The user must be able to visually tell whether roof vents are open or closed.

Current problem:

```text
dark background
+
dark frame/roof
+
subtle vent rotation
=
opening state difficult to see
```

Improve this with a combination of:

```text
background contrast
material contrast
lighting direction
selected-state edge emphasis
control-view de-emphasis
optional local label
```

Do not solve this by turning all vents neon cyan.

---

# 25. Directional lighting

Add or tune a directional light so roof geometry reads clearly.

The light should create visible differences between:

```text
closed roof surface
partially open vent
fully open vent
```

Avoid flat ambient-only appearance and avoid expensive cinematic lighting.

Do not enable shadows unless performance remains acceptable and the benefit is clear.

---

# 26. Hover / selected vent emphasis

Normal:

```text
no glow
no strong outline
```

Hover:

```text
subtle cyan/teal edge/material emphasis
```

Selected:

```text
stronger but restrained highlight
label visible
context panel visible
```

If a vent is open, the angle should remain readable even without selection.

---

# 27. Control View visual behavior

When `Control` view or `Control State` overlay is active:

```text
structure → muted
cover → more transparent if useful
crops → de-emphasized
actuators → visually emphasized
sensors → visible as markers if Sensors layer enabled
```

Do not recolor all assets.

---

# 28. Navigation controls

Keep only practical controls:

```text
Reset Camera
Fit Selected
Fullscreen
Back to Overview
```

Optional:

```text
Auto Rotate
Interior Walk Mode
```

Optional controls must not block completion.

---

# 29. Data source status

Always show:

```text
MOCK
LIVE
DISCONNECTED
```

Current implementation remains mock-only.

Recommended compact status:

```text
MOCK DATA
LOCAL
NO FIELD CONTROL
```

---

# 30. Sensor modeling constraints

Current project constraints:

- Detailed environmental sensing is not known to exist independently for every span.
- Do not generate S1/S2/S3/S4 environmental values.
- Use house-level representative values only.
- Sensor location/ownership may be provisional/unverified.

Therefore:

```text
do not present per-span temperature
do not present per-span RH
do not imply per-span sensor coverage
```

unless an actual mapped sensor is verified.

---

# 31. Fertigation equipment

Support picking only at useful group/asset level.

Recommended:

```text
tank group
pump
blower
filter group
control panel
```

Avoid making every small sub-part an interactive target.

---

# 32. Crop Zone

Do not create fake crop analytics.

Crop Zone may support:

```text
focus
visibility
selection label
metadata
```

Do not show yield, stress, growth, health, or irrigation demand without real data/model support.

---

# 33. History and alerts — current phase boundary

Do not implement real alert evaluation.

Do not implement real history storage.

This phase may prepare:

```text
History tab shell
Alert UI placeholder
status badge component
```

but no fake analytics.

---

# 34. Performance rules

The scene contains thousands of nodes.

Requirements:

```text
full scene traversal → once after GLB load
span registry → cached
asset registry → cached
layer registry → cached
raycast targets → reduced set
DOM updates → only on state/data changes
render loop → camera interpolation + actuator interpolation + controls + render
```

Do not:

```text
traverse scene every frame
rebuild registries every click
raycast all decorative nodes
clone every material unnecessarily
```

---

# 35. Module organization

Use the existing project structure where possible.

Suggested separation:

```text
viewer.mjs
viewer-config.mjs
selection-runtime.mjs
camera-runtime.mjs
visibility-runtime.mjs
interaction-runtime.mjs
context-panel.mjs
label-runtime.mjs
actuator-runtime.mjs
```

Do not create unnecessary tiny modules if current files already cover these responsibilities cleanly.

---

# 36. Material highlight safety

Do not modify transform or animation state to show selection.

Selection styling must be separate from actuator motion.

Store original material properties before highlight.

Handle shared materials carefully.

If changing a shared material would highlight unrelated objects, clone only the selected interactable material as needed.

Do not clone the entire scene.

---

# 37. Manual browser acceptance

Verify at 1440×900.

## General

```text
[ ] greenhouse is clearly visible against the background
[ ] roof vents can visually be distinguished when open
[ ] no excessive neon/glow styling
[ ] UI feels like engineering software, not a sci-fi HUD
```

## Spatial navigation

```text
[ ] ALL works
[ ] S1 works
[ ] S2 works
[ ] S3 works
[ ] S4 works
[ ] selected span is clear
[ ] non-selected spans are de-emphasized
[ ] camera moves smoothly
```

## Object selection

```text
[ ] roof vent picking works
[ ] shade screen picking works
[ ] diffuse screen picking works
[ ] sensor picking works where available
[ ] equipment picking works at useful group level
[ ] selected object is highlighted
[ ] context panel updates
```

## Navigation

```text
[ ] breadcrumb works
[ ] Back to Overview works
[ ] Fit Selected works
[ ] Reset Camera works
[ ] camera presets still work
```

## Data integrity

```text
[ ] no fake span temperature
[ ] no fake span RH
[ ] representative environment is labeled correctly
[ ] mock source is visible
[ ] history does not fabricate data
[ ] alerts do not fabricate rules
```

## Performance

```text
[ ] no per-frame scene traversal
[ ] no console error loop
[ ] hover remains responsive
[ ] actuator animation remains smooth
```

---

# 38. Implementation order

Follow this order:

```text
1. inspect existing Phase 1.8 runtime
2. create unified selection state
3. build cached span registry
4. build cached interactable asset registry
5. implement ALL/S1/S2/S3/S4 selector
6. implement direct 3D span selection
7. implement asset picking
8. implement breadcrumb
9. convert right panel to context panel
10. implement fitSelected camera behavior
11. implement span/object visual emphasis
12. separate layers and overlays
13. implement selected/hover labels
14. improve background
15. improve vent material readability
16. tune directional lighting
17. refine Control View
18. add History disabled shell
19. add tests
20. run browser acceptance
21. update README
```

Do not begin with decorative polish before selection architecture is working.

---

# 39. Execution commands

Use the existing virtual environment named `sfes`.

From the project root in PowerShell:

```powershell
.\sfes\Scripts\Activate.ps1
```

If dependencies are already installed, do not recreate the environment.

Install requirements only if needed:

```powershell
python -m pip install -r requirements.txt
```

Synchronize GLB:

```powershell
python scripts/sync_web_assets.py
```

Django check:

```powershell
python manage.py check
```

Python tests:

```powershell
python -m unittest discover -s tests -v
```

Existing frontend tests:

```powershell
node --test tests/frontend_phase17.test.mjs
```

If a new Phase 1.8.1 frontend test is added:

```powershell
node --test tests/frontend_phase18_1.test.mjs
```

If all current `.test.mjs` files are compatible:

```powershell
node --test tests/*.test.mjs
```

Check GLB sync if supported:

```powershell
python scripts/sync_web_assets.py --check
```

Run server:

```powershell
python manage.py runserver 127.0.0.1:8010
```

Open:

```text
http://127.0.0.1:8010/
```

Do not use port 8000 for this local viewer.

---

# 40. README update

Add a concise section:

```text
Phase 1.8.1 — Interactive Spatial Navigation
```

Document:

```text
Greenhouse → Span → Asset navigation
ALL/S1/S2/S3/S4 selector
3D direct selection
Context Panel
breadcrumb
Fit Selected
layer vs overlay distinction
house-level representative sensor constraint
history placeholder
alert limitation
dark slate visual direction
roof vent readability improvements
run/test commands
```

Do not copy this full implementation brief into README.

---

# 41. Explicitly out of scope

Do not implement:

```text
actual Growlink connection
PLC connection
PLC commands
write endpoints
real historical logging
real alert engine
MPC
thermal model
radiation ray tracing
weather forecast
crop analytics
span-specific environmental values without sensors
database-backed history
```

---

# 42. Completion criteria

Phase 1.8.1 is complete only when:

```text
[ ] 3D greenhouse is the primary interaction surface
[ ] unified Greenhouse/Span/Asset selection state exists
[ ] ALL/S1/S2/S3/S4 selection works
[ ] direct 3D span picking works
[ ] direct asset picking works
[ ] camera smoothly focuses selected context
[ ] right panel is context-aware
[ ] breadcrumb works
[ ] no fake per-span environmental data exists
[ ] layers and overlays are separated
[ ] floating labels are contextual
[ ] dark background no longer hides roof vent state
[ ] vent opening is visually readable
[ ] UI avoids sci-fi neon styling
[ ] mock/live source remains explicit
[ ] History does not fabricate data
[ ] alerts do not fabricate rules
[ ] actuator animation still works
[ ] no expensive per-frame scene traversal
[ ] Python tests pass
[ ] frontend tests pass
[ ] README is updated
```

---

# 43. Final Codex report format

Return only:

```text
Phase 1.8.1 — Interactive Spatial Navigation result

Created
- ...

Modified
- ...

Selection architecture
- greenhouse:
- span:
- asset:

Spatial navigation
- ALL/S1/S2/S3/S4:
- direct span picking:
- camera focus:
- span de-emphasis:

Asset interaction
- roof vents:
- screens:
- sensors:
- equipment:
- crop zone:

Context panel
- greenhouse:
- span:
- asset:
- breadcrumb:
- history:
- details:

Visual refinement
- background:
- roof vent readability:
- lighting:
- selected state:
- neon/glow restraint:

Layers / overlays
- ...

Performance
- scene traversal:
- cached registries:
- raycasting:
- render loop:

Verified
- Django check:
- Python tests:
- frontend tests:
- GLB:
- mock polling:
- actuator animation:
- browser acceptance:

Known limitations
- ...

Next phase handoff
- read-only Growlink bridge
- historical logging
- real alert rules
```

---

# Final implementation principle

The viewer should no longer merely display a greenhouse model.

It should allow the user to understand the system through the greenhouse itself:

```text
3D SPACE
→ SELECT
→ FOCUS
→ CONTEXT
→ DATA
```

Keep the visual design restrained, technical, and credible.

Do not use excessive futuristic neon styling.

Do not let the dark background hide mechanical state.

Roof vents, screens, sensors, and selected spans must remain visually understandable without sacrificing the calm engineering-dashboard appearance.
