// Wall curtains the GLB does not contain, added in the viewer only (display; physics reads the GLB as before).
// Drawing (MS8.0 x 97.5 m, pp. 27-29): the side curtain hangs from the eave and is wound up by drums and
// rollers. The GLB already has the long-side outer curtains (GH_SIDE_CURTAIN_LEFT/RIGHT), shown as 측창.
// Added here, all provisional (positions follow the GLB, field L/R/front/rear convention unconfirmed):
//   - 측창 정면/후면: outer roll-up curtain on the windbreak part of each end wall (no drawing detail).
//   - 수직커튼 4면: inner curtain 0.45 m inside each windbreak wall, same eave-to-lower-wall band.
// Every curtain follows the GLB side-curtain contract: root at the eave, panel hanging down by full_height,
// opening % = share wound up (0 = closed, 100 = fully up).

import * as THREE from "../vendor/three/three.module.js";

const OUTSIDE_M = 0.12;   // same clearance as the GLB side curtains (config side_curtains.frame_clearance)
const INSIDE_M = 0.45;
const WALL_LABELS = { LEFT: "좌측", RIGHT: "우측", FRONT: "정면", REAR: "후면" };

/** Panel scale, bottom bar and roller pose of one wall curtain at an opening %. */
export function applyWallCurtainOpening(root, percent) {
  const covered = Math.max(0.000001, 1 - Math.min(100, Math.max(0, percent)) / 100);
  const height = root.userData.full_height;
  for (const child of root.children) {
    const type = child.userData?.asset_type;
    if (type === "curtain_panel") child.scale.y = covered;
    else if (type === "curtain_bottom_bar") child.position.y = -height * covered;
    else if (type === "curtain_roller" || type === "curtain_drum") child.rotation.x = (1 - covered) * Math.PI * 2;
  }
}

/** Largest vertical plane (x = const) of the end-wall windbreak below the eave: { x, zMin, zMax } in world space. */
export function windbreakFace(shell, eave) {
  const planes = new Map();
  const point = new THREE.Vector3();
  shell.updateWorldMatrix(true, true);
  shell.traverse((mesh) => {
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    if (!mesh.isMesh || !materials.some((material) => material?.name === "MAT_END_WINDBREAK")) return;
    const position = mesh.geometry.attributes.position;
    const index = mesh.geometry.index;
    const count = index ? index.count : position.count;
    for (let i = 0; i < count; i += 3) {
      const corners = [0, 1, 2].map((k) => point.fromBufferAttribute(position, index ? index.getX(i + k) : i + k)
        .applyMatrix4(mesh.matrixWorld).clone());
      if (corners.some((c) => c.y > eave + 1e-3) || corners.some((c) => Math.abs(c.x - corners[0].x) > 1e-3)) continue;
      // Gutter-level slivers of the roof-arch strips lie flat at eave height; they are not wall.
      if (Math.max(...corners.map((c) => c.y)) - Math.min(...corners.map((c) => c.y)) < 0.05) continue;
      const key = corners[0].x.toFixed(2);
      const plane = planes.get(key) ?? { x: corners[0].x, zMin: Infinity, zMax: -Infinity };
      for (const c of corners) { plane.zMin = Math.min(plane.zMin, c.z); plane.zMax = Math.max(plane.zMax, c.z); }
      planes.set(key, plane);
    }
  });
  return [...planes.values()].sort((a, b) => (b.zMax - b.zMin) - (a.zMax - a.zMin))[0] ?? null;
}

function rollUpCurtain({ name, assetType, wall, center, length, height, alongZ, material, barMaterial }) {
  const root = new THREE.Object3D();
  root.name = name;
  root.position.copy(center);
  if (alongZ) root.rotation.y = Math.PI / 2;
  root.userData = { asset_type: assetType, wall_label: WALL_LABELS[wall], full_height: height, controllable: true,
    control_variable: "opening_percent", source: "viewer_added", position: "approximate", drawing_pages: "27-29" };
  const panelGeometry = new THREE.PlaneGeometry(length, height);
  panelGeometry.translate(0, -height / 2, 0);
  const panel = new THREE.Mesh(panelGeometry, material);
  panel.name = `${name}_PANEL`;
  panel.userData = { asset_type: "curtain_panel" };
  const bar = (suffix, radius, y, type) => {
    const geometry = new THREE.CylinderGeometry(radius, radius, length, 8);
    geometry.rotateZ(Math.PI / 2);
    const mesh = new THREE.Mesh(geometry, barMaterial);
    mesh.name = `${name}_${suffix}`;
    mesh.position.y = y;
    mesh.userData = { asset_type: type };
    return mesh;
  };
  root.add(panel, bar("ROLLER", 0.065, 0.1, "curtain_roller"), bar("BOTTOM_BAR", 0.023, -height, "curtain_bottom_bar"));
  return root;
}

/**
 * Adds the missing wall curtains to the loaded GLB scene (call before building the scene registry) and labels
 * the existing long-side ones. Returns the names that were added.
 */
export function addWallCurtains(model) {
  model.updateWorldMatrix(true, true);
  const left = model.getObjectByName("GH_SIDE_CURTAIN_LEFT");
  const right = model.getObjectByName("GH_SIDE_CURTAIN_RIGHT");
  const leftPanel = model.getObjectByName("GH_SIDE_CURTAIN_LEFT_PANEL");
  if (!left || !right || !leftPanel) return [];
  left.userData.wall_label = WALL_LABELS.LEFT;
  right.userData.wall_label = WALL_LABELS.RIGHT;
  const height = left.userData.full_height ?? 4.2;
  const eave = left.getWorldPosition(new THREE.Vector3()).y;
  const film = leftPanel.material;
  const barMaterial = model.getObjectByName("GH_SIDE_CURTAIN_LEFT_BOTTOM_BAR")?.material ?? film;
  const fabric = new THREE.MeshStandardMaterial({ name: "MAT_VERTICAL_CURTAIN", color: 0xd8ccb0, roughness: 0.9,
    transparent: true, opacity: 0.82, depthWrite: false, side: THREE.DoubleSide });
  const parent = model.getObjectByName("GH_CURTAINS") ?? model;
  const added = [];
  const place = (spec) => {
    const root = rollUpCurtain({ ...spec, height, barMaterial });
    parent.add(root);
    // rollUpCurtain positions are world positions; GH_CURTAINS carries no transform in the GLB, but stay exact.
    parent.updateWorldMatrix(true, false);
    root.position.applyMatrix4(parent.matrixWorld.clone().invert());
    added.push(root.name);
  };

  for (const [wall, side] of [["LEFT", left], ["RIGHT", right]]) {
    const center = side.getWorldPosition(new THREE.Vector3());
    const box = new THREE.Box3().setFromObject(model.getObjectByName(`GH_SIDE_CURTAIN_${wall}_PANEL`));
    center.z -= Math.sign(center.z) * INSIDE_M;
    place({ name: `GH_VERTICAL_CURTAIN_${wall}`, assetType: "vertical_curtain", wall, center,
      length: box.max.x - box.min.x, alongZ: false, material: fabric });
  }
  for (const [wall, shellName, outward] of [["FRONT", "GH_FRONT_WALL_SHELL", -1], ["REAR", "GH_REAR_WALL_SHELL", 1]]) {
    const shell = model.getObjectByName(shellName);
    const face = shell && windbreakFace(shell, eave);
    if (!face) continue;
    const z = (face.zMin + face.zMax) / 2;
    const length = face.zMax - face.zMin;
    place({ name: `GH_SIDE_VENT_${wall}`, assetType: "side_curtain", wall, length, alongZ: true, material: film,
      center: new THREE.Vector3(face.x + outward * OUTSIDE_M, eave, z) });
    place({ name: `GH_VERTICAL_CURTAIN_${wall}`, assetType: "vertical_curtain", wall, length, alongZ: true, material: fabric,
      center: new THREE.Vector3(face.x - outward * INSIDE_M, eave, z) });
  }
  return added;
}
