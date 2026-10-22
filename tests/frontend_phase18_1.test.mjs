import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import * as THREE from "../digital_twin/static/digital_twin/vendor/three/three.module.js";
import { GLTFLoader } from "../digital_twin/static/digital_twin/vendor/three/addons/loaders/GLTFLoader.js";
import { buildSceneRegistry } from "../digital_twin/static/digital_twin/js/scene-registry.mjs";
import { SelectionRuntime } from "../digital_twin/static/digital_twin/js/selection-runtime.mjs";
import { VisibilityRuntime } from "../digital_twin/static/digital_twin/js/visibility-runtime.mjs";
import { CameraRuntime } from "../digital_twin/static/digital_twin/js/camera-runtime.mjs";
import { InteractionRuntime } from "../digital_twin/static/digital_twin/js/interaction-runtime.mjs";
import { buildContextModel, HISTORY_EMPTY_MESSAGE } from "../digital_twin/static/digital_twin/js/context-panel.mjs";
import { mappedAssetContext } from "../digital_twin/static/digital_twin/js/live-config.mjs";
import { ActuatorRuntime } from "../digital_twin/static/digital_twin/js/actuator-runtime.mjs";
import { LiveState } from "../digital_twin/static/digital_twin/js/live-state.mjs";
import { LabelRuntime } from "../digital_twin/static/digital_twin/js/label-runtime.mjs";

globalThis.ProgressEvent ??= class {};
const bytes = await readFile(new URL("../digital_twin/static/digital_twin/models/greenhouse.glb", import.meta.url));
const gltf = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), "");
let traversals = 0;
const traverse = gltf.scene.traverse.bind(gltf.scene);
gltf.scene.traverse = (callback) => { traversals++; traverse(callback); };
const registry = buildSceneRegistry(gltf.scene);
const live = new LiveState();
live.acceptSnapshot({ source: "mock_dynamic", connected: true, environment: { indoor_temperature_c: 28, indoor_rh_pct: 66, vpd_kpa: 0.8 },
  actuators: { roof_vent_left_pct: 72, roof_vent_right_pct: 35, shade_screen_1_pct: 40, shade_screen_2_pct: 12 } }, 1000);

test("single cached traversal builds honest membership and useful assets", () => {
  assert.equal(traversals, 1);
  for (const id of ["S01","S02","S03","S04"]) {
    assert.ok(!registry.spanRegistry[id].bounds.isEmpty());
    assert.equal(registry.spanRegistry[id].assets.filter(a=>a.type==="roof_vent").length, 2);
    assert.equal(registry.spanRegistry[id].assets.filter(a=>a.type==="sensor").length, 0);
  }
  for (const type of ["tank","pump","blower","filter","control_panel","sensor","side_curtain","crop_zone"]) {
    assert.ok([...registry.assetRegistry.values()].some(a=>a.type===type), type);
  }
  assert.ok(registry.assetTargets.length < registry.meshes.length / 5);
  assert.equal(registry.getAsset("GH_SENSOR_T_RH_01").spanId, null);
});

test("Greenhouse to span to asset to breadcrumb parent has one selection state", () => {
  const selection = new SelectionRuntime();
  const events = [];
  selection.subscribe(s=>events.push(s));
  selection.selectSpan("S02");
  selection.selectAsset(registry.getAsset("GH_VENT_S02_01"));
  assert.deepEqual(selection.state, {level:"asset",spanId:"S02",assetId:"GH_VENT_S02_01",assetType:"roof_vent"});
  selection.back();
  assert.equal(selection.state.level, "span");
  selection.back();
  assert.equal(selection.state.level, "greenhouse");
  selection.selectAsset(registry.getAsset("GH_FEED_PUMP"));
  assert.equal(selection.state.spanId, null);
  assert.throws(()=>selection.selectSpan("S99"));
  assert.equal(events.length, 6);
});

test("context uses house environment, real mapping, no sensor readings or fake history", () => {
  const base = { liveState: live, now: 1500 };
  const house = buildContextModel({...base,selection:{level:"greenhouse"}});
  assert.deepEqual(house.sections.map((x) => x.title), ["실내", "장치 (%)"]);   // no outdoor/status data in this snapshot
  assert.ok(house.sections[1].rows.some((r) => r.label === "천창" && r.value === "좌 72 · 우 35 %"));
  assert.ok(!JSON.stringify(house.sections).includes("시스템"));          // system state lives in the header status bar
  const span = buildContextModel({...base,selection:{level:"span",spanId:"S02"},spanAssets:registry.spanRegistry.S02.assets});
  assert.ok(JSON.stringify(span).includes("온실 전체 센서 1개 · 동별 값이 아닙니다"));
  assert.equal(span.sections[0].rows[0].value, "72.0%");
  assert.equal(span.sections[0].rows[3].value, "—");
  const sensor = registry.getAsset("GH_SENSOR_T_RH_01");
  const model = buildContextModel({...base,selection:{level:"asset",assetId:sensor.id},assetEntry:sensor,assetContext:mappedAssetContext(sensor,live)});
  assert.equal(model.sections.length,0);
  assert.ok(model.liveMessage.includes("확인된 실시간 연결이 없는"));
  assert.ok(HISTORY_EMPTY_MESSAGE.includes("아직 없습니다"));
});

test("span dimming caches variants, restores shared originals, leaves transforms unchanged", () => {
  const runtime = new VisibilityRuntime(registry);
  const mesh = registry.getByName("GH_ROOF_COVER_S02");
  const original = mesh.material, opacity = original.opacity, transform = mesh.matrix.clone();
  runtime.setSpanEmphasis("S01");
  const dimmed = mesh.material;
  assert.notEqual(dimmed, original);
  assert.equal(dimmed.opacity, opacity);
  runtime.setSpanEmphasis("S01");
  assert.equal(mesh.material, dimmed);
  assert.ok(mesh.matrix.equals(transform));
  runtime.restoreDefault();
  assert.equal(mesh.material, original);
  assert.equal(traversals,1);
});

test("camera focus interpolates actual selected bounds and presets preserve context", () => {
  const camera = new THREE.PerspectiveCamera(42,1.6,.05,2000);
  camera.position.set(150,80,120);
  const controls = {target:new THREE.Vector3(),update(){}};
  const runtime = new CameraRuntime({camera,controls,registry});
  const bounds = registry.spanRegistry.S02.bounds;
  const start = camera.position.clone();
  runtime.goTo("roof",{bounds,now:0});
  runtime.update(300);
  assert.ok(!camera.position.equals(start));
  runtime.update(600);
  assert.ok(controls.target.distanceTo(bounds.getCenter(new THREE.Vector3())) < 1e-8);
  runtime.goTo("front",{bounds,immediate:true});
  assert.ok(camera.position.x < bounds.min.x);
  runtime.goTo("rear",{bounds,immediate:true});
  assert.ok(camera.position.x > bounds.max.x);
  assert.equal(traversals,1);
});

test("actual raycasting selects span and assets; hidden ancestors are excluded; drag does not select", () => {
  const camera = new THREE.PerspectiveCamera(42,1.6,.05,2000);
  const handlers={};
  const dom={ addEventListener:(n,f)=>{handlers[n]=f;},removeEventListener(){},classList:{toggle(){},remove(){}},
    getBoundingClientRect:()=>({left:0,top:0,width:1440,height:900}) };
  let picked=null;
  const interaction = new InteractionRuntime({camera,domElement:dom,registry,tooltipRoot:null,onPick:r=>{picked=r;}});
  const target = registry.getAsset("GH_VENT_S02_01");
  const point = target.bounds.getCenter(new THREE.Vector3());
  camera.position.copy(point).add(new THREE.Vector3(0,25,0));
  camera.up.set(0,0,-1); camera.lookAt(point); camera.updateMatrixWorld();
  gltf.scene.updateMatrixWorld(true);
  const hit=interaction.pick({clientX:720,clientY:450});
  assert.equal(hit.entry.id,target.id);
  handlers.pointerdown({clientX:720,clientY:450,button:0});
  handlers.click({clientX:745,clientY:450});
  assert.equal(picked,null);
  handlers.click({clientX:720,clientY:450});
  assert.equal(picked.entry.id,target.id);
  const highlighted=hit.mesh.material;
  interaction.pick({clientX:720,clientY:450});
  assert.equal(hit.mesh.material,highlighted);
  const vents=registry.getByName("GH_VENTS"); vents.visible=false;
  assert.notEqual(interaction.pick({clientX:720,clientY:450})?.entry?.id,target.id);
  vents.visible=true;
  const cover=registry.getByName("GH_ROOF_COVER_S02");
  const vertex=new THREE.Vector3(-44,4.3,cover.position.z);
  const coverBox=new THREE.Box3().setFromObject(cover);
  vertex.copy(coverBox.getCenter(new THREE.Vector3())); vertex.x=coverBox.min.x+1;
  camera.position.copy(vertex).add(new THREE.Vector3(0,25,0));
  camera.lookAt(vertex); camera.updateMatrixWorld();
  assert.equal(interaction.pick({clientX:720,clientY:450})?.spanId,"S02");
  interaction.dispose();
});

test("selection focus bounds follow moving pivots and original actuator contract survives styling", () => {
  const runtime = new ActuatorRuntime({warn:()=>{}});
  runtime.bindScene(gltf.scene,{registry:registry.controlRegistry,byName:registry.byName});
  const state={level:"asset",assetId:"GH_VENT_S02_01"};
  const before=registry.getSelectionBounds(state);
  runtime.setTargets({roof_vent_left_pct:100,shade_screen_1_pct:20,shade_screen_2_pct:80}); // 1 -> diffuse, 2 -> shade
  for(let i=0;i<100;i++)runtime.update(.1);
  const after=registry.getSelectionBounds(state);
  assert.ok(!before.equals(after));
  assert.ok(Math.abs(registry.getByName("GH_SHADE_SCREEN_S01_N_PIVOT").scale.z-.2)<1e-6);
  assert.ok(Math.abs(registry.getByName("GH_DIFFUSE_SCREEN_S01_N_PIVOT").scale.z-.8)<1e-6);
  assert.equal(traversals,1);
});

test("selected label follows the moving object between snapshots without a scene scan", () => {
  const owner = new THREE.Mesh(new THREE.BoxGeometry(2,1,1));
  owner.name = "test vent";
  owner.userData.asset_type = "roof_vent";
  const camera = new THREE.PerspectiveCamera(42,1.6,.05,100);
  camera.position.set(0,3,12);
  camera.lookAt(0,0,0); camera.updateMatrixWorld();
  const fields = new Map();
  const root = { hidden:true, style:{}, querySelector(key) {
    if (!fields.has(key)) fields.set(key,{textContent:""});
    return fields.get(key);
  }};
  const label = new LabelRuntime({root,camera,domElement:{
    getBoundingClientRect:()=>({width:1440,height:900})
  }});
  label.setSelection({level:"asset",assetId:owner.name},{
    entry:{owner,type:"roof_vent"},bounds:new THREE.Box3().setFromObject(owner)
  });
  label.update();
  const before = root.style.transform;
  owner.position.x = 2;
  label.update();
  assert.notEqual(root.style.transform,before);
  assert.equal(traversals,1);
});

test("greenhouse panel shows faulty sensors as a state and adds outdoor, devices and field status", () => {
  const state = new LiveState();
  state.acceptSnapshot({ source: "field_collector", connected: true,
    environment: { indoor_temperature_c: 19.1, setpoint_temperature_c: 18, indoor_rh_pct: 99.9, dew_point_c: 19.1, vpd_kpa: 0.003,
      co2_ppm: 0, outdoor_temperature_c: 15.3, wind_speed_m_s: 0.3, wind_direction_text: "112° 동남동" },
    actuators: { roof_vent_left_pct: 30, roof_vent_right_pct: 30, shade_screen_1_pct: 100, shade_screen_2_pct: 100, boiler_on: false },
    status: { operation_mode: "자동", rain: true, strong_wind: false, alarm: false, caution: false, alarm_count: 0 } }, 1000);
  const model = buildContextModel({ liveState: state, now: 1500, selection: { level: "greenhouse" } });
  const rows = Object.fromEntries(model.sections.flatMap((x) => x.rows.map((r) => [r.label, r])));
  assert.deepEqual(model.sections.map((x) => x.title), ["실내", "외부", "장치 (%)", "운전 상태"]);
  assert.equal(rows["온도"].value, "19.1 °C");
  assert.equal(rows["온도"].note, "설정 18.0 °C");
  assert.equal(rows["습도"].value, "센서 점검 필요");                         // 99.9 % stuck: no number, no dew point / VPD
  assert.ok(!("CO₂" in rows));                                              // 0 ppm = no sensor
  assert.equal(rows["바람"].note, "112° 동남동");
  assert.equal(rows["비"].value, "비 옴");
  assert.equal(rows["보일러"].value, "꺼짐");
  assert.ok(!("순환팬" in rows));                                            // no value -> not shown
  assert.equal(rows["운전 모드"].value, "자동");
  assert.equal(rows["경보"].value, "없음");
});
