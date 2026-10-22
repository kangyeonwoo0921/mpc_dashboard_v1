import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

import { CameraRuntime } from "./camera-runtime.mjs";
import { ContextPanelRuntime } from "./context-panel.mjs";
import { ControlTags } from "./control-tags.mjs";
import { addEnvironment, environmentEnabled } from "./environment-runtime.mjs";
import { InteractionRuntime } from "./interaction-runtime.mjs";
import { CHANNEL_LABELS, mappedAssetContext } from "./live-config.mjs";
import { LabelRuntime } from "./label-runtime.mjs";
import { initMotion } from "./motion-runtime.mjs";
import { OpsPanel } from "./ops-panel.mjs";
import { buildSceneRegistry } from "./scene-registry.mjs";
import { SelectionRuntime } from "./selection-runtime.mjs";
import { SOLAR_CONFIG, SOLAR_ENDPOINTS, SolarRuntime } from "./solar-runtime.mjs";
import { createLiveViewerIntegration } from "./viewer-live-integration.mjs";
import { CAMERA_PRESETS, SCENE_COLORS, VIEWER_UI_CONFIG } from "./viewer-config.mjs";
import { VisibilityRuntime } from "./visibility-runtime.mjs";
import { addWallCurtains } from "./wall-curtains.mjs";
import { WindRuntime } from "./wind-runtime.mjs";

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

const hemisphereLight = new THREE.HemisphereLight(0xd8e2ee, 0x3d3328, 1.55);
scene.add(hemisphereLight);
const roofKeyLight = new THREE.DirectionalLight(0xfff0d8, 3.1);
roofKeyLight.position.set(-18, 58, 36);
scene.add(roofKeyLight);
const sideFillLight = new THREE.DirectionalLight(0xa9c8d6, 1.0);
sideFillLight.position.set(42, 21, -38);
scene.add(sideFillLight);
const roofEdgeLight = new THREE.DirectionalLight(0xdcc8b0, 0.72);
roofEdgeLight.position.set(8, 34, -42);
scene.add(roofEdgeLight);

const selectionRuntime = new SelectionRuntime();
const opsPanel = new OpsPanel({
  root: document.getElementById("ops-panel"),
  statusRoot: document.getElementById("ops-status"),
  onPreview: (request) => applyPreview(request),
});
let liveIntegration = null;
let sceneRegistry = null;
let cameraRuntime = null;
let visibilityRuntime = null;
let interactionRuntime = null;
let labelRuntime = null;
let controlTags = null;
let windRuntime = null;
let environment = null;
let contextPanel = null;
let solarRuntime = null;
let solarTimer = null;
let solarDebounce = null;
let solarPreview = null;   // { label, detail } while the 60-min preview drives the sun and light map
const clock = new THREE.Clock();

function siteDate() {
  // Site-local calendar date; the server applies the site timezone to naive times.
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
}

function renderSolarReadout(payload, error = null) {
  const node = shell.querySelector("[data-solar-readout]");
  if (!node) return;
  if (error) {
    node.textContent = "태양 모델을 불러오지 못했습니다";
    return;
  }
  const time = payload.timestamp.slice(11, 16);
  const sun = payload.sun.altitude_deg > 0
    ? `태양 고도 ${payload.sun.altitude_deg.toFixed(0)}° · 방위 ${payload.sun.azimuth_deg.toFixed(0)}°`
    : "해가 진 뒤";
  const { sunlitFraction, mean, directMean, ghi } = payload.summary;
  const parts = [solarPreview ? solarPreview.label : time, sun];
  if (typeof payload.beam === "number" && payload.sun.altitude_deg > 0) {
    parts.push(payload.beam < 0.1 ? "흐림 · 직달광 거의 없음" : `직달광 비율 ${(payload.beam * 100).toFixed(0)}%`);
  }
  if (sunlitFraction !== null && sunlitFraction !== undefined && payload.sun.altitude_deg > 0 && (payload.beam ?? 1) >= 0.1) {
    parts.push(`일조 ${(sunlitFraction * 100).toFixed(0)}%`);
  }
  if (mean !== null && mean !== undefined) parts.push(`작물면 평균 ${mean.toFixed(0)} ${payload.summary.unit}`);
  else if (payload.grid.mode === "direct" && directMean !== null) parts.push(`직달광 평균 ${directMean.toFixed(0)} W/m² (추정·산란 제외)`);
  else if (payload.sun.altitude_deg > 0 && (ghi === null || ghi === undefined)) parts.push("일사 입력 없음 → 일조 여부만 표시");
  node.textContent = parts.join(" · ") + (solarPreview ? ` · ${solarPreview.detail}` : "");
}

function refreshSolar(time = null, params = {}) {
  if (!solarRuntime) return;
  solarRuntime.refresh(time, params).then(() => renderSolarReadout(solarRuntime.state)).catch((error) => renderSolarReadout(null, error));
}

function siteMinutes(iso) {
  const [hh, mm] = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false })
    .format(new Date(iso)).split(":").map(Number);
  return hh * 60 + mm;
}

function applyPreview(request) {
  if (!request) {
    solarPreview = null;
    setSolarLive(true);
    return;
  }
  solarPreview = { label: request.label, detail: request.detail };
  shell.querySelector("[data-solar-now]")?.setAttribute("aria-pressed", "false");
  clearInterval(solarTimer);
  const slider = shell.querySelector("[data-solar-time]");
  if (slider) slider.value = String(Math.min(Math.max(siteMinutes(request.time), Number(slider.min)), Number(slider.max)));
  refreshSolar(request.time, request.params);
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
    solarPreview = null;
    opsPanel.markPreview(0);
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
  // Overlay UI stays 1:1 in the page and enlarges in fullscreen (900px-high reference, max 1.5x).
  const uiScale = document.fullscreenElement && width > 720 ? Math.min(Math.max(Math.min(height / 900, width / 1500), 1), 1.5) : 1;
  shell.style.setProperty("--ui-scale", uiScale.toFixed(3));
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
  // "제어 장치" turns the control state on and the overview resets it; other views keep what the user chose.
  if (name === "control" || name === "overview") visibilityRuntime.setOverlay("controlState", name === "control");
  const bounds = selectionRuntime.state.level === "greenhouse" ? null : selectedBounds();
  cameraRuntime.goTo(name, { bounds, immediate });
  interactionRuntime?.refreshHighlights();
  setActivePreset(name);
  syncLayerControls();
}

function renderMappingStatus(status) {
  mappingStatusRoot.replaceChildren();
  for (const [key, result] of Object.entries(status)) {
    const item = document.createElement("span");
    item.className = result.provisional ? "mapping-warning" : "";
    item.textContent = `${CHANNEL_LABELS[key] ?? key} ${result.found}/${result.expected}${result.provisional ? " · provisional" : ""}`;
    mappingStatusRoot.append(item);
  }
}

function syncLiveChrome(state) {
  const status = state.connectionStatus();
  const updated = state.lastReceivedAt === null ? "—" : new Date(state.lastReceivedAt).toLocaleTimeString("en-GB", { hour12: false });
  opsPanel.setLive({ source: state.source, status, receivedAt: state.lastReceivedAt, ghi: state.environment?.solar_w_m2 ?? null,
    alarm: state.status?.alarm === true });
  setDevField("source", state.source ?? "—");
  setDevField("connection", status.toUpperCase());
  setDevField("lastSuccess", updated);
  controlTags?.setActuators(state.actuators);
  windRuntime?.setLive(state.environment, state.actuators);
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
  message.textContent = "온실 모델을 불러오지 못했습니다";
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
    button.addEventListener("click", () => {
      // "전체(선택 초기화)" also clears the span/asset selection and restores the default layers and
      // overlays (what the former "전체 보기로" did) before framing the whole greenhouse.
      if (button.dataset.viewPreset === "overview") {
        selectionRuntime.selectGreenhouse();
        interactionRuntime?.resetHighlights();
        interactionRuntime?.clearHover();
        visibilityRuntime?.restoreDefault();
        visibilityRuntime?.setOverlay("labels", true);
        interactionRuntime?.setLabelsEnabled(true);
        labelRuntime?.setEnabled(true);
      }
      activatePreset(button.dataset.viewPreset);
    });
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
  shell.querySelector("[data-wind]")?.addEventListener("change", (event) => windRuntime?.setEnabled(event.currentTarget.checked));
  document.getElementById("fit-selected").addEventListener("click", () => cameraRuntime?.zoomInOn(selectedBounds()));
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
    solarPreview = null;
    opsPanel.markPreview(-1);
    setSolarLive(false);
    clearTimeout(solarDebounce);
    solarDebounce = setTimeout(() => refreshSolar(`${siteDate()}T${hh}:${mm}`), 150);
  });
  shell.querySelector("[data-solar-now]")?.addEventListener("click", () => setSolarLive(true));
  const opsRoot = document.getElementById("ops-panel");
  opsRoot.querySelector("[data-ops-collapse]")?.addEventListener("click", (event) => {
    const collapsed = opsRoot.dataset.collapsed !== "true";
    opsRoot.dataset.collapsed = String(collapsed);
    event.currentTarget.setAttribute("aria-expanded", String(!collapsed));
    event.currentTarget.textContent = collapsed ? "+" : "−";
    event.currentTarget.setAttribute("aria-label", collapsed ? "운영 요약 펼치기" : "운영 요약 접기");
  });
  document.getElementById("left-panels-toggle")?.addEventListener("click", (event) => {
    const hidden = shell.dataset.leftPanels !== "hidden";
    shell.dataset.leftPanels = hidden ? "hidden" : "shown";
    event.currentTarget.setAttribute("aria-expanded", String(!hidden));
    event.currentTarget.setAttribute("aria-label", hidden ? "왼쪽 패널 보이기" : "왼쪽 패널 숨기기");
  });
  document.getElementById("toolbar-toggle")?.addEventListener("click", (event) => {
    const hidden = shell.dataset.toolbar !== "hidden";
    shell.dataset.toolbar = hidden ? "hidden" : "shown";
    event.currentTarget.setAttribute("aria-expanded", String(!hidden));
    event.currentTarget.setAttribute("aria-label", hidden ? "시점 도구 보이기" : "시점 도구 숨기기");
  });
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
initMotion(shell);
opsPanel.start();
window.addEventListener("resize", resize);
new ResizeObserver(() => resize()).observe(shell);
document.addEventListener("fullscreenchange", resize);

const loader = new GLTFLoader();
loader.load(
  shell.dataset.modelUrl,
  (gltf) => {
    try {
      addWallCurtains(gltf.scene);   // 측창 정면/후면 and 수직커튼 4면 (not in the GLB; display only)
      sceneRegistry = buildSceneRegistry(gltf.scene);
      scene.add(gltf.scene);
      // sky + ground + time of day (trial); ?env=0 = before
      if (environmentEnabled()) environment = addEnvironment({ scene, model: gltf.scene, hemisphere: hemisphereLight, renderer });
      visibilityRuntime = new VisibilityRuntime(sceneRegistry);
      cameraRuntime = new CameraRuntime({ camera, controls, registry: sceneRegistry, onPresetChange: (name) => setActivePreset(name) });
      labelRuntime = new LabelRuntime({ root: selectedLabelRoot, camera, domElement: renderer.domElement });
      controlTags = new ControlTags({
        root: document.getElementById("control-tags"), camera, domElement: renderer.domElement,
        onSelect(name) {
          const entry = sceneRegistry.getAsset(name);
          if (entry) selectionRuntime.selectAsset(entry);
        },
      });
      controlTags.bind(gltf.scene);
      const azimuth = Number.parseFloat(shell.dataset.longAxisAzimuth);
      windRuntime = new WindRuntime({ scene, model: gltf.scene, longAxisAzimuthDeg: Number.isFinite(azimuth) ? azimuth : Number.NaN });
      windRuntime.setEnabled(shell.querySelector("[data-wind]")?.checked ?? true);
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
      message.textContent = `온실 모델을 불러오는 중… ${percent}%`;
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
  controlTags?.setEnabled(visibilityRuntime?.overlayState.controlState);
  controlTags?.update();
  windRuntime?.tick(deltaSeconds);
  solarRuntime?.tick(timeMs);
  environment?.setSunAltitude(solarRuntime?.state?.sun?.altitude_deg);
  renderer.render(scene, camera);
});
