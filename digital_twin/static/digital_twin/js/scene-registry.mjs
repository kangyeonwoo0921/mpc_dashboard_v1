import * as THREE from "../vendor/three/three.module.js";

import {
  FOCUS_NODE_NAMES,
  INTERACTABLE_ASSET_TYPES,
  LAYER_NODE_NAMES,
  SPAN_EMPHASIS_ASSET_TYPES,
  SPAN_IDS,
  SPAN_PICK_ASSET_TYPES,
} from "./viewer-config.mjs";
import { normalizeSpanId } from "./selection-runtime.mjs";

function spanIdFromObject(object) {
  let current = object;
  while (current) {
    const explicit = normalizeSpanId(current.userData?.span_index);
    if (explicit) return explicit;
    const match = String(current.name ?? "").match(/(?:^|_)S(0[1-4])(?:_|$)/i);
    if (match) return `S${match[1]}`;
    current = current.parent;
  }
  return null;
}

function nearestAssetOwner(object) {
  let current = object;
  while (current) {
    const type = current.userData?.asset_type;
    if (type === "sensor_anchor") {
      return current.children.find((child) => child.userData?.asset_type === "sensor") ?? current;
    }
    if (INTERACTABLE_ASSET_TYPES.has(type)) return current;
    current = current.parent;
  }
  return null;
}

function semanticAssetType(owner) {
  const type = owner.userData?.asset_type ?? "asset";
  if (type === "sensor_anchor") return "sensor";
  if (type === "crop_bed") return "crop_zone";
  return type;
}

function prepareMaterial(object, material) {
  if (!material) return;
  if (material.opacity < 1) {
    material.transparent = true;
    material.depthWrite = false;
  }
  if (object.userData?.asset_type === "roof_vent") {
    material.opacity = Math.max(material.opacity, 0.34);
    material.transparent = true;
    material.depthWrite = false;
    material.color?.lerp(new THREE.Color(0xe8eeea), 0.2);
  } else if (object.userData?.asset_type === "vent_frame") {
    material.color?.lerp(new THREE.Color(0xc8d2d4), 0.18);
    material.roughness = Math.min(0.52, material.roughness ?? 0.52);
  }
}

function meshWorldBounds(mesh) {
  const geometry = mesh.geometry;
  if (!geometry) return new THREE.Box3();
  if (!geometry.boundingBox) geometry.computeBoundingBox();
  return geometry.boundingBox?.clone().applyMatrix4(mesh.matrixWorld) ?? new THREE.Box3();
}

function groupFlags(object) {
  const flags = new Set();
  let current = object;
  while (current) {
    const name = current.name ?? "";
    if (name === "GH_STRUCTURE") flags.add("structure");
    if (name === "GH_CROPS" || name === "GH_BEDS") flags.add("crops");
    if (name === "GH_ROOF_COVER") flags.add("cover");
    if (name === "GH_FERTIGATION") flags.add("equipment");
    if (name === "GH_FERTIGATION_UNIT") flags.add("equipmentFocus");
    if (name === "GH_SENSORS") flags.add("sensors");
    if (name === "GH_VENTS" || name === "GH_SCREENS") flags.add("controls");
    current = current.parent;
  }
  if (object.userData?.asset_type === "side_curtain" || nearestAssetOwner(object)?.userData?.asset_type === "side_curtain") {
    flags.add("controls");
  }
  return flags;
}

function uniqueExisting(byName, names) {
  return [...new Set(names.map((name) => byName.get(name)).filter(Boolean))];
}

function emptySpanRegistry() {
  return Object.fromEntries(SPAN_IDS.map((id, index) => [id, {
    id,
    index: index + 1,
    objects: [],
    meshes: [],
    emphasisMeshes: [],
    pickTargets: [],
    assets: [],
    bounds: new THREE.Box3(),
  }]));
}

export function buildSceneRegistry(model) {
  model.updateMatrixWorld(true);
  const byName = new Map();
  const meshes = [];
  const assetTargets = [];
  const spanTargets = [];
  const interactionOwners = new WeakMap();
  const assetRecordByMesh = new WeakMap();
  const spanRecordByMesh = new WeakMap();
  const spanByObject = new WeakMap();
  const styleProfileByMesh = new WeakMap();
  const assetTypeCounts = new Map();
  const assetRegistry = new Map();
  const spanRegistry = emptySpanRegistry();
  const overlayMeshes = { structure: [], crops: [], cover: [], equipment: [], sensors: [], controls: [] };
  const focusBounds = {
    interior: new THREE.Box3(),
    equipment: new THREE.Box3(),
    controls: new THREE.Box3(),
  };
  const modelBounds = new THREE.Box3();
  const preparedMaterials = new Set();
  let nodeCount = 0;

  model.traverse((object) => {
    nodeCount += 1;
    if (object.name) byName.set(object.name, object);
    const assetType = object.userData?.asset_type;
    if (assetType) assetTypeCounts.set(assetType, (assetTypeCounts.get(assetType) ?? 0) + 1);

    const spanId = spanIdFromObject(object);
    if (spanId && spanRegistry[spanId]) {
      spanRegistry[spanId].objects.push(object);
      spanByObject.set(object, spanId);
    }
    if (!object.isMesh) return;

    meshes.push(object);
    object.castShadow = false;
    object.receiveShadow = true;
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.forEach((material) => {
      if (preparedMaterials.has(material)) return;
      preparedMaterials.add(material);
      prepareMaterial(object, material);
    });
    const bounds = meshWorldBounds(object);
    if (!bounds.isEmpty()) modelBounds.union(bounds);

    const flags = groupFlags(object);
    styleProfileByMesh.set(object, flags);
    for (const group of Object.keys(overlayMeshes)) {
      if (flags.has(group)) overlayMeshes[group].push(object);
    }
    if ((flags.has("crops")) && !bounds.isEmpty()) focusBounds.interior.union(bounds);
    if (flags.has("equipmentFocus") && !bounds.isEmpty()) focusBounds.equipment.union(bounds);
    if ((flags.has("controls") || flags.has("sensors")) && !bounds.isEmpty()) focusBounds.controls.union(bounds);

    if (spanId && spanRegistry[spanId]) {
      const span = spanRegistry[spanId];
      span.meshes.push(object);
      if (!bounds.isEmpty()) span.bounds.union(bounds);
      if (SPAN_EMPHASIS_ASSET_TYPES.has(assetType)) span.emphasisMeshes.push(object);
      if (SPAN_PICK_ASSET_TYPES.has(assetType)) {
        const record = { kind: "span", spanId, owner: object, mesh: object };
        span.pickTargets.push(object);
        spanTargets.push(object);
        spanRecordByMesh.set(object, record);
      }
    }

    const owner = nearestAssetOwner(object);
    if (!owner) return;
    const id = owner.name || owner.uuid;
    let entry = assetRegistry.get(id);
    if (!entry) {
      entry = {
        id,
        name: owner.name || id,
        type: semanticAssetType(owner),
        sourceAssetType: owner.userData?.asset_type ?? "asset",
        owner,
        spanId: spanIdFromObject(owner) ?? spanId,
        meshes: [],
        bounds: new THREE.Box3(),
      };
      assetRegistry.set(id, entry);
      if (entry.spanId) spanRegistry[entry.spanId]?.assets.push(entry);
    }
    entry.meshes.push(object);
    if (!bounds.isEmpty()) entry.bounds.union(bounds);
    const record = { kind: "asset", spanId: entry.spanId, owner, entry, mesh: object };
    assetTargets.push(object);
    assetRecordByMesh.set(object, record);
    interactionOwners.set(object, owner);
  });

  if (modelBounds.isEmpty()) throw new Error("The GLB has no renderable bounds");
  for (const span of Object.values(spanRegistry)) span.available = !span.bounds.isEmpty();

  const layers = Object.fromEntries(
    Object.entries(LAYER_NODE_NAMES).map(([name, nodeNames]) => [name, uniqueExisting(byName, nodeNames)]),
  );
  const focusNodes = Object.fromEntries(
    Object.entries(FOCUS_NODE_NAMES).map(([name, nodeNames]) => [name, uniqueExisting(byName, nodeNames)]),
  );
  const controlRegistry = { roofVents: [], shadeScreens: [], diffuseScreens: [], sideCurtains: [] };
  for (const object of byName.values()) {
    const name = object.name ?? "";
    const metadata = object.userData ?? {};
    if (name.endsWith("_PIVOT") && (metadata.asset_type === "vent_pivot" || /^GH_VENT_S\d+_\d{2}_PIVOT$/.test(name))) {
      controlRegistry.roofVents.push(object);
    } else if (name.endsWith("_PIVOT") && metadata.asset_type === "screen_pivot" && (metadata.screen_type === "shade_screen" || name.startsWith("GH_SHADE_SCREEN_"))) {
      controlRegistry.shadeScreens.push(object);
    } else if (name.endsWith("_PIVOT") && metadata.asset_type === "screen_pivot" && (metadata.screen_type === "diffuse_screen" || name.startsWith("GH_DIFFUSE_SCREEN_"))) {
      controlRegistry.diffuseScreens.push(object);
    } else if (metadata.asset_type === "side_curtain" || name === "GH_SIDE_CURTAIN_LEFT" || name === "GH_SIDE_CURTAIN_RIGHT") {
      controlRegistry.sideCurtains.push(object);
    }
  }

  return {
    model,
    modelBounds,
    nodeCount,
    byName,
    meshes,
    layers,
    focusNodes,
    focusBounds,
    overlayMeshes,
    styleProfileByMesh,
    spanRegistry,
    spanByObject,
    assetRegistry,
    assetTargets,
    spanTargets,
    interactableTargets: assetTargets,
    interactionOwners,
    assetRecordByMesh,
    spanRecordByMesh,
    assetTypeCounts,
    controlRegistry,
    getByName(name) {
      return byName.get(name) ?? null;
    },
    getAsset(id) {
      return assetRegistry.get(id) ?? null;
    },
    getSelectionBounds(selection) {
      if (selection?.level === "asset") {
        const entry = assetRegistry.get(selection.assetId);
        if (!entry) return modelBounds.clone();
        const bounds = new THREE.Box3();
        for (const mesh of entry.meshes) {
          mesh.updateWorldMatrix(true, false);
          bounds.union(meshWorldBounds(mesh));
        }
        return bounds.isEmpty() ? entry.bounds.clone() : bounds;
      }
      if (selection?.level === "span") return spanRegistry[selection.spanId]?.bounds.clone() ?? modelBounds.clone();
      return modelBounds.clone();
    },
    getFocusBounds(name) {
      if (name === "model") return modelBounds.clone();
      const bounds = focusBounds[name];
      return !bounds || bounds.isEmpty() ? modelBounds.clone() : bounds.clone();
    },
  };
}
