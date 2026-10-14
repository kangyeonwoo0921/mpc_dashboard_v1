import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { GLTFLoader } from "../digital_twin/static/digital_twin/vendor/three/addons/loaders/GLTFLoader.js";
import { Box3, Vector3 } from "../digital_twin/static/digital_twin/vendor/three/three.module.js";
import { ActuatorRuntime, buildControllableRegistry } from "../digital_twin/static/digital_twin/js/actuator-runtime.mjs";
import { LIVE_CONFIG, OBJECT_MAP } from "../digital_twin/static/digital_twin/js/live-config.mjs";
import { LivePollingClient } from "../digital_twin/static/digital_twin/js/live-client.mjs";
import { updateLivePanel } from "../digital_twin/static/digital_twin/js/live-panel.mjs";
import { LiveState } from "../digital_twin/static/digital_twin/js/live-state.mjs";

function object(name, { opening = 0, maxAngle = 35, rotationX = 0, scaleX = 1 } = {}) {
  return {
    name,
    rotation: { x: rotationX },
    scale: { x: scaleX },
    userData: { opening_percent: opening, max_open_angle_deg: maxAngle },
  };
}

function scene(objects) {
  const index = new Map(objects.map((item) => [item.name, item]));
  return { getObjectByName: (name) => index.get(name) ?? null };
}

globalThis.ProgressEvent ??= class ProgressEvent {
  constructor(type, init = {}) { this.type = type; Object.assign(this, init); }
};

test("mapping config is the single current GLB naming contract", () => {
  assert.equal(LIVE_CONFIG.pollIntervalMs, 2000);
  assert.deepEqual(OBJECT_MAP.roofVentLeft.names, ["GH_VENT_S01_01_PIVOT", "GH_VENT_S02_01_PIVOT", "GH_VENT_S03_01_PIVOT", "GH_VENT_S04_01_PIVOT"]);
  assert.deepEqual(OBJECT_MAP.roofVentRight.names, ["GH_VENT_S01_02_PIVOT", "GH_VENT_S02_02_PIVOT", "GH_VENT_S03_02_PIVOT", "GH_VENT_S04_02_PIVOT"]);
  assert.equal(OBJECT_MAP.shadeScreen1.names.length, 8); // two halves per span (both gutters)
});

test("GLTFLoader parses the copied GLB and every configured object exists", async () => {
  const bytes = await readFile(new URL("../digital_twin/static/digital_twin/models/greenhouse.glb", import.meta.url));
  assert.equal(bytes.toString("ascii", 0, 4), "glTF");
  const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const gltf = await new Promise((resolve, reject) => new GLTFLoader().parse(arrayBuffer, "", resolve, reject));
  const size = new Box3().setFromObject(gltf.scene).getSize(new Vector3());
  assert.ok(Math.max(size.x, size.y, size.z) > 90, "model bounds support camera auto-fit");
  for (const mapping of Object.values(OBJECT_MAP)) {
    for (const name of mapping.names) assert.ok(gltf.scene.getObjectByName(name), `missing GLB node ${name}`);
  }
  const runtime = new ActuatorRuntime({ warn: () => {} });
  const status = runtime.bindScene(gltf.scene);
  assert.ok(Object.values(status).every((item) => item.found === item.expected));
  const registry = buildControllableRegistry(gltf.scene);
  assert.equal(registry.roofVents.length, 8);
  assert.equal(registry.shadeScreens.length, 8);
  assert.equal(registry.diffuseScreens.length, 8);
  assert.equal(registry.sideCurtains.length, 2);
  const leftVent = gltf.scene.getObjectByName("GH_VENT_S01_01_PIVOT");
  const rightVent = gltf.scene.getObjectByName("GH_VENT_S01_02_PIVOT");
  const shade = gltf.scene.getObjectByName("GH_SHADE_SCREEN_S01_N_PIVOT");
  const diffuse = gltf.scene.getObjectByName("GH_DIFFUSE_SCREEN_S01_N_PIVOT");
  const before = {
    leftVent: leftVent.rotation.x,
    rightVent: rightVent.rotation.x,
    shade: shade.scale.z,
    diffuse: diffuse.scale.z,
  };
  runtime.setTargets({
    roof_vent_left_pct: 80,
    roof_vent_right_pct: 5,
    shade_screen_1_pct: 10, // 차광커튼1 -> diffuse layer
    shade_screen_2_pct: 80, // 차광커튼2 -> aluminium shade layer
  });
  runtime.update(0.1);
  assert.ok(leftVent.rotation.x > before.leftVent);
  // The -Y leaf rotates negatively to open, so closing reduces its magnitude.
  assert.ok(Math.abs(rightVent.rotation.x) < Math.abs(before.rightVent));
  // Screens travel across the span: Blender local Y is exported as glTF local Z.
  assert.equal(shade.userData.retract_axis, "y");
  assert.ok(shade.scale.z < before.shade);
  assert.ok(diffuse.scale.z > before.diffuse);
});

test("missing objects warn once and do not stop actuator updates", () => {
  const warnings = [];
  const vent = object("GH_VENT_S01_01_PIVOT", { opening: 20, rotationX: 7 * Math.PI / 180 });
  const runtime = new ActuatorRuntime({ warn: (message) => warnings.push(message) });
  const status = runtime.bindScene(scene([vent]));
  assert.equal(status.roofVentLeft.found, 1);
  assert.ok(warnings.length > 0);
  runtime.setTargets({ roof_vent_left_pct: 80 });
  runtime.update(0.1);
  assert.ok(vent.rotation.x > 7 * Math.PI / 180);
});

test("vent and screen motion is smoothed instead of snapping", () => {
  const objects = Object.values(OBJECT_MAP).flatMap((mapping) => mapping.names.map((name) => (
    mapping.kind === "screen"
      ? object(name, { opening: 100, scaleX: 0.000001 })
      : object(name)
  )));
  const runtime = new ActuatorRuntime({ warn: () => {} });
  runtime.bindScene(scene(objects));
  runtime.setTargets({
    roof_vent_left_pct: 100,
    roof_vent_right_pct: 100,
    shade_screen_1_pct: 0,
    shade_screen_2_pct: 0,
  });
  runtime.update(1 / 60);
  const vent = objects.find((item) => item.name === "GH_VENT_S01_01_PIVOT");
  const screen = objects.find((item) => item.name === "GH_SHADE_SCREEN_S01_N_PIVOT");
  assert.ok(vent.rotation.x > 0 && vent.rotation.x < 35 * Math.PI / 180);
  assert.ok(screen.scale.x > 0 && screen.scale.x < 1);
  for (let index = 0; index < 120; index += 1) runtime.update(1 / 60);
  assert.ok(Math.abs(vent.rotation.x - 35 * Math.PI / 180) < 0.001);
  assert.ok(Math.abs(screen.scale.x - 1) < 0.001);
});

test("API failure preserves the last valid state and exposes connection states", () => {
  const state = new LiveState({ staleAfterMs: 10000 });
  state.acceptSnapshot({
    source: "mock_dynamic",
    timestamp: "2026-09-24T00:00:00+09:00",
    connected: true,
    environment: { indoor_temperature_c: 29 },
    actuators: { roof_vent_left_pct: 40 },
  }, 1000);
  assert.equal(state.connectionStatus(2000), "live");
  state.markRequestFailure(new Error("offline"));
  assert.equal(state.connectionStatus(2000), "disconnected");
  assert.equal(state.environment.indoor_temperature_c, 29);
  assert.equal(state.actuators.roof_vent_left_pct, 40);
  state.transportConnected = true;
  assert.equal(state.connectionStatus(12000), "stale");
});

test("LIVE panel renders mock values and stale state without source-specific keys", () => {
  const nodes = new Map();
  const root = {
    dataset: {},
    querySelector(selector) {
      const key = selector.match(/data-live-field="([^"]+)"/)?.[1];
      if (!key) return null;
      if (!nodes.has(key)) nodes.set(key, { textContent: "" });
      return nodes.get(key);
    },
  };
  const state = new LiveState({ staleAfterMs: 10000 });
  state.acceptSnapshot({
    source: "mock_dynamic",
    timestamp: "2026-09-24T00:00:00+09:00",
    connected: true,
    environment: { indoor_temperature_c: 28.75, wind_direction_text: "NE" },
    actuators: { roof_vent_left_pct: 42.2 },
  }, 1000);
  updateLivePanel(root, state, 2000);
  assert.equal(root.dataset.connection, "live");
  assert.equal(nodes.get("source").textContent, "실시간 — 모의 데이터");
  assert.equal(nodes.get("indoorTemperature").textContent, "28.8 °C");
  assert.equal(nodes.get("roofVentLeft").textContent, "42.2 %");
  updateLivePanel(root, state, 12000);
  assert.equal(root.dataset.connection, "stale");
});

test("polling schedules the next request only after the current request completes", async () => {
  const resolvers = [];
  const timers = [];
  let active = 0;
  let maximumActive = 0;
  let calls = 0;
  const scheduler = {
    setTimeout(callback) { timers.push(callback); return timers.length; },
    clearTimeout() {},
  };
  const fetchImpl = async () => {
    calls += 1;
    active += 1;
    maximumActive = Math.max(maximumActive, active);
    await new Promise((resolve) => resolvers.push(resolve));
    active -= 1;
    return { ok: true, json: async () => ({ source: "mock_dynamic", connected: true, environment: {}, actuators: {} }) };
  };
  const client = new LivePollingClient({ fetchImpl, scheduler });
  client.start();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls, 1);
  assert.equal(timers.length, 0);
  resolvers.shift()();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(timers.length, 1);
  timers.shift()();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls, 2);
  assert.equal(maximumActive, 1);
  client.stop();
  resolvers.shift()();
});
