import * as THREE from "../vendor/three/three.module.js";

import { CAMERA_PRESETS, CAMERA_TRANSITION_MS } from "./viewer-config.mjs";

const WORLD_UP = new THREE.Vector3(0, 1, 0);

function boxCorners(bounds) {
  const { min, max } = bounds;
  return [
    new THREE.Vector3(min.x, min.y, min.z),
    new THREE.Vector3(min.x, min.y, max.z),
    new THREE.Vector3(min.x, max.y, min.z),
    new THREE.Vector3(min.x, max.y, max.z),
    new THREE.Vector3(max.x, min.y, min.z),
    new THREE.Vector3(max.x, min.y, max.z),
    new THREE.Vector3(max.x, max.y, min.z),
    new THREE.Vector3(max.x, max.y, max.z),
  ];
}

export function calculateFitPose(bounds, camera, directionValues, margin = 1.14) {
  const target = bounds.getCenter(new THREE.Vector3());
  const direction = new THREE.Vector3(...directionValues).normalize();
  let right = new THREE.Vector3().crossVectors(WORLD_UP, direction);
  if (right.lengthSq() < 1e-6) right = new THREE.Vector3(1, 0, 0);
  right.normalize();
  const viewUp = new THREE.Vector3().crossVectors(direction, right).normalize();
  let halfWidth = 0;
  let halfHeight = 0;
  let halfDepth = 0;
  for (const corner of boxCorners(bounds)) {
    const delta = corner.sub(target);
    halfWidth = Math.max(halfWidth, Math.abs(delta.dot(right)));
    halfHeight = Math.max(halfHeight, Math.abs(delta.dot(viewUp)));
    halfDepth = Math.max(halfDepth, Math.abs(delta.dot(direction)));
  }
  const verticalFov = THREE.MathUtils.degToRad(camera.fov);
  const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * Math.max(camera.aspect, 0.01));
  const fitDistance = Math.max(
    halfHeight / Math.tan(verticalFov / 2),
    halfWidth / Math.tan(horizontalFov / 2),
  );
  const distance = halfDepth + fitDistance * margin;
  return {
    position: target.clone().addScaledVector(direction, distance),
    target,
    distance,
  };
}

export function calculateInteriorPose(bounds) {
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const eyeHeight = bounds.min.y + Math.max(1.45, Math.min(1.9, size.y * 0.36));
  return {
    position: new THREE.Vector3(
      center.x - size.x * 0.3,
      eyeHeight,
      center.z + size.z * 0.06,
    ),
    target: new THREE.Vector3(
      center.x + size.x * 0.24,
      eyeHeight - 0.12,
      center.z,
    ),
    distance: size.x * 0.54,
  };
}

function easeInOutCubic(value) {
  return value < 0.5
    ? 4 * value * value * value
    : 1 - Math.pow(-2 * value + 2, 3) / 2;
}

export class CameraRuntime {
  constructor({ camera, controls, registry, onPresetChange = () => {}, transitionMs = CAMERA_TRANSITION_MS }) {
    this.camera = camera;
    this.controls = controls;
    this.registry = registry;
    this.onPresetChange = onPresetChange;
    this.transitionMs = transitionMs;
    this.currentPreset = null;
    this.currentBounds = null;
    this.transition = null;
  }

  poseFor(name, boundsOverride = null) {
    const preset = CAMERA_PRESETS[name];
    if (!preset) throw new RangeError(`Unknown camera preset: ${name}`);
    const bounds = boundsOverride?.clone() ?? this.registry.getFocusBounds(preset.focus);
    if (preset.mode === "interior") return calculateInteriorPose(bounds);
    return calculateFitPose(bounds, this.camera, preset.direction, preset.margin);
  }

  goTo(name, { bounds = null, immediate = false, now = globalThis.performance?.now() ?? Date.now() } = {}) {
    const pose = this.poseFor(name, bounds);
    this.currentPreset = name;
    this.currentBounds = bounds?.clone() ?? null;
    this.onPresetChange(name, CAMERA_PRESETS[name]);
    this.#transitionTo(pose, { immediate, now });
  }

  fitSelected(bounds, {
    direction = null,
    margin = 1.32,
    immediate = false,
    now = globalThis.performance?.now() ?? Date.now(),
  } = {}) {
    if (!bounds || bounds.isEmpty()) return false;
    const target = bounds.getCenter(new THREE.Vector3());
    const fallbackDirection = this.camera.position.clone().sub(this.controls.target);
    const fitDirection = direction ?? (fallbackDirection.lengthSq() > 1e-6 ? fallbackDirection.normalize().toArray() : CAMERA_PRESETS.overview.direction);
    const pose = calculateFitPose(bounds, this.camera, fitDirection, margin);
    this.currentBounds = bounds.clone();
    this.#transitionTo(pose, { immediate, now });
    return true;
  }

  // "선택 확대": frame the selection tightly, and always end closer than the current view.
  zoomInOn(bounds, {
    margin = 1.05,
    zoomFactor = 0.65,
    now = globalThis.performance?.now() ?? Date.now(),
  } = {}) {
    if (!bounds || bounds.isEmpty()) return false;
    const offset = this.camera.position.clone().sub(this.controls.target);
    const currentDistance = offset.length();
    const direction = currentDistance > 1e-6 ? offset.normalize() : new THREE.Vector3(...CAMERA_PRESETS.overview.direction).normalize();
    const pose = calculateFitPose(bounds, this.camera, direction.toArray(), margin);
    if (pose.distance >= currentDistance * 0.95) {
      const distance = Math.max(this.controls.minDistance, currentDistance * zoomFactor);
      pose.distance = distance;
      pose.position = pose.target.clone().addScaledVector(direction, distance);
    }
    this.currentBounds = bounds.clone();
    this.#transitionTo(pose, { immediate: false, now });
    return true;
  }

  #transitionTo(pose, { immediate, now }) {
    this.camera.near = Math.max(0.03, pose.distance / 2500);
    this.camera.far = Math.max(500, pose.distance * 12);
    this.camera.updateProjectionMatrix();
    this.controls.minDistance = Math.max(0.35, this.registry.modelBounds.getSize(new THREE.Vector3()).length() * 0.008);
    this.controls.maxDistance = Math.max(250, pose.distance * 5);
    this.controls.maxPolarAngle = Math.PI * 0.495;

    if (immediate) {
      this.camera.position.copy(pose.position);
      this.controls.target.copy(pose.target);
      this.controls.update();
      this.transition = null;
      return;
    }
    this.transition = {
      startedAt: now,
      fromPosition: this.camera.position.clone(),
      fromTarget: this.controls.target.clone(),
      toPosition: pose.position,
      toTarget: pose.target,
    };
  }

  update(now = globalThis.performance?.now() ?? Date.now()) {
    if (!this.transition) return false;
    const rawProgress = Math.min(1, Math.max(0, (now - this.transition.startedAt) / this.transitionMs));
    const progress = easeInOutCubic(rawProgress);
    this.camera.position.lerpVectors(this.transition.fromPosition, this.transition.toPosition, progress);
    this.controls.target.lerpVectors(this.transition.fromTarget, this.transition.toTarget, progress);
    if (rawProgress >= 1) this.transition = null;
    return true;
  }

  refitCurrent({ immediate = true } = {}) {
    if (this.currentPreset) this.goTo(this.currentPreset, { bounds: this.currentBounds, immediate });
  }
}
