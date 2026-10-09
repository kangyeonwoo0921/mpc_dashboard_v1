import * as THREE from "../vendor/three/three.module.js";

export const SOLAR_ENDPOINTS = Object.freeze({
  v1: "/api/digital-twin/radiation/v1/",
  reference: "/api/digital-twin/solar/",
});

export const SOLAR_CONFIG = Object.freeze({
  endpoint: SOLAR_ENDPOINTS.v1,
  refreshMs: 5 * 60 * 1000,
  sunDistance: 85,
  shadowExtent: 72,
  shadowMapSize: 4096,
  lightMapOpacity: 0.78,
  shadowRefreshMs: 250,
});

// Frame members and the shade screen cast the visual shadows; film surfaces do not.
const SHADOW_CASTERS = new Set([
  "rafter", "truss", "main_column", "secondary_column", "gutter", "roof_frame",
  "end_wall_post", "end_wall_rail", "vent_frame", "shade_screen",
]);
const SHADOW_RECEIVERS = new Set(["ground", "crop_bed", "crop_plant", "end_closure", "sidewall_fixed"]);

export function physicsToThree([x, y, z]) {
  return [x, z, -y];
}

/**
 * One shape for both backends. v1 (spec model) shows total irradiance when every
 * cell has a value, otherwise the binary sunlit map; the reference model shows PAR.
 */
export function normalizeSolarPayload(payload) {
  if (payload.model === "radiation_v1") {
    const grid = payload.radiation.grid;
    const haveTotals = grid.total_W_m2.some((v) => v !== null) && grid.total_W_m2.every((v, i) => v !== null || grid.sunlit[i] === null);
    return {
      timestamp: payload.timestamp,
      sun: { altitude_deg: payload.solar.altitude_deg, azimuth_deg: payload.solar.azimuth_deg, direction_threejs: payload.solar.direction_threejs },
      sunPath: payload.solar.path_threejs,
      height: grid.height_m,
      grid: {
        rows: grid.rows, cols: grid.cols, cell: grid.cell_size_m, origin: grid.origin_xy_m,
        values: haveTotals ? grid.total_W_m2 : grid.sunlit.map((v) => (v === null ? null : Number(v))),
        mode: haveTotals ? "irradiance" : "sunlit",
      },
      summary: { status: payload.radiation.status, sunlitFraction: payload.radiation.sunlit_fraction, mean: payload.radiation.mean_W_m2, unit: "W/m²" },
    };
  }
  return {
    timestamp: payload.timestamp,
    sun: payload.sun,
    sunPath: payload.sun_path_threejs ?? [],
    height: payload.canopy_height_m,
    grid: {
      rows: payload.grid.rows, cols: payload.grid.cols, cell: payload.grid.cell_size_m, origin: payload.grid.origin_xy_m,
      values: payload.grid.par_w_m2, mode: "irradiance",
    },
    summary: { status: payload.outside?.source ?? "reference", sunlitFraction: payload.mean?.sunlit_fraction ?? null, mean: payload.mean?.par_w_m2 ?? null, unit: "PAR W/m²" },
  };
}

function assetType(object) {
  for (let node = object; node; node = node.parent) {
    if (node.userData?.asset_type) return node.userData.asset_type;
  }
  return null;
}

// Blue (dark) -> green -> yellow -> white, readable on the dark viewport.
const RAMP = [[0.0, [24, 40, 92]], [0.35, [32, 140, 132]], [0.7, [236, 206, 72]], [1.0, [255, 248, 228]]];
export function rampColor(t) {
  const v = Math.min(1, Math.max(0, t));
  for (let i = 1; i < RAMP.length; i += 1) {
    const [t1, c1] = RAMP[i];
    const [t0, c0] = RAMP[i - 1];
    if (v <= t1) {
      const f = (v - t0) / (t1 - t0);
      return c0.map((c, k) => Math.round(c + (c1[k] - c) * f));
    }
  }
  return RAMP[RAMP.length - 1][1];
}

function glowTexture() {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const context = canvas.getContext("2d");
  const gradient = context.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(255,240,190,1)");
  gradient.addColorStop(0.25, "rgba(255,214,120,0.55)");
  gradient.addColorStop(1, "rgba(255,190,90,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, size, size);
  return new THREE.CanvasTexture(canvas);
}

export class SolarRuntime {
  constructor({ scene, renderer, model, dimmedLights = [], fetchImpl = globalThis.fetch?.bind(globalThis), config = SOLAR_CONFIG, endpoint = config.endpoint }) {
    this.scene = scene;
    this.config = config;
    this.endpoint = endpoint;
    this.fetchImpl = fetchImpl;
    this.dimmedLights = dimmedLights.map((light) => ({ light, intensity: light.intensity }));
    this.sunEnabled = true;
    this.lightMapEnabled = false;
    this.state = null;
    this.requestId = 0;

    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // The sun moves over minutes and actuators over seconds, so the shadow map is
    // redrawn on a short interval instead of every frame.
    renderer.shadowMap.autoUpdate = false;
    renderer.shadowMap.needsUpdate = true;
    this.shadowMap = renderer.shadowMap;
    this.lastShadowMs = -Infinity;

    this.light = new THREE.DirectionalLight(0xfff1d6, 2.6);
    this.light.castShadow = true;
    const camera = this.light.shadow.camera;
    camera.left = camera.bottom = -config.shadowExtent;
    camera.right = camera.top = config.shadowExtent;
    camera.near = 1;
    camera.far = config.sunDistance * 2.2;
    this.light.shadow.mapSize.set(config.shadowMapSize, config.shadowMapSize);
    this.light.shadow.bias = -0.0004;
    this.light.shadow.normalBias = 0.02;
    scene.add(this.light, this.light.target);

    this.sun = new THREE.Group();
    const disc = new THREE.Mesh(new THREE.SphereGeometry(3.6, 24, 16), new THREE.MeshBasicMaterial({ color: 0xffd98a, fog: false }));
    const map = typeof document === "undefined" ? null : glowTexture(); // headless tests have no canvas
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map, color: 0xffffff, transparent: true, depthWrite: false, fog: false }));
    glow.scale.set(36, 36, 1);
    this.sun.add(disc, glow);
    this.sun.name = "SOLAR_SUN_MARKER";
    scene.add(this.sun);

    this.casters = 0;
    model.traverse((object) => {
      if (!object.isMesh) return;
      const type = assetType(object);
      if (SHADOW_CASTERS.has(type)) {
        object.castShadow = true;
        this.casters += 1;
      }
      if (SHADOW_RECEIVERS.has(type)) object.receiveShadow = true;
    });

    this.lightMap = null;
    this.path = new THREE.Line(
      new THREE.BufferGeometry(),
      new THREE.LineDashedMaterial({ color: 0xd9b45f, dashSize: 3, gapSize: 2, transparent: true, opacity: 0.6, fog: false }),
    );
    this.path.name = "SOLAR_SUN_PATH";
    scene.add(this.path);
    this.setSunEnabled(true);
  }

  tick(timeMs) {
    if (timeMs - this.lastShadowMs >= this.config.shadowRefreshMs) {
      this.shadowMap.needsUpdate = true;
      this.lastShadowMs = timeMs;
    }
  }

  setSunEnabled(enabled) {
    this.sunEnabled = enabled;
    this.#applyVisibility();
  }

  setLightMapEnabled(enabled) {
    this.lightMapEnabled = enabled;
    if (this.lightMap) this.lightMap.visible = enabled;
  }

  async refresh(time = null) {
    const requestId = ++this.requestId;
    const url = time ? `${this.endpoint}?time=${encodeURIComponent(time)}` : this.endpoint;
    const response = await this.fetchImpl(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`Solar API ${response.status}`);
    const payload = await response.json();
    if (requestId === this.requestId) this.apply(payload);
    return payload;
  }

  apply(raw) {
    const payload = normalizeSolarPayload(raw);
    this.state = payload;
    const [x, y, z] = payload.sun.direction_threejs;
    const direction = new THREE.Vector3(x, y, z).normalize();
    this.sun.position.copy(direction).multiplyScalar(this.config.sunDistance);
    this.light.position.copy(this.sun.position);
    this.light.target.position.set(0, 0, 0);
    const height = Math.max(0, Math.sin(THREE.MathUtils.degToRad(payload.sun.altitude_deg)));
    this.light.intensity = 0.6 + 2.4 * Math.min(1, height * 1.4);
    // Warmer, weaker light near the horizon.
    this.light.color.setHSL(0.1, 0.55 - 0.35 * Math.min(1, height * 1.5), 0.75);
    const points = (payload.sunPath ?? []).map((v) => new THREE.Vector3(...v).normalize().multiplyScalar(this.config.sunDistance));
    this.path.geometry.setFromPoints(points);
    this.path.computeLineDistances();
    this.#updateLightMap(payload);
    this.#applyVisibility();
    this.shadowMap.needsUpdate = true;
    return payload;
  }

  #applyVisibility() {
    const above = (this.state?.sun.altitude_deg ?? 0) > 0;
    const on = this.sunEnabled && above;
    this.sun.visible = on;
    this.light.visible = on;
    this.path.visible = this.sunEnabled && this.state !== null;
    for (const { light, intensity } of this.dimmedLights) light.intensity = on ? intensity * 0.35 : intensity;
  }

  #updateLightMap(payload) {
    const { rows, cols, cell, origin: [x0, y0], values, mode } = payload.grid;
    const finite = values.filter((v) => v !== null);
    const max = mode === "sunlit" ? 1 : Math.max(1, ...finite);
    const data = new Uint8Array(rows * cols * 4);
    values.forEach((value, index) => {
      const [r, g, b] = rampColor(value === null ? 0 : value / max);
      data.set([r, g, b, value === null ? 0 : 255], index * 4);
    });
    if (!this.lightMap) {
      const texture = new THREE.DataTexture(data, cols, rows, THREE.RGBAFormat);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.magFilter = THREE.LinearFilter;
      const material = new THREE.MeshBasicMaterial({
        map: texture, transparent: true, opacity: this.config.lightMapOpacity, depthWrite: false, side: THREE.DoubleSide, fog: false,
      });
      this.lightMap = new THREE.Mesh(new THREE.PlaneGeometry(cols * cell, rows * cell), material);
      this.lightMap.name = "SOLAR_LIGHT_MAP";
      this.lightMap.rotation.x = -Math.PI / 2; // plane +Y (rows, physics +Y) -> world -Z
      this.lightMap.renderOrder = 5;
      this.scene.add(this.lightMap);
    } else {
      this.lightMap.material.map.image.data.set(data);
      this.lightMap.material.map.needsUpdate = true;
    }
    const [cx, cy, cz] = physicsToThree([x0 + cols * cell / 2, y0 + rows * cell / 2, payload.height + 0.05]);
    this.lightMap.position.set(cx, cy, cz);
    this.lightMap.visible = this.lightMapEnabled;
    this.maxPar = max;
  }
}
