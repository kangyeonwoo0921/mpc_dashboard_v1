// "제어 상태" value tags in the 3D view: the current opening of every actuator, placed where it acts.
// The field reports one value per device for the whole greenhouse, so roof vents and screens are tagged once,
// on span 1 (S01, the representative span); side vents and vertical curtains are tagged on their own wall.
// Clicking a tag selects the device. All text is set with textContent.

import * as THREE from "../vendor/three/three.module.js";

import { cueChange } from "./motion-runtime.mjs";

const SPAN_TAGS = [
  // [label, dto key, asset to select, position along S01 (0 = front end, 1 = rear end), height]
  ["천창 좌", "roof_vent_left_pct", "GH_VENT_S01_01", 0.12, "ridge"],
  ["천창 우", "roof_vent_right_pct", "GH_VENT_S01_02", 0.3, "ridge"],
  ["차광 (알루미늄)", "shade_screen_2_pct", "GH_SHADE_SCREEN_S01_N", 0.7, "screen"],
  ["산광", "shade_screen_1_pct", "GH_DIFFUSE_SCREEN_S01_N", 0.88, "screen"],
];
const WALL_TAGS = [
  // [label, outer curtain (측창), inner curtain (수직커튼), dto suffix]
  ["정면", "GH_SIDE_VENT_FRONT", "GH_VERTICAL_CURTAIN_FRONT", "front"],
  ["후면", "GH_SIDE_VENT_REAR", "GH_VERTICAL_CURTAIN_REAR", "rear"],
  ["좌측", "GH_SIDE_CURTAIN_LEFT", "GH_VERTICAL_CURTAIN_LEFT", "left"],
  ["우측", "GH_SIDE_CURTAIN_RIGHT", "GH_VERTICAL_CURTAIN_RIGHT", "right"],
];

export function percentText(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value)}%` : "—";
}

/** Tag anchors in world space from the loaded model: [{ title, rows: [{label, key}], select, anchor }]. */
export function controlTagSpecs(model) {
  model.updateWorldMatrix(true, true);
  const world = (name) => model.getObjectByName(name)?.getWorldPosition(new THREE.Vector3()) ?? null;
  const specs = [];
  const ventPivot = world("GH_VENT_S01_01_PIVOT");
  const screenN = world("GH_SHADE_SCREEN_S01_N_PIVOT");
  const screenP = world("GH_SHADE_SCREEN_S01_P_PIVOT");
  const span = model.getObjectByName("GH_SHADE_SCREEN_S01_N");
  if (ventPivot && screenN && screenP && span) {
    const box = new THREE.Box3().setFromObject(span);
    for (const [title, key, select, along, level] of SPAN_TAGS) {
      const x = box.min.x + along * (box.max.x - box.min.x);
      const anchor = level === "ridge"
        ? new THREE.Vector3(x, ventPivot.y + 0.6, ventPivot.z)
        : new THREE.Vector3(x, screenN.y, (screenN.z + screenP.z) / 2);
      specs.push({ id: key, title, rows: [{ label: "", key }], select, anchor });
    }
  }
  for (const [title, outer, inner, side] of WALL_TAGS) {
    const anchor = world(outer) ?? world(inner);
    if (!anchor) continue;
    anchor.y += 0.5;
    specs.push({ id: `wall_${side}`, title, select: model.getObjectByName(outer) ? outer : inner, anchor,
      rows: [{ label: "측창", key: `side_vent_${side}_pct` }, { label: "수직커튼", key: `vertical_curtain_${side}_pct` }] });
  }
  return specs;
}

export class ControlTags {
  constructor({ root, camera, domElement, onSelect = () => {} }) {
    this.root = root;
    this.camera = camera;
    this.domElement = domElement;
    this.onSelect = onSelect;
    this.tags = [];
    this.enabled = false;
    this.values = {};
    this.projected = new THREE.Vector3();
  }

  bind(model) {
    this.tags = controlTagSpecs(model).map((spec) => {
      const node = document.createElement("button");
      node.type = "button";
      node.className = "control-tag";
      const title = document.createElement("strong");
      title.textContent = spec.title;
      node.append(title);
      const rows = spec.rows.map((row) => {
        const line = document.createElement("span");
        line.className = "control-tag-row";
        if (row.label) line.append(Object.assign(document.createElement("small"), { textContent: row.label }));
        const value = document.createElement("b");
        const bar = document.createElement("i");
        bar.className = "control-tag-bar";
        bar.append(document.createElement("i"));
        line.append(value, bar);
        node.append(line);
        return { key: row.key, value, fill: bar.firstChild };
      });
      node.addEventListener("click", () => this.onSelect(spec.select));
      this.root.append(node);
      return { spec, node, rows };
    });
    this.#render();
  }

  setEnabled(enabled) {
    if (this.enabled === Boolean(enabled)) return;
    this.enabled = Boolean(enabled);
    this.root.hidden = !this.enabled;
  }

  setActuators(actuators) {
    this.values = actuators ?? {};
    this.#render();
  }

  #render() {
    for (const tag of this.tags) {
      for (const row of tag.rows) {
        const value = this.values[row.key];
        const text = percentText(value);
        if (row.value.textContent !== text) {
          const changed = row.value.textContent !== "";
          row.value.textContent = text;
          if (changed && this.enabled) cueChange(row.value);
        }
        row.fill.style.width = typeof value === "number" ? `${Math.min(100, Math.max(0, value))}%` : "0%";
      }
    }
  }

  update() {
    if (!this.enabled) return;
    const rect = this.domElement.getBoundingClientRect();
    const shown = [];
    for (const tag of this.tags) {
      this.projected.copy(tag.spec.anchor).project(this.camera);
      const visible = this.projected.z >= -1 && this.projected.z <= 1
        && Math.abs(this.projected.x) <= 1.05 && Math.abs(this.projected.y) <= 1.05;
      tag.node.hidden = !visible;
      if (!visible) continue;
      shown.push({ tag, depth: this.projected.z, x: (this.projected.x * 0.5 + 0.5) * rect.width,
        y: (-this.projected.y * 0.5 + 0.5) * rect.height, w: tag.node.offsetWidth, h: tag.node.offsetHeight });
    }
    // Nearest tags keep their place; a tag that would cover one already placed moves up above it.
    shown.sort((a, b) => a.depth - b.depth);
    const placed = [];
    for (const item of shown) {
      const lead = 10;
      let top = item.y - lead - item.h;
      const left = item.x - item.w / 2;
      for (let pass = 0; pass < placed.length + 1; pass += 1) {
        const hit = placed.find((p) => left < p.left + p.w + 4 && left + item.w + 4 > p.left && top < p.top + p.h + 4 && top + item.h + 4 > p.top);
        if (!hit) break;
        top = hit.top - item.h - 4;
      }
      placed.push({ left, top, w: item.w, h: item.h });
      item.tag.node.style.transform = `translate(${left}px, ${top}px)`;
      item.tag.node.style.setProperty("--lead", `${Math.max(lead, item.y - top - item.h)}px`);
    }
  }
}
