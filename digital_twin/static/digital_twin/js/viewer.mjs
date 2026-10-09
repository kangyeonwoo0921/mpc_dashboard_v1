import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

import { CameraRuntime } from "./camera-runtime.mjs";
import { ContextPanelRuntime } from "./context-panel.mjs";
import { InteractionRuntime } from "./interaction-runtime.mjs";
import { mappedAssetContext } from "./live-config.mjs";
import { LabelRuntime } from "./label-runtime.mjs";
import { buildSceneRegistry } from "./scene-registry.mjs";
import { SelectionRuntime } from "./selection-runtime.mjs";
import { SOLAR_CONFIG, SOLAR_ENDPOINTS, SolarRuntime } from "./solar-runtime.mjs";
import { createLiveViewerIntegration } from "./viewer-live-integration.mjs";
import { CAMERA_PRESETS, SCENE_COLORS, VIEWER_UI_CONFIG } from "./viewer-config.mjs";
import { VisibilityRuntime } from "./visibility-runtime.mjs";

const shell = document.getElementById("digital-twin-viewer");
const canvas = document.getElementById("greenhouse-canvas");
const message = document.getElementById("viewer-message");
const contextRoot = document.getElementById("context-panel");
const mappingStatusRoot = document.getElementById("mapping-status");
const developerDrawer = document.getElementById("developer-drawer");
const developerToggle = document.getElementById("developer-toggle");
const tooltipRoot = document.getElementById("object-tooltip");
const selectedLabelRoot = document.getElementById("selected-label");

const scene = new THREE.Scene();
scene.background = new THREE.Color(SCENE_COLORS.background);
scene.fog = new THREE.FogExp2(SCENE_COLORS.fog, 0.00145);

const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 2000);
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.08;
renderer.setPixelRatio(Math.min(window.devicePixelRatio, VIEWER_UI_CONFIG.maxPixelRatio));
renderer.shadowMap.enabled = false;

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.screenSpacePanning = true;
controls.maxPolarAngle = Math.PI * 0.495;

scene.add(new THREE.HemisphereLight(0xd8e4e6, 0x344149, 1.55));
const roofKeyLight = new THREE.DirectionalLight(0xfff0d8, 3.1);
roofKeyLight.position.set(-18, 58, 36);
scene.add(roofKeyLight);
const sideFillLight = new THREE.DirectionalLight(0xa9c8d6, 1.0);
sideFillLight.position.set(42, 21, -38);
scene.add(sideFillLight);
const roofEdgeLight = new THREE.DirectionalLight(0xc7e2dc, 0.72);
roofEdgeLight.position.set(8, 34, -42);
scene.add(roofEdgeLight);

const selectionRuntime = new SelectionRuntime();
let liveIntegration = null;
let sceneRegistry = null;
let cameraRuntime = null;
let visibilityRuntime = null;
let interactionRuntime = null;
let labelRuntime = null;
let contextPanel = null;
let solarRuntime = null;
let solarTimer = null;
let solarDebounce = null;
const clock = new THREE.Clock();

function siteDate() {
  // Site-local calendar date; the server applies the site timezone to naive times.
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
}

function renderSolarReadout(payload, error = null) {
  const node = shell.querySelector("[data-solar-readout]");
  if (!node) return;
  if (error) {
    node.textContent = "Sun model unavailable";
    return;
  }
  const time = payload.timestamp.slice(11, 16);
  const sun = payload.sun.altitude_deg > 0
    ? `Sun ${payload.sun.altitude_deg.toFixed(0)}° / ${payload.sun.azimuth_deg.toFixed(0)}°`
    : "Sun below horizon";
  const { status, sunlitFraction, mean, unit } = payload.summary;
  const light = mean === null || mean === undefined ? `radiation: ${status}` : `${mean.toFixed(0)} ${unit}`;
  const sunlit = sunlitFraction === null || sunlitFraction === undefined ? "" : ` · sunlit ${(sunlitFraction * 100).toFixed(0)}%`;
  node.textContent = `${time} · ${sun}${sunlit} · ${light}`;
}

function refreshSolar(time = null) {
  if (!solarRuntime) return;
  solarRuntime.refresh(time).then(() => renderSolarReadout(solarRuntime.state)).catch((error) => renderSolarReadout(null, error));
}

// Optional deep link, e.g. ?time=09:30&lightmap=1&view=interior
function applySolarUrlOptions(params) {
  const view = params.get("view");
  if (view && CAMERA_PRESETS[view]) activatePreset(view, { immediate: true });
  if (params.get("lightmap") === "1") {
    const toggle = shell.querySelector('[data-solar="lightMap"]');
    if (toggle) toggle.checked = true;
    solarRuntime.setLightMapEnabled(true);
  }
  const match = /^(\d{1,2}):(\d{2})$/.exec(params.get("time") ?? "");
  if (!match) {
    setSolarLive(true);
    return;
  }
  const slider = shell.querySelector("[data-solar-time]");
  if (slider) slider.value = String(Number(match[1]) * 60 + Number(match[2]));
  setSolarLive(false);
  refreshSolar(`${siteDate()}T${match[1].padStart(2, "0")}:${match[2]}`);
}

function setSolarLive(live) {
  shell.querySelector("[data-solar-now]")?.setAttribute("aria-pressed", String(live));
  clearInterval(solarTimer);
  if (live) {
    refreshSolar();
    solarTimer = setInterval(() => refreshSolar(), SOLAR_CONFIG.refreshMs);
  }
}

function setDevField(name, value) {
  const node = shell.querySelector(`[data-dev-field="${name}"]`);
  if (node) node.textContent = value;
}

function resize() {
  const width = Math.max(shell.clientWidth, 1);
  const height = Math.max(shell.clientHeight, 1);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  cameraRuntime?.refitCurrent({ immediate: true });
}

function setActivePreset(name) {
  shell.querySelectorAll("[data-view-preset]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.viewPreset === name));
  });
  setDevField("cameraPreset", CAMERA_PRESETS[name]?.label ?? name);
}

function syncSpanSelector(selection) {
  const selected = selection.level === "greenhouse" ? "ALL" : selection.spanId ?? "ALL";
  shell.querySelectorAll("[data-span-select]").forEach((button) => {
    const id = button.dataset.spanSelect;
    button.disabled = id !== "ALL" && !sceneRegistry?.spanRegistry[id]?.available;
    button.setAttribute("aria-pressed", String(button.dataset.spanSelect === selected));
  });
}

function syncLayerControls() {
  if (!visibilityRuntime) return;
  const available = visibilityRuntime.availableLayers();
  shell.querySelectorAll("[data-layer]").forEach((input) => {
    const name = input.dataset.layer;
    input.disabled = !available[name];
    input.checked = Boolean(visibilityRuntime.layerState[name]);
  });
  shell.querySelectorAll("[data-overlay]").forEach((input) => {
    input.checked = Boolean(visibilityRuntime.overlayState[input.dataset.overlay]);
  });
}

function selectedEntry() {
  return sceneRegistry?.getAsset(selectionRuntime.state.assetId);
}

function selectedBounds() {
  return sceneRegistry?.getSelectionBounds(selectionRuntime.state) ?? null;
}

function mappingContext(subject) {
  return mappedAssetContext(subject?.entry ?? subject, liveIntegration?.state);
}

function renderContext(now = Date.now()) {
  if (!contextPanel || !liveIntegration) return;
  const entry = selectedEntry();
  contextPanel.update({
    selection: selectionRuntime.state,
    liveState: liveIntegration.state,
    assetEntry: entry,
    assetContext: mappingContext(entry),
    spanAssets: sceneRegistry?.spanRegistry[selectionRuntime.state.spanId]?.assets ?? [],
    now,
  });
}

function updateSelectionLabel() {
  if (!labelRuntime || !sceneRegistry) return;
  const entry = selectedEntry();
  labelRuntime.setSelection(selectionRuntime.state, {
    entry,
    bounds: selectedBounds(),
    context: mappingContext(entry),
  });
}

function applySelection(selection, previous, { focus = true } = {}) {
  if (!sceneRegistry || !visibilityRuntime || !interactionRuntime) return;
  interactionRuntime.resetHighlights();
  visibilityRuntime.setSpanEmphasis(selection.spanId);
  const entry = selectedEntry();
  const selectedRecord = selection.level === "asset" && entry
    ? { kind: "asset", spanId: entry.spanId, entry, owner: entry.owner, mesh: entry.meshes[0] }
    : selection.level === "span"
      ? { kind: "span", spanId: selection.spanId }
      : null;
  interactionRuntime.setSelectedRecord(selectedRecord);
  syncSpanSelector(selection);
  setDevField("selectionLevel", selection.level);
  setDevField("selectedSpan", selection.spanId ?? "—");
  setDevField("selectedAsset", selection.assetId ?? "—");
  renderContext();
  updateSelectionLabel();
  if (focus && previous) cameraRuntime?.fitSelected(selectedBounds(), { margin: selection.level === "asset" ? 1.5 : 1.18 });
}

function activatePreset(name, { immediate = false } = {}) {
  const preset = CAMERA_PRESETS[name];
  if (!preset || !cameraRuntime || !visibilityRuntime) return;
  interactionRuntime?.resetHighlights();
  visibilityRuntime.applyPreset(preset.visibility);
  visibilityRuntime.setOverlay("controlState", name === "control");
  const bounds = selectionRuntime.state.level === "greenhouse" ? null : selectedBounds();
  cameraRuntime.goTo(name, { bounds, immediate });
  interactionRuntime?.refreshHighlights();
  setActivePreset(name);
  syncLayerControls();
}

function renderMappingStatus(status) {
  const labels = { roofVentLeft: "RoofVent_L", roofVentRight: "RoofVent_R", shadeScreen1: "ShadeScreen_01", shadeScreen2: "ShadeScreen_02" };
  mappingStatusRoot.replaceChildren();
  for (const [key, result] of Object.entries(status)) {
    const item = document.createElement("span");
    item.className = result.provisional ? "mapping-warning" : "";
    item.textContent = `${labels[key]} ${result.found}/${result.expected}${result.provisional ? " · provisional" : ""}`;
    mappingStatusRoot.append(item);
  }
}

function syncLiveChrome(state) {
  const status = state.connectionStatus();
  const source = state.source?.startsWith("mock") ? "MOCK DATA" : state.source?.toUpperCase() ?? "LOCAL";
  const updated = state.lastReceivedAt === null ? "—" : new Date(state.lastReceivedAt).toLocaleTimeString();
  const sourceNode = shell.querySelector('[data-header-field="source"]');
  const statusNode = shell.querySelector('[data-header-field="connection"]');
  const updatedNode = shell.querySelector('[data-header-field="lastUpdate"]');
  if (sourceNode) sourceNode.textContent = source;
  if (statusNode) {
    statusNode.textContent = status === "live" ? "CONNECTED" : status.toUpperCase();
    statusNode.dataset.status = status;
  }
  if (updatedNode) updatedNode.textContent = updated;
  setDevField("source", state.source ?? "—");
  setDevField("connection", status.toUpperCase());
  setDevField("lastSuccess", updated);
  renderContext();
  updateSelectionLabel();
  interactionRuntime?.refreshTooltip();
}

function renderRegistryDiagnostics(registry) {
  setDevField("nodeCount", registry.nodeCount.toLocaleString());
  setDevField("spans", String(Object.keys(registry.spanRegistry).length));
  setDevField("assets", String(registry.assetRegistry.size));
  setDevField("roofVents", String(registry.controlRegistry.roofVents.length));
  setDevField("shadeScreens", String(registry.controlRegistry.shadeScreens.length));
  setDevField("diffuseScreens", String(registry.controlRegistry.diffuseScreens.length));
  setDevField("sideCurtains", String(registry.controlRegistry.sideCurtains.length));
  setDevField("raycastTargets", String(registry.assetTargets.length));
  setDevField("spanTargets", String(registry.spanTargets.length));
}

function setDeveloperOpen(open) {
  developerDrawer.setAttribute("aria-hidden", String(!open));
  developerDrawer.inert = !open;
  developerToggle.setAttribute("aria-expanded", String(open));
}

function showError(error) {
  const detail = error instanceof Error ? error.message : String(error);
  message.hidden = false;
  message.dataset.kind = "error";
  message.textContent = "Failed to load greenhouse model";
  setDevField("glbStatus", "Failed");
  setDevField("loadDetail", detail);
}

function bindInterface() {
  shell.querySelectorAll("[data-span-select]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.spanSelect === "ALL") selectionRuntime.selectGreenhouse();
      else selectionRuntime.selectSpan(button.dataset.spanSelect);
    });
  });
  shell.querySelectorAll("[data-view-preset]").forEach((button) => {
    button.addEventListener("click", () => activatePreset(button.dataset.viewPreset));
  });
  shell.querySelectorAll("[data-layer]").forEach((input) => {
    input.addEventListener("change", () => visibilityRuntime?.setLayer(input.dataset.layer, input.checked));
  });
  shell.querySelectorAll("[data-overlay]").forEach((input) => {
    input.addEventListener("change", () => {
      const name = input.dataset.overlay;
      if (name === "labels") {
        visibilityRuntime?.setOverlay(name, input.checked);
        interactionRuntime?.setLabelsEnabled(input.checked);
        labelRuntime?.setEnabled(input.checked);
      } else {
        interactionRuntime?.resetHighlights();
        visibilityRuntime?.setOverlay(name, input.checked);
        interactionRuntime?.refreshHighlights();
      }
    });
  });
  document.getElementById("reset-view").addEventListener("click", () => {
    const bounds = selectionRuntime.state.level === "greenhouse" ? null : selectedBounds();
    cameraRuntime?.goTo("overview", { bounds });
    setActivePreset("overview");
  });
  document.getElementById("fit-selected").addEventListener("click", () => cameraRuntime?.fitSelected(selectedBounds(), { margin: 1.25 }));
  document.getElementById("back-overview").addEventListener("click", () => {
    selectionRuntime.selectGreenhouse();
    interactionRuntime?.resetHighlights();
    visibilityRuntime?.restoreDefault();
    interactionRuntime?.clearHover();
    syncLayerControls();
    cameraRuntime?.goTo("overview");
    setActivePreset("overview");
  });
  shell.querySelectorAll("[data-solar]").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.dataset.solar === "sun") solarRuntime?.setSunEnabled(input.checked);
      else solarRuntime?.setLightMapEnabled(input.checked);
    });
  });
  shell.querySelector("[data-solar-time]")?.addEventListener("input", (event) => {
    const minutes = Number(event.target.value);
    const hh = String(Math.floor(minutes / 60)).padStart(2, "0");
    const mm = String(minutes % 60).padStart(2, "0");
    setSolarLive(false);
    clearTimeout(solarDebounce);
    solarDebounce = setTimeout(() => refreshSolar(`${siteDate()}T${hh}:${mm}`), 150);
  });
  shell.querySelector("[data-solar-now]")?.addEventListener("click", () => setSolarLive(true));
  developerToggle.addEventListener("click", () => setDeveloperOpen(developerDrawer.getAttribute("aria-hidden") === "true"));
  document.getElementById("developer-close").addEventListener("click", () => setDeveloperOpen(false));
  document.getElementById("fullscreen-toggle").addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await shell.requestFullscreen();
    } catch (error) {
      setDevField("loadDetail", `Fullscreen unavailable: ${error.message}`);
    }
  });
}

resize();
bindInterface();
window.addEventListener("resize", resize);

const loader = new GLTFLoader();
loader.load(
  shell.dataset.modelUrl,
  (gltf) => {
    try {
      sceneRegistry = buildSceneRegistry(gltf.scene);
      scene.add(gltf.scene);
      visibilityRuntime = new VisibilityRuntime(sceneRegistry);
      cameraRuntime = new CameraRuntime({ camera, controls, registry: sceneRegistry, onPresetChange: (name) => setActivePreset(name) });
      labelRuntime = new LabelRuntime({ root: selectedLabelRoot, camera, domElement: renderer.domElement });
      contextPanel = new ContextPanelRuntime(contextRoot, {
        onNavigate(item) {
          if (item.level === "greenhouse") selectionRuntime.selectGreenhouse();
          else if (item.level === "span") selectionRuntime.selectSpan(item.spanId);
        },
      });
      interactionRuntime = new InteractionRuntime({
        camera,
        domElement: renderer.domElement,
        registry: sceneRegistry,
        tooltipRoot,
        contextForRecord: (record) => mappingContext(record.entry ?? record.owner),
        onPick(record) {
          if (record.kind === "asset") selectionRuntime.selectAsset(record.entry);
          else selectionRuntime.selectSpan(record.spanId);
        },
      });
      liveIntegration = createLiveViewerIntegration({
        scene: gltf.scene,
        panelRoot: null,
        sceneRegistry,
        onStateChange: syncLiveChrome,
      });
      renderRegistryDiagnostics(sceneRegistry);
      renderMappingStatus(liveIntegration.mappingStatus);
      cameraRuntime.goTo("overview", { immediate: true });
      selectionRuntime.subscribe((selection, previous) => applySelection(selection, previous), { emitCurrent: false });
      applySelection(selectionRuntime.state, null, { focus: false });
      syncLayerControls();
      liveIntegration.start();
      // ?model=reference keeps the earlier light model reachable for comparison.
      const solarModel = new URLSearchParams(window.location.search).get("model") === "reference" ? "reference" : "v1";
      solarRuntime = new SolarRuntime({
        scene, renderer, model: gltf.scene, dimmedLights: [roofKeyLight, sideFillLight, roofEdgeLight],
        endpoint: SOLAR_ENDPOINTS[solarModel],
      });
      applySolarUrlOptions(new URLSearchParams(window.location.search));
      setDevField("glbStatus", "Loaded");
      setDevField("loadDetail", `Loaded ${sceneRegistry.nodeCount.toLocaleString()} cached scene nodes.`);
      message.hidden = true;
    } catch (error) {
      showError(error);
    }
  },
  (progress) => {
    if (progress.total > 0) {
      const percent = Math.round(progress.loaded / progress.total * 100);
      message.textContent = `Loading greenhouse model… ${percent}%`;
      setDevField("loadDetail", `Loading greenhouse.glb… ${percent}%`);
    }
  },
  showError,
);

renderer.setAnimationLoop((timeMs) => {
  const deltaSeconds = Math.min(clock.getDelta(), 0.1);
  liveIntegration?.update(deltaSeconds);
  cameraRuntime?.update(timeMs);
  controls.update();
  labelRuntime?.update();
  solarRuntime?.tick(timeMs);
  renderer.render(scene, camera);
});
