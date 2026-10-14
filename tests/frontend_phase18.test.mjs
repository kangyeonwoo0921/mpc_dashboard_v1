import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { GLTFLoader } from "../digital_twin/static/digital_twin/vendor/three/addons/loaders/GLTFLoader.js";
import { PerspectiveCamera, Vector3 } from "../digital_twin/static/digital_twin/vendor/three/three.module.js";
import { calculateFitPose } from "../digital_twin/static/digital_twin/js/camera-runtime.mjs";
import { formatInspectionData, formatTooltipText } from "../digital_twin/static/digital_twin/js/interaction-runtime.mjs";
import { formatValue, statusBadge } from "../digital_twin/static/digital_twin/js/live-panel.mjs";
import { buildSceneRegistry } from "../digital_twin/static/digital_twin/js/scene-registry.mjs";
import {
  CAMERA_FIT_MARGIN,
  CAMERA_PRESETS,
  VIEW_PRESET_ORDER,
  VISIBILITY_PRESETS,
} from "../digital_twin/static/digital_twin/js/viewer-config.mjs";
import { VisibilityRuntime } from "../digital_twin/static/digital_twin/js/visibility-runtime.mjs";

globalThis.ProgressEvent ??= class ProgressEvent {
  constructor(type, init = {}) { this.type = type; Object.assign(this, init); }
};

let cachedScene = null;
async function loadScene() {
  if (cachedScene) return cachedScene;
  const bytes = await readFile(new URL("../digital_twin/static/digital_twin/models/greenhouse.glb", import.meta.url));
  const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const gltf = await new Promise((resolve, reject) => new GLTFLoader().parse(arrayBuffer, "", resolve, reject));
  cachedScene = gltf.scene;
  return cachedScene;
}

function projectedCoverage(bounds, camera, pose) {
  camera.position.copy(pose.position);
  camera.lookAt(pose.target);
  camera.updateMatrixWorld();
  const points = [];
  for (const x of [bounds.min.x, bounds.max.x]) {
    for (const y of [bounds.min.y, bounds.max.y]) {
      for (const z of [bounds.min.z, bounds.max.z]) points.push(new Vector3(x, y, z).project(camera));
    }
  }
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  return {
    width: (Math.max(...xs) - Math.min(...xs)) / 2,
    height: (Math.max(...ys) - Math.min(...ys)) / 2,
  };
}

test("all Phase 1.8 camera presets exist and Front/Rear follow X1/X23", () => {
  assert.deepEqual(VIEW_PRESET_ORDER, ["overview", "front", "rear", "roof", "interior", "equipment", "control"]);
  for (const name of VIEW_PRESET_ORDER) assert.ok(CAMERA_PRESETS[name]);
  assert.ok(CAMERA_PRESETS.front.direction[0] < 0, "Front camera is at negative X looking toward +X");
  assert.ok(CAMERA_PRESETS.rear.direction[0] > 0, "Rear camera is at positive X looking toward -X");
});

test("Overview uses model bounds and fills the 1440x900 viewport", async () => {
  const registry = buildSceneRegistry(await loadScene());
  const camera = new PerspectiveCamera(42, 1440 / 900, 0.05, 2000);
  const pose = calculateFitPose(registry.modelBounds, camera, CAMERA_PRESETS.overview.direction, CAMERA_FIT_MARGIN);
  const coverage = projectedCoverage(registry.modelBounds, camera, pose);
  assert.ok(coverage.width >= 0.6 && coverage.width <= 0.75, `width coverage ${coverage.width}`);
  assert.ok(coverage.height >= 0.55 && coverage.height <= 0.7, `height coverage ${coverage.height}`);
});

test("scene registry traverses once and caches names, layers, controls, and raycast targets", async () => {
  const model = await loadScene();
  const originalTraverse = model.traverse.bind(model);
  let traverseCalls = 0;
  model.traverse = (callback) => { traverseCalls += 1; return originalTraverse(callback); };
  const registry = buildSceneRegistry(model);
  model.traverse = originalTraverse;
  assert.equal(traverseCalls, 1);
  assert.ok(registry.nodeCount > 6000);
  assert.equal(registry.controlRegistry.roofVents.length, 8);
  assert.equal(registry.controlRegistry.shadeScreens.length, 8);
  assert.equal(registry.controlRegistry.diffuseScreens.length, 8);
  assert.equal(registry.controlRegistry.sideCurtains.length, 2);
  assert.ok(registry.interactableTargets.length > 0);
  for (const layer of ["cover", "crops", "equipment", "sensors", "controls"]) assert.ok(registry.layers[layer].length > 0);
});

test("visibility presets use cached layer references and restore defaults", () => {
  const nodes = Object.fromEntries(["cover", "crops", "equipment", "sensors", "controls"].map((name) => [name, [{ visible: true }]]));
  const runtime = new VisibilityRuntime({ layers: nodes });
  assert.deepEqual(VISIBILITY_PRESETS.interior, { cover: false, crops: true, equipment: true, sensors: true, controls: true });
  runtime.applyPreset("control_devices");
  assert.equal(nodes.cover[0].visible, false);
  assert.equal(nodes.controls[0].visible, true);
  runtime.setLayer("sensors", false);
  assert.equal(nodes.sensors[0].visible, false);
  runtime.restoreDefault();
  assert.ok(Object.values(nodes).every(([node]) => node.visible));
});

test("inspection text only reports available metadata and uncertainty", () => {
  const object = {
    name: "GH_SENSOR_T_RH_01",
    userData: { asset_type: "sensor", sensor_type: "temperature_rh", verified_position: false, source_confidence: "placeholder" },
  };
  const details = formatInspectionData(object);
  assert.equal(details.title, "온습도 센서");
  assert.ok(details.rows.some((row) => row.label === "위치" && row.value === "미확인"));
  assert.ok(details.rows.some((row) => row.label === "출처 신뢰도" && row.value === "placeholder"));
  assert.ok(formatTooltipText(object).includes("위치: 미확인"));
});

test("LIVE UI formatting covers null and connection badges", () => {
  assert.equal(formatValue(null, "°C", 1), "—");
  assert.equal(formatValue(28.45, "°C", 1), "28.4 °C");
  assert.equal(statusBadge("live"), "연결됨");
  assert.equal(statusBadge("stale"), "지연");
  assert.equal(statusBadge("disconnected"), "연결 끊김");
});
