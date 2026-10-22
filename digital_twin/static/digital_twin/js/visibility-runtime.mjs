import * as THREE from "../vendor/three/three.module.js";

import { VISIBILITY_PRESETS } from "./viewer-config.mjs";

function uniqueMeshes(registry) {
  const meshes = new Set();
  Object.values(registry.spanRegistry ?? {}).forEach((span) => span.emphasisMeshes.forEach((mesh) => meshes.add(mesh)));
  Object.values(registry.overlayMeshes ?? {}).forEach((group) => group.forEach((mesh) => meshes.add(mesh)));
  return [...meshes];
}

export class VisibilityRuntime {
  constructor(registry) {
    this.registry = registry;
    this.initialVisibility = new Map();
    this.layerState = {};
    this.overlayState = { controlState: false, labels: true };
    this.selectedSpanId = null;
    this.stylableMeshes = uniqueMeshes(registry);
    this.originalMaterials = new Map(this.stylableMeshes.map((mesh) => [mesh, mesh.material]));
    this.materialVariants = new WeakMap();
    this.arrayVariants = new Map();
    for (const [layer, nodes] of Object.entries(registry.layers)) {
      nodes.forEach((node) => this.initialVisibility.set(node, node.visible));
      this.layerState[layer] = nodes.some((node) => node.visible);
    }
    this.currentPreset = "exterior";
  }

  availableLayers() {
    return Object.fromEntries(
      Object.entries(this.registry.layers).map(([name, nodes]) => [name, nodes.length > 0]),
    );
  }

  setLayer(name, visible) {
    const nodes = this.registry.layers[name] ?? [];
    nodes.forEach((node) => { node.visible = Boolean(visible); });
    this.layerState[name] = Boolean(visible);
    return nodes.length > 0;
  }

  setOverlay(name, enabled) {
    if (!(name in this.overlayState)) return false;
    this.overlayState[name] = Boolean(enabled);
    if (name === "controlState") this.refreshMaterialStyles();
    return true;
  }

  setSpanEmphasis(spanId) {
    this.selectedSpanId = spanId ?? null;
    this.refreshMaterialStyles();
  }

  applyPreset(name) {
    const preset = VISIBILITY_PRESETS[name];
    if (!preset) throw new RangeError(`Unknown visibility preset: ${name}`);
    this.currentPreset = name;
    for (const [layer, visible] of Object.entries(preset)) this.setLayer(layer, visible);
    return { ...this.layerState };
  }

  refreshMaterialStyles() {
    for (const mesh of this.stylableMeshes) {
      const original = this.originalMaterials.get(mesh);
      const spanId = this.registry.spanByObject?.get(mesh);
      const groups = this.registry.styleProfileByMesh?.get(mesh) ?? new Set();
      const dimSpan = Boolean(this.selectedSpanId && spanId && spanId !== this.selectedSpanId);
      const controlMuted = this.overlayState.controlState && (groups.has("structure") || groups.has("crops"));
      const coverMuted = this.overlayState.controlState && groups.has("cover");
      const controlTarget = this.overlayState.controlState && (groups.has("controls") || groups.has("sensors"));
      const key = [dimSpan ? "span" : "", controlMuted ? "mute" : "", coverMuted ? "cover" : "", controlTarget ? "target" : ""].filter(Boolean).join("+");
      mesh.material = key ? this.#variant(original, key, { dimSpan, controlMuted, coverMuted, controlTarget }) : original;
    }
  }

  restoreDefault() {
    for (const [node, visible] of this.initialVisibility) node.visible = visible;
    for (const [layer, nodes] of Object.entries(this.registry.layers)) {
      this.layerState[layer] = nodes.some((node) => node.visible);
    }
    this.currentPreset = "exterior";
    this.selectedSpanId = null;
    this.overlayState.controlState = false;
    this.refreshMaterialStyles();
    return { ...this.layerState };
  }

  #variant(source, key, flags) {
    if (Array.isArray(source)) {
      let variants = this.arrayVariants.get(source);
      if (!variants) {
        variants = new Map();
        this.arrayVariants.set(source, variants);
      }
      if (!variants.has(key)) variants.set(key, source.map((material) => this.#variant(material, key, flags)));
      return variants.get(key);
    }
    if (!source) return source;
    let variants = this.materialVariants.get(source);
    if (!variants) {
      variants = new Map();
      this.materialVariants.set(source, variants);
    }
    if (variants.has(key)) return variants.get(key);
    const material = source.clone();
    if (material.color && (flags.dimSpan || flags.controlMuted)) {
      material.color.multiplyScalar(flags.dimSpan ? 0.52 : 0.62);
      material.color.offsetHSL(0, -0.18, -0.03);
    }
    if (flags.coverMuted && typeof material.opacity === "number") {
      material.opacity *= 0.58;
      material.transparent = true;
      material.depthWrite = false;
    }
    if (flags.controlTarget) {
      material.color?.lerp(new THREE.Color(0xa9c3e0), 0.12);
      if (material.emissive) {
        material.emissive.set(0x17304f);
        material.emissiveIntensity = 0.16;
      }
    }
    variants.set(key, material);
    return material;
  }
}
