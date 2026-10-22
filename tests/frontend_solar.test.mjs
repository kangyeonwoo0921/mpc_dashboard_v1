import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { GLTFLoader } from "../digital_twin/static/digital_twin/vendor/three/addons/loaders/GLTFLoader.js";
import * as THREE from "../digital_twin/static/digital_twin/vendor/three/three.module.js";
import { SOLAR_CONFIG, SolarRuntime, physicsToThree, rampColor } from "../digital_twin/static/digital_twin/js/solar-runtime.mjs";

async function loadModel() {
  const bytes = await readFile(new URL("../digital_twin/static/digital_twin/models/greenhouse.glb", import.meta.url));
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  return new Promise((resolve, reject) => new GLTFLoader().parse(buffer, "", (gltf) => resolve(gltf.scene), reject));
}

function payload(altitude, directionPhysics) {
  const rows = 2, cols = 3;
  return {
    timestamp: "2026-10-01T12:30:00+09:00",
    sun: { altitude_deg: altitude, azimuth_deg: 183, direction_physics: directionPhysics, direction_threejs: physicsToThree(directionPhysics) },
    outside: { source: "clear_sky_model" },
    canopy_height_m: 3,
    mean: { par_w_m2: 250 },
    grid: { rows, cols, cell_size_m: 1, origin_xy_m: [-1.5, -1], par_w_m2: [0, 100, 200, null, 300, 400], sunlit: [1, 1, 0, null, 1, 1] },
  };
}

test("physics to three.js axes and colour ramp", () => {
  assert.deepEqual(physicsToThree([1, 2, 3]), [1, 3, -2]);
  assert.deepEqual(rampColor(0), [24, 40, 92]);
  assert.deepEqual(rampColor(1), [255, 248, 228]);
});

test("sun, frame shadows and light map follow the solar payload", async () => {
  const model = await loadModel();
  const scene = new THREE.Scene();
  scene.add(model);
  const key = new THREE.DirectionalLight(0xffffff, 3);
  const renderer = { shadowMap: {} };
  const runtime = new SolarRuntime({ scene, renderer, model, dimmedLights: [key] });
  assert.equal(runtime.sun.visible, false, "sun stays hidden until its position is available");
  assert.equal(runtime.light.visible, false);
  assert.equal(runtime.path.visible, false);
  assert.equal(key.intensity, 3, "keep fill lighting before solar data arrives");
  assert.equal(renderer.shadowMap.enabled, true);
  assert.equal(renderer.shadowMap.autoUpdate, false, "shadow map is refreshed on an interval");
  renderer.shadowMap.needsUpdate = false;
  runtime.tick(1000);
  assert.equal(renderer.shadowMap.needsUpdate, true);
  renderer.shadowMap.needsUpdate = false;
  runtime.tick(1100);
  assert.equal(renderer.shadowMap.needsUpdate, false, "no redraw within the refresh interval");
  assert.ok(runtime.casters > 500, "frame members cast shadows");
  const rafter = model.getObjectByName("GH_RAFTER_X001_S03");
  assert.ok(rafter.castShadow || rafter.children.some((c) => c.castShadow));
  const cover = model.getObjectByName("GH_ROOF_COVER_S03");
  assert.ok(!cover.castShadow, "film cover does not cast shadows");

  const up = [-0.12, 0.614, 0.78];
  runtime.apply(payload(51, up));
  const expected = new THREE.Vector3(...physicsToThree(up)).normalize().multiplyScalar(SOLAR_CONFIG.sunDistance);
  assert.ok(runtime.sun.position.distanceTo(expected) < 1e-6);
  assert.ok(runtime.sun.visible && runtime.light.visible);
  assert.ok(Math.abs(key.intensity - 3 * 0.35) < 1e-9, "fill lights dim while the sun is shown");
  assert.equal(runtime.lightMap.visible, false);
  assert.ok(runtime.lightMap.position.distanceTo(new THREE.Vector3(0, 3.05, 0)) < 1e-9, "light map sits on the canopy plane");
  runtime.setLightMapEnabled(true);
  assert.equal(runtime.lightMap.visible, true);
  const data = runtime.lightMap.material.map.image.data;
  assert.equal(data[3 * 4 + 3], 0, "cells outside the footprint are transparent");

  runtime.apply(payload(-20, [0, 0.5, -0.34]));
  assert.ok(!runtime.sun.visible && !runtime.light.visible);
  assert.equal(key.intensity, 3, "fill lights restore at night");
});

test("v1 payload: sunlit map until every cell has irradiance", async () => {
  const { normalizeSolarPayload } = await import("../digital_twin/static/digital_twin/js/solar-runtime.mjs");
  const v1 = (totals) => ({
    model: "radiation_v1",
    timestamp: "2026-10-01T09:30:00+09:00",
    solar: { altitude_deg: 34, azimuth_deg: 124, direction_threejs: [0.1, 0.5, 0.8], path_threejs: [[0, 1, 0]] },
    radiation: {
      status: totals ? "ok" : "missing_input", sunlit_fraction: 0.5, mean_W_m2: totals ? 300 : null,
      grid: { rows: 1, cols: 3, cell_size_m: 1, origin_xy_m: [0, 0], height_m: 3, sunlit: [true, false, null], total_W_m2: totals ?? [null, null, null] },
    },
  });
  const sunlit = normalizeSolarPayload(v1(null));
  assert.equal(sunlit.grid.mode, "sunlit");
  assert.deepEqual(sunlit.grid.values, [1, 0, null]);
  assert.equal(sunlit.summary.mean, null);
  const irradiance = normalizeSolarPayload(v1([400, 200, null]));
  assert.equal(irradiance.grid.mode, "irradiance");
  assert.deepEqual(irradiance.grid.values, [400, 200, null]);
});

test("overcast or rain: weak sun light and faint shadows from the direct-beam share", async () => {
  const { beamShare } = await import("../digital_twin/static/digital_twin/js/solar-runtime.mjs");
  const base = { solar: { altitude_deg: 25 }, inputs: { weather: { ghi_W_m2: 12, decomposition: { status: "ok", kd: 0.9992 } } } };
  assert.ok(beamShare(base) < 0.01);
  assert.equal(beamShare({ ...base, inputs: { weather: { ghi_W_m2: 600, decomposition: { status: "ok", kd: 0.25 } } } }), 0.75);
  assert.equal(beamShare({ solar: { altitude_deg: 25 }, inputs: { weather: { ghi_W_m2: null } } }), null);   // clear-sky geometry view
  assert.equal(beamShare({ solar: { altitude_deg: -3 }, inputs: {} }), 0);
});

test("sun strength follows GHI: full at 100 W/m² and above, fading below", async () => {
  const { sunStrength } = await import("../digital_twin/static/digital_twin/js/solar-runtime.mjs");
  const at = (ghi, altitude = 40) => ({ solar: { altitude_deg: altitude }, inputs: { weather: { ghi_W_m2: ghi } } });
  assert.equal(sunStrength(at(560)), 1);
  assert.equal(sunStrength(at(100)), 1);
  assert.equal(sunStrength(at(70)), 0.7);
  assert.equal(sunStrength(at(0)), 0);
  assert.equal(sunStrength(at(300, -2)), 0);
  assert.equal(sunStrength(at(null)), null);   // clear-sky geometry view
});
