import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { GLTFLoader } from "../digital_twin/static/digital_twin/vendor/three/addons/loaders/GLTFLoader.js";
import { Box3, Vector3 } from "../digital_twin/static/digital_twin/vendor/three/three.module.js";
import { ActuatorRuntime } from "../digital_twin/static/digital_twin/js/actuator-runtime.mjs";
import { ALL_OBJECT_MAP, WALL_OBJECT_MAP, mappedAssetContext } from "../digital_twin/static/digital_twin/js/live-config.mjs";
import { addWallCurtains } from "../digital_twin/static/digital_twin/js/wall-curtains.mjs";

async function loadModel() {
  const bytes = await readFile(new URL("../digital_twin/static/digital_twin/models/greenhouse.glb", import.meta.url));
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  return new Promise((resolve, reject) => new GLTFLoader().parse(buffer, "", (gltf) => resolve(gltf.scene), reject));
}

test("wall curtains: 측창 정면/후면 and 수직커튼 4면 are added on the windbreak part of each wall", async () => {
  const model = await loadModel();
  const added = addWallCurtains(model);
  assert.deepEqual(added.sort(), ["GH_SIDE_VENT_FRONT", "GH_SIDE_VENT_REAR", "GH_VERTICAL_CURTAIN_FRONT",
    "GH_VERTICAL_CURTAIN_LEFT", "GH_VERTICAL_CURTAIN_REAR", "GH_VERTICAL_CURTAIN_RIGHT"]);
  for (const mapping of Object.values(WALL_OBJECT_MAP)) assert.ok(model.getObjectByName(mapping.names[0]), mapping.names[0]);

  model.updateMatrixWorld(true);
  const box = (name) => new Box3().setFromObject(model.getObjectByName(`${name}_PANEL`));
  // Ends: only the 16 m windbreak half (the sandwich-panel half has no curtain), front on the X3 face.
  const rear = box("GH_SIDE_VENT_REAR");
  assert.ok(Math.abs(rear.max.z - rear.min.z - 16) < 0.01);
  assert.ok(rear.min.z > -0.01 && rear.min.x > 48.75);                    // outside the rear plane
  const rearInner = box("GH_VERTICAL_CURTAIN_REAR");
  assert.ok(rearInner.max.x < 48.75);                                      // inside
  const front = box("GH_SIDE_VENT_FRONT");
  assert.ok(Math.abs(front.min.x - (-39.75 - 0.12)) < 0.01);
  // Long sides: inner curtain follows the GLB outer curtain length, 0.45 m inside it.
  const outer = box("GH_SIDE_CURTAIN_RIGHT");
  const inner = box("GH_VERTICAL_CURTAIN_RIGHT");
  assert.ok(Math.abs((outer.max.x - outer.min.x) - (inner.max.x - inner.min.x)) < 0.01);
  assert.ok(Math.abs(Math.abs(outer.min.z) - Math.abs(inner.min.z) - 0.45) < 0.01);
  assert.equal(model.getObjectByName("GH_VERTICAL_CURTAIN_FRONT").userData.wall_label, "정면");
});

test("wall curtains follow the field opening: 0 % hangs to the lower wall, 100 % is wound up to the eave", async () => {
  const model = await loadModel();
  addWallCurtains(model);
  const runtime = new ActuatorRuntime({ objectMap: ALL_OBJECT_MAP, warn: () => {} });
  const status = runtime.bindScene(model);
  for (const key of Object.keys(WALL_OBJECT_MAP)) assert.equal(status[key].found, 1, key);

  const bottom = (name) => { model.updateMatrixWorld(true); return new Box3().setFromObject(model.getObjectByName(`${name}_PANEL`)).min.y; };
  const settle = (actuators) => { runtime.setTargets(actuators); for (let i = 0; i < 200; i += 1) runtime.update(0.1); };
  settle({ side_vent_left_pct: 0, vertical_curtain_rear_pct: 0 });
  assert.ok(Math.abs(bottom("GH_SIDE_CURTAIN_LEFT") - 0.8) < 0.01);        // GLB curtain, eave 5.0 - 4.2
  assert.ok(Math.abs(bottom("GH_VERTICAL_CURTAIN_REAR") - 0.8) < 0.01);
  settle({ side_vent_left_pct: 50, vertical_curtain_rear_pct: 100 });
  assert.ok(Math.abs(bottom("GH_SIDE_CURTAIN_LEFT") - 2.9) < 0.01);
  assert.ok(bottom("GH_VERTICAL_CURTAIN_REAR") > 4.99);
  const bar = model.getObjectByName("GH_SIDE_CURTAIN_LEFT_BOTTOM_BAR").getWorldPosition(new Vector3());
  assert.ok(Math.abs(bar.y - 2.9) < 0.01);                                 // the bottom bar follows the fabric
});

test("selecting a wall curtain shows its live value and the provisional mapping", async () => {
  const model = await loadModel();
  addWallCurtains(model);
  const owner = model.getObjectByName("GH_VERTICAL_CURTAIN_LEFT");
  const context = mappedAssetContext({ owner }, { actuators: { vertical_curtain_left_pct: 95 } });
  assert.equal(context.openingPercent, 95);
  assert.equal(context.channel, "수직커튼 좌측");
  assert.equal(context.mappingStatus, "잠정");
});

test("control tags: roof vents and screens once on span 1, side vents and vertical curtains on each wall", async () => {
  const { controlTagSpecs, percentText } = await import("../digital_twin/static/digital_twin/js/control-tags.mjs");
  const model = await loadModel();
  addWallCurtains(model);
  const specs = controlTagSpecs(model);
  assert.deepEqual(specs.map((spec) => spec.title), ["천창 좌", "천창 우", "차광 (알루미늄)", "산광", "정면", "후면", "좌측", "우측"]);
  for (const spec of specs.slice(0, 4)) assert.ok(spec.anchor.z > 8 && spec.anchor.z < 16, spec.title);   // over S01
  const front = specs.find((spec) => spec.title === "정면");
  assert.deepEqual(front.rows.map((row) => row.key), ["side_vent_front_pct", "vertical_curtain_front_pct"]);
  assert.equal(front.select, "GH_SIDE_VENT_FRONT");
  for (const spec of specs) assert.ok(model.getObjectByName(spec.select), spec.select);
  assert.equal(percentText(69.6), "70%");
  assert.equal(percentText(null), "—");
});

test("wind: field direction text -> flow in model axes, and windward openings take air in", async () => {
  const { WindRuntime, openingFlow, parseWindDirection, windFlowThree } = await import("../digital_twin/static/digital_twin/js/wind-runtime.mjs");
  assert.equal(parseWindDirection("67° 동북동"), 67);
  assert.equal(parseWindDirection("-90°"), 270);
  assert.equal(parseWindDirection("바람 없음"), null);
  // Long axis 284° (X1 entrance at the east end): a wind from 67° blows toward the rear (+X) and across to -Z.
  const flow = windFlowThree(67, 284);
  assert.ok(Math.abs(flow.x - 0.799) < 0.01 && Math.abs(flow.z + 0.602) < 0.01 && flow.y === 0);
  assert.equal(openingFlow(new Vector3(-1, 0, 0), flow, 4), 1);     // front wall faces the wind: in
  assert.equal(openingFlow(new Vector3(1, 0, 0), flow, 4), -1);     // rear: out
  assert.equal(openingFlow(new Vector3(-1, 0, 0), flow, 0), 0);     // calm: no side-vent arrows
  assert.equal(openingFlow(new Vector3(-1, 0, 0), flow, 0.2), 1);   // 0.2 m/s (a common field reading) still counts
  assert.equal(openingFlow(new Vector3(0, 1, 0), null, 0, undefined, "roof"), -1);   // roof: out even in calm air
  // a wall within 20° of parallel to the wind shows nothing; roof vents always let air out
  const along = windFlowThree(67, 284);
  const sideways = new Vector3(-along.z, 0, along.x);                     // normal at 90° to the wind
  assert.equal(openingFlow(sideways, along, 4), 0);
  const tilted = sideways.clone().applyAxisAngle(new Vector3(0, 1, 0), 25 * Math.PI / 180);
  assert.notEqual(openingFlow(tilted, along, 4), 0);                      // 25° off parallel: counts
  assert.equal(openingFlow(new Vector3(0, 0.8, 0.6).normalize(), along, 4, undefined, "roof"), -1);
  assert.equal(openingFlow(new Vector3(0, 0.8, -0.6).normalize(), along, 4, undefined, "roof"), -1);

  const model = await loadModel();
  addWallCurtains(model);
  const { Scene } = await import("../digital_twin/static/digital_twin/vendor/three/three.module.js");
  const wind = new WindRuntime({ scene: new Scene(), model, longAxisAzimuthDeg: 284 });
  assert.equal(wind.windows.length, 4 * 3 + 8);                      // 3 arrows per wall, one per roof-vent leaf
  wind.setLive({ wind_speed_m_s: 4, wind_direction_text: "67° 동북동" },
    { side_vent_front_pct: 60, side_vent_rear_pct: 0, side_vent_left_pct: 60, side_vent_right_pct: 60, roof_vent_left_pct: 50, roof_vent_right_pct: 50 });
  wind.tick(0.3);
  const arrows = (key) => wind.windows.filter((w) => w.key === key).flatMap((w) => w.arrows);
  assert.ok(arrows("side_vent_front_pct").some((m) => m.visible));
  assert.ok(arrows("side_vent_front_pct").every((m) => m.material === wind.inMaterial));
  assert.ok(arrows("side_vent_rear_pct").every((m) => !m.visible));   // closed
  assert.ok(arrows("side_vent_right_pct").every((m) => m.material === wind.outMaterial));
  assert.ok([...arrows("roof_vent_left_pct"), ...arrows("roof_vent_right_pct")].every((m) => m.material === wind.outMaterial));
  // the arrows move: a later frame puts them elsewhere along the stream
  const before = arrows("side_vent_front_pct")[0].position.clone();
  wind.tick(0.2);
  assert.ok(arrows("side_vent_front_pct")[0].position.distanceTo(before) > 0.05);
});

test("environment trial: sky, ground and haze are added and fully removed again (rollback)", async () => {
  const { addEnvironment, environmentEnabled, lookAt } = await import("../digital_twin/static/digital_twin/js/environment-runtime.mjs");
  const { Color, FogExp2, Scene } = await import("../digital_twin/static/digital_twin/vendor/three/three.module.js");
  assert.equal(environmentEnabled("?env=0"), false);
  assert.equal(environmentEnabled(""), true);
  // golden hour sits between dusk and day: warm horizon (more red than blue)
  const golden = lookAt(3);
  assert.ok(golden.horizon.r > golden.horizon.b);
  assert.equal(lookAt(-40).stars, 1);
  assert.equal(lookAt(null).light, 1);
  const model = await loadModel();
  const scene = new Scene();
  scene.background = new Color(0x16304f);
  scene.fog = new FogExp2(0x16304f, 0.00145);
  const before = { children: scene.children.length, background: scene.background, fog: scene.fog,
    pad: model.getObjectByName("GH_GROUND_PLANE").material.color.getHex() };
  const hemisphere = { intensity: 1.55 };
  const renderer = { toneMappingExposure: 1.08 };
  const environment = addEnvironment({ scene, model, hemisphere, renderer });
  assert.ok(scene.getObjectByName("VIEWER_SKY") && scene.getObjectByName("VIEWER_GROUND"));
  environment.setSunAltitude(-15);                                        // night: dimmer light, stars on
  assert.ok(hemisphere.intensity < 1 && renderer.toneMappingExposure < 1);
  assert.ok(scene.getObjectByName("VIEWER_STARS").visible);
  environment.setSunAltitude(40);                                         // day: the original look
  assert.equal(hemisphere.intensity, 1.55);
  assert.equal(scene.getObjectByName("VIEWER_STARS").visible, false);
  environment.setSunAltitude(-15);
  environment.remove();
  assert.equal(hemisphere.intensity, 1.55);
  assert.equal(renderer.toneMappingExposure, 1.08);
  assert.equal(scene.children.length, before.children);
  assert.equal(scene.background, before.background);
  assert.equal(scene.fog, before.fog);
  assert.equal(model.getObjectByName("GH_GROUND_PLANE").material.color.getHex(), before.pad);
});
