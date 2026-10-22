// Wind through the greenhouse in the 3D view: small arrows keep flowing through every open window.
// Display rule (user decision 2026-10-22): a side vent facing into the measured wind takes air in, one facing
// away lets it out, and one nearly parallel to the wind (within parallelDeg) or in calm air shows nothing; open
// roof vents always let air out, wind or not (in through the sides, out through the roof).
// Inputs: LIVE wind_speed_m_s, wind_direction_text ("67° 동북동", the direction the wind blows FROM, clockwise
// from true north), actuator openings, and the greenhouse long-axis azimuth (config/physics/site.json).
// Axes as physics/coordinates.py: physics +X = long axis (X1 -> X23) at azimuth A, +Y its left, three = (x, z, -y).

import * as THREE from "../vendor/three/three.module.js";

export const WIND_CONFIG = Object.freeze({
  calmBelowMs: 0.1,          // side vents show no flow below this speed (sensor step 0.1 m/s; field daytime median 0.5)
  fullAtMs: 6,               // flow speed stops growing here
  openBelowPct: 2,           // a window counts as open above this opening
  parallelDeg: 20,           // side vents within this angle of parallel to the wind show no flow
  arrowsPerWindow: 3,
  travelM: 4,                // each arrow runs this far through the opening, then starts again
  arrowSizeM: 2,
});

/** Degrees from a field text like "67° 동북동" (or a number); null when unreadable. */
export function parseWindDirection(text) {
  if (typeof text === "number" && Number.isFinite(text)) return ((text % 360) + 360) % 360;
  const match = typeof text === "string" ? text.match(/(-?\d+(?:\.\d+)?)\s*°?/) : null;
  return match ? ((Number(match[1]) % 360) + 360) % 360 : null;
}

/** Unit vector (three.js, horizontal) the air moves toward, for a wind blowing FROM `fromDeg`. */
export function windFlowThree(fromDeg, longAxisAzimuthDeg) {
  const to = (fromDeg + 180) * Math.PI / 180;
  const a = longAxisAzimuthDeg * Math.PI / 180;
  const east = Math.sin(to), north = Math.cos(to);
  const x = east * Math.sin(a) + north * Math.cos(a);
  const y = -east * Math.cos(a) + north * Math.sin(a);
  return new THREE.Vector3(x, 0, -y).normalize();
}

/**
 * +1 = air flows in through an opening, -1 = out, 0 = none (calm, or a side vent nearly parallel to the wind).
 * kind "roof" always flows out; kind "side" compares its horizontal outward normal with the wind.
 */
export function openingFlow(normal, flow, speed, config = WIND_CONFIG, kind = "side") {
  if (kind === "roof") return -1;
  if (!flow || !(speed >= config.calmBelowMs)) return 0;
  const horizontal = new THREE.Vector3(normal.x, 0, normal.z).normalize();
  const facing = horizontal.dot(flow);
  if (Math.abs(facing) < Math.sin(config.parallelDeg * Math.PI / 180)) return 0;
  return facing < 0 ? 1 : -1;
}

function solidArrowGeometry() {
  // Round shaft + cone head along +X, 1 m long, readable from any viewing angle.
  const shaft = new THREE.CylinderGeometry(0.06, 0.06, 0.62, 10);
  shaft.rotateZ(-Math.PI / 2);
  shaft.translate(-0.19, 0, 0);
  const head = new THREE.ConeGeometry(0.17, 0.38, 14);
  head.rotateZ(-Math.PI / 2);
  head.translate(0.31, 0, 0);
  const geometry = new THREE.BufferGeometry();
  const merge = (parts) => {
    const positions = [], normals = [], indices = [];
    let offset = 0;
    for (const part of parts) {
      const g = part.toNonIndexed();
      positions.push(...g.attributes.position.array);
      normals.push(...g.attributes.normal.array);
      for (let i = 0; i < g.attributes.position.count; i += 1) indices.push(offset + i);
      offset += g.attributes.position.count;
    }
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
    geometry.setIndex(indices);
  };
  merge([shaft, head]);
  return geometry;
}

export class WindRuntime {
  constructor({ scene, model, longAxisAzimuthDeg, config = WIND_CONFIG }) {
    this.config = config;
    this.azimuth = longAxisAzimuthDeg;
    this.enabled = true;
    this.speed = 0;
    this.flow = null;
    this.openings = {};
    this.phase = 0;
    this.group = new THREE.Group();
    this.group.name = "VIEWER_WIND";
    scene.add(this.group);
    model.updateWorldMatrix(true, true);
    this.bounds = new THREE.Box3().setFromObject(model.getObjectByName("GH_STRUCTURE") ?? model);
    this.#buildOpenings(model);
    this.#refresh();
  }

  #buildOpenings(model) {
    const center = this.bounds.getCenter(new THREE.Vector3());
    const top = this.bounds.max.y;
    this.windows = [];
    // Side vents: the curtain is wound up from the lower wall, so the opening starts at the bottom of the band.
    const walls = [["side_vent_front_pct", "GH_SIDE_VENT_FRONT"], ["side_vent_rear_pct", "GH_SIDE_VENT_REAR"],
      ["side_vent_left_pct", "GH_SIDE_CURTAIN_LEFT"], ["side_vent_right_pct", "GH_SIDE_CURTAIN_RIGHT"]];
    for (const [key, name] of walls) {
      const root = model.getObjectByName(name);
      const panel = model.getObjectByName(`${name}_PANEL`);
      if (!root || !panel) continue;
      const eave = root.getWorldPosition(new THREE.Vector3()).y;
      const fullHeight = root.userData.full_height ?? 4.2;
      const box = new THREE.Box3().setFromObject(panel);
      const alongX = box.max.x - box.min.x > box.max.z - box.min.z;
      const normal = alongX ? new THREE.Vector3(0, 0, Math.sign(box.min.z - center.z)) : new THREE.Vector3(Math.sign(box.min.x - center.x), 0, 0);
      for (const t of [0.2, 0.5, 0.8]) {
        const position = alongX
          ? new THREE.Vector3(box.min.x + t * (box.max.x - box.min.x), 0, box.min.z)
          : new THREE.Vector3(box.min.x, 0, box.min.z + t * (box.max.z - box.min.z));
        this.windows.push({ key, kind: "side", position, normal, band: { bottom: eave - fullHeight, height: fullHeight } });
      }
    }
    // Roof vents: one stream per vent leaf at mid length; the gap faces the leaf's side of the ridge.
    model.traverse((object) => {
      const match = /^GH_VENT_S0[1-4]_(01|02)_PIVOT$/.exec(object.name ?? "");
      if (!match) return;
      const side = object.userData?.side === "negative_y" ? -1 : object.userData?.side === "positive_y" ? 1 : match[1] === "01" ? 1 : -1;
      const pivot = object.getWorldPosition(new THREE.Vector3());
      // physics +Y is three -Z
      this.windows.push({ key: match[1] === "01" ? "roof_vent_left_pct" : "roof_vent_right_pct", kind: "roof",
        position: new THREE.Vector3(center.x, Math.min(top, pivot.y + 0.3), pivot.z - side * 1.2),
        normal: new THREE.Vector3(0, 0.8, -side).normalize() });
    });
    this.inMaterial = new THREE.MeshBasicMaterial({ color: 0x8fd0ac, transparent: true, opacity: 0.95, depthWrite: false,
      depthTest: false, fog: false });
    this.outMaterial = this.inMaterial.clone();
    this.outMaterial.color.set(0xf0b46a);
    const geometry = solidArrowGeometry();
    for (const window of this.windows) {
      window.arrows = Array.from({ length: this.config.arrowsPerWindow }, () => {
        const mesh = new THREE.Mesh(geometry, this.inMaterial);
        mesh.renderOrder = 6;
        mesh.visible = false;
        this.group.add(mesh);
        return mesh;
      });
    }
  }

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    this.group.visible = this.enabled;
  }

  /** environment: LIVE environment block; actuators: LIVE actuator openings (%). */
  setLive(environment, actuators) {
    const from = parseWindDirection(environment?.wind_direction_text);
    const speed = environment?.wind_speed_m_s;
    this.speed = typeof speed === "number" && Number.isFinite(speed) ? speed : 0;
    this.flow = from === null || !Number.isFinite(this.azimuth) ? null : windFlowThree(from, this.azimuth);
    this.openings = actuators ?? {};
    this.#refresh();
  }

  #strength() {
    return Math.min(1, this.speed / this.config.fullAtMs);
  }

  /** Which windows stream, which way, and where (call when the LIVE values change). */
  #refresh() {
    for (const window of this.windows) {
      const opening = this.openings[window.key];
      const direction = openingFlow(window.normal, this.flow, this.speed, this.config, window.kind);
      window.active = direction !== 0 && typeof opening === "number" && opening > this.config.openBelowPct;
      if (!window.active) {
        for (const mesh of window.arrows) mesh.visible = false;
        continue;
      }
      window.center = window.position.clone();
      if (window.band) window.center.y = window.band.bottom + window.band.height * Math.min(1, opening / 100) / 2;
      // inflow runs inward (against the outward normal), outflow outward
      window.pointing = window.normal.clone().multiplyScalar(-direction);
      const quaternion = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(1, 0, 0), window.pointing);
      for (const mesh of window.arrows) {
        mesh.quaternion.copy(quaternion);
        mesh.material = direction > 0 ? this.inMaterial : this.outMaterial;
      }
    }
    this.#place();
  }

  #place() {
    const { travelM, arrowsPerWindow, arrowSizeM } = this.config;
    for (const window of this.windows) {
      if (!window.active) continue;
      window.arrows.forEach((mesh, index) => {
        const t = (this.phase + index / arrowsPerWindow) % 1;
        // runs through the opening (t = 0.5 is the opening) and grows in and out at the ends
        mesh.position.copy(window.center).addScaledVector(window.pointing, (t - 0.5) * travelM);
        const size = arrowSizeM * Math.sin(Math.PI * t);
        mesh.scale.set(size, size, size);
        mesh.visible = size > 0.02;
      });
    }
  }

  /** Advance the streams (call every frame); faster wind, faster flow. */
  tick(deltaSeconds) {
    if (!this.enabled || !this.windows.some((window) => window.active)) return;
    this.phase = (this.phase + (0.35 + 0.9 * this.#strength()) * Math.max(0, deltaSeconds)) % 1;
    this.#place();
  }
}
