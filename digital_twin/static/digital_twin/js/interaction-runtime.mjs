import * as THREE from "../vendor/three/three.module.js";

import { ASSET_LABELS, SCENE_COLORS } from "./viewer-config.mjs";

function titleCase(value) {
  return String(value ?? "").split("_").filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

export function displayTitle(object, semanticType = null) {
  const metadata = object?.userData ?? {};
  const sensorLabels = { temperature_rh: "온습도 센서", solar_radiation: "일사 센서" };
  const type = semanticType ?? metadata.asset_type;
  const base = type === "sensor"
    ? sensorLabels[metadata.sensor_type] ?? "센서"
    : type === "crop_zone"
      ? "재배 구역"
      : ASSET_LABELS[type] ?? ASSET_LABELS[metadata.asset_type] ?? titleCase(type) ?? object?.name ?? "객체";
  const span = Number(metadata.span_index);
  return Number.isFinite(span) && span > 0 ? `${base} — ${span}동` : base;
}

export function formatInspectionData(object, { openingPercent = null, mappingNote = null } = {}) {
  if (!object) return { title: "", rows: [] };
  const metadata = object.userData ?? {};
  const rows = [];
  const add = (label, value) => {
    if (value !== null && value !== undefined && value !== "") rows.push({ label, value: String(value) });
  };
  add("이름", object.name);
  add("종류", metadata.asset_type);
  add("동 번호", metadata.span_index);
  add("제어 변수", metadata.control_variable);
  if (typeof openingPercent === "number" && Number.isFinite(openingPercent)) add("열림", `${openingPercent.toFixed(1)}%`);
  else if (typeof metadata.opening_percent === "number") add("열림", `${metadata.opening_percent.toFixed(1)}%`);
  if (typeof metadata.verified === "boolean") add("확인", metadata.verified ? "확인됨" : "미확인");
  else if (typeof metadata.verified_position === "boolean") add("위치", metadata.verified_position ? "확인됨" : "미확인");
  add("출처 신뢰도", metadata.source_confidence);
  add("형상 신뢰도", metadata.geometry_confidence);
  add("위치 신뢰도", metadata.position_confidence);
  if (typeof metadata.plc_tag_verified === "boolean") add("PLC 태그", metadata.plc_tag_verified ? "확인됨" : "미확인");
  add("연결 상태", mappingNote);
  return { title: displayTitle(object), rows };
}

export function formatTooltipText(subject, context = {}) {
  if (subject?.kind === "span") return [`${Number(subject.spanId.slice(1))}동`, "클릭하면 확대"];
  const object = subject?.entry?.owner ?? subject;
  const type = subject?.entry?.type ?? null;
  const details = formatInspectionData(object, context);
  details.title = displayTitle(object, type);
  const preferred = details.rows.filter((row) => ["열림", "위치", "연결 상태"].includes(row.label));
  return [details.title, ...preferred.map((row) => `${row.label}: ${row.value}`)];
}

export function isVisibleInHierarchy(object) {
  for (let node = object; node; node = node.parent) if (!node.visible) return false;
  return true;
}

function setTooltipContent(root, lines) {
  root.replaceChildren();
  lines.forEach((line, index) => {
    const node = document.createElement(index === 0 ? "strong" : "span");
    node.textContent = line;
    root.append(node);
  });
}

export class InteractionRuntime {
  constructor({
    camera,
    domElement,
    registry,
    tooltipRoot,
    contextForRecord = () => ({}),
    onPick = () => {},
    onHoverChange = () => {},
  }) {
    this.camera = camera;
    this.domElement = domElement;
    this.registry = registry;
    this.tooltipRoot = tooltipRoot;
    this.contextForRecord = contextForRecord;
    this.onPick = onPick;
    this.onHoverChange = onHoverChange;
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.hovered = null;
    this.selectedRecord = null;
    this.highlighted = new Map();
    this.edgeCache = new Map();
    this.pendingPointer = null;
    this.labelsEnabled = true;
    this.frameRequested = false;
    this.boundMove = (event) => this.handlePointerMove(event);
    this.boundLeave = () => this.clearHover();
    this.pointerDown = null;
    this.boundDown = (event) => { this.pointerDown = { x: event.clientX, y: event.clientY, button: event.button }; };
    this.boundClick = (event) => {
      if (!this.pointerDown || this.pointerDown.button !== 0 ||
          Math.hypot(event.clientX - this.pointerDown.x, event.clientY - this.pointerDown.y) > 5) return;
      this.pick(event);
      this.selectHovered();
    };
    domElement.addEventListener("pointerdown", this.boundDown);
    domElement.addEventListener("pointermove", this.boundMove);
    domElement.addEventListener("pointerleave", this.boundLeave);
    domElement.addEventListener("click", this.boundClick);
  }

  handlePointerMove(event) {
    this.pendingPointer = { clientX: event.clientX, clientY: event.clientY };
    if (this.frameRequested) return;
    this.frameRequested = true;
    requestAnimationFrame(() => {
      this.frameRequested = false;
      if (this.pendingPointer) this.pick(this.pendingPointer);
    });
  }

  pick(pointer) {
    const rect = this.domElement.getBoundingClientRect();
    this.pointer.x = ((pointer.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((pointer.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const assetHit = this.raycaster.intersectObjects(this.registry.assetTargets.filter(isVisibleInHierarchy), false)[0] ?? null;
    const spanHit = this.raycaster.intersectObjects(this.registry.spanTargets.filter(isVisibleInHierarchy), false)[0] ?? null;
    let record = null;
    if (assetHit && (!spanHit || assetHit.distance <= spanHit.distance + 1.25)) {
      record = { ...this.registry.assetRecordByMesh.get(assetHit.object), mesh: assetHit.object };
    } else if (spanHit) {
      record = { ...this.registry.spanRecordByMesh.get(spanHit.object), mesh: spanHit.object };
    }
    const changed = record?.kind !== this.hovered?.kind
      || record?.spanId !== this.hovered?.spanId
      || record?.entry?.id !== this.hovered?.entry?.id
      || record?.mesh !== this.hovered?.mesh;
    this.hovered = record;
    this.domElement.classList.toggle("is-inspecting", Boolean(record));
    if (changed) this.refreshHighlights();
    this.#renderTooltip(pointer, rect);
    if (changed) this.onHoverChange(record);
    return record;
  }

  selectHovered() {
    if (this.hovered) this.onPick(this.hovered);
  }

  setSelectedRecord(record) {
    this.selectedRecord = record ?? null;
    this.refreshHighlights();
  }

  setLabelsEnabled(enabled) {
    this.labelsEnabled = Boolean(enabled);
    if (!this.labelsEnabled && this.tooltipRoot) this.tooltipRoot.hidden = true;
    else if (this.pendingPointer) this.#renderTooltip(this.pendingPointer, this.domElement.getBoundingClientRect());
  }

  refreshTooltip() {
    if (this.pendingPointer) this.#renderTooltip(this.pendingPointer, this.domElement.getBoundingClientRect());
  }

  clearHover() {
    this.pendingPointer = null;
    const changed = Boolean(this.hovered);
    this.hovered = null;
    this.domElement.classList.remove("is-inspecting");
    if (this.tooltipRoot) this.tooltipRoot.hidden = true;
    this.refreshHighlights();
    if (changed) this.onHoverChange(null);
  }

  resetHighlights() {
    for (const [mesh, record] of this.highlighted) {
      mesh.material = record.original;
      record.highlighted.forEach((material) => material.dispose());
    }
    this.highlighted.clear();
    for (const edge of this.edgeCache.values()) edge.visible = false;
  }

  refreshHighlights() {
    const desired = new Map();
    if (this.hovered?.mesh) desired.set(this.hovered.mesh, "hover");
    if (this.selectedRecord?.kind === "asset") {
      this.selectedRecord.entry.meshes.forEach((mesh) => desired.set(mesh, "selected"));
    }
    for (const [mesh, record] of this.highlighted) {
      if (desired.get(mesh) === record.mode && mesh.material === record.applied) continue;
      mesh.material = record.original;
      record.highlighted.forEach((material) => material.dispose());
      this.highlighted.delete(mesh);
      const edge = this.edgeCache.get(mesh);
      if (edge) edge.visible = false;
    }
    for (const [mesh, mode] of desired) if (!this.highlighted.has(mesh)) this.#highlight(mesh, mode);
  }

  #highlight(mesh, mode) {
    const original = mesh.material;
    const sourceMaterials = Array.isArray(original) ? original : [original];
    const highlighted = sourceMaterials.map((source) => {
      const material = source.clone();
      const color = new THREE.Color(mode === "selected" ? SCENE_COLORS.selected : SCENE_COLORS.hover);
      if (material.emissive) {
        material.emissive.copy(color).multiplyScalar(mode === "selected" ? 0.34 : 0.2);
        material.emissiveIntensity = mode === "selected" ? 0.48 : 0.3;
      }
      material.color?.lerp(color, mode === "selected" ? 0.18 : 0.1);
      return material;
    });
    mesh.material = Array.isArray(original) ? highlighted : highlighted[0];
    this.highlighted.set(mesh, { original, highlighted, mode, applied: mesh.material });
    if (mesh.userData?.asset_type === "roof_vent") {
      let edge = this.edgeCache.get(mesh);
      if (!edge) {
        edge = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 25),
          new THREE.LineBasicMaterial({ color: SCENE_COLORS.selected, transparent: true, opacity: 0.65 }));
        edge.raycast = () => {};
        mesh.add(edge);
        this.edgeCache.set(mesh, edge);
      }
      edge.visible = true;
    }
  }

  #renderTooltip(pointer, rect) {
    if (!this.tooltipRoot || !this.labelsEnabled || !this.hovered) {
      if (this.tooltipRoot) this.tooltipRoot.hidden = true;
      return;
    }
    setTooltipContent(this.tooltipRoot, formatTooltipText(this.hovered, this.contextForRecord(this.hovered)));
    this.tooltipRoot.hidden = false;
    const left = Math.min(pointer.clientX - rect.left + 14, rect.width - 250);
    const top = Math.min(pointer.clientY - rect.top + 14, rect.height - 110);
    this.tooltipRoot.style.transform = `translate(${Math.max(8, left)}px, ${Math.max(8, top)}px)`;
  }

  dispose() {
    this.resetHighlights();
    for (const [mesh, edge] of this.edgeCache) {
      mesh.remove(edge); edge.geometry.dispose(); edge.material.dispose();
    }
    this.edgeCache.clear();
    this.domElement.removeEventListener("pointermove", this.boundMove);
    this.domElement.removeEventListener("pointerleave", this.boundLeave);
    this.domElement.removeEventListener("click", this.boundClick);
    this.domElement.removeEventListener("pointerdown", this.boundDown);
  }
}
