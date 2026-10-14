import * as THREE from "../vendor/three/three.module.js";

import { displayTitle } from "./interaction-runtime.mjs";

export class LabelRuntime {
  constructor({ root, camera, domElement }) {
    this.root = root;
    this.camera = camera;
    this.domElement = domElement;
    this.anchor = null;
    this.anchorOwner = null;
    this.enabled = true;
    this.projected = new THREE.Vector3();
  }

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    // Selected context stays labelled; the Labels overlay controls hover labels.
  }

  setSelection(selection, { entry = null, bounds = null, context = {} } = {}) {
    if (!bounds || selection.level === "greenhouse") {
      this.anchor = null;
      this.anchorOwner = null;
      this.root.hidden = true;
      return;
    }
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    center.y += Math.max(0.35, size.y * 0.16);
    this.anchor = center;
    this.anchorOwner = entry?.owner ?? null;
    if (this.anchorOwner) {
      this.anchorOwner.updateWorldMatrix(true, false);
      this.anchorOwner.worldToLocal(this.anchor);
    }
    const title = this.root.querySelector("[data-label-title]");
    const value = this.root.querySelector("[data-label-value]");
    if (selection.level === "span") {
      title.textContent = `${Number(selection.spanId.slice(1))}동`;
      value.textContent = "선택한 동";
    } else {
      title.textContent = entry ? displayTitle(entry.owner, entry.type) : selection.assetId;
      value.textContent = typeof context.openingPercent === "number"
        ? `${context.openingPercent.toFixed(1)}%`
        : entry?.type === "sensor"
          ? (entry.owner.userData?.verified_position === true ? "위치 확인됨" : "위치 미확인")
          : "선택한 장치";
    }
    this.root.hidden = false;
  }

  update() {
    if (!this.anchor) return;
    const rect = this.domElement.getBoundingClientRect();
    this.projected.copy(this.anchor);
    if (this.anchorOwner) {
      this.anchorOwner.updateWorldMatrix(true, false);
      this.projected.applyMatrix4(this.anchorOwner.matrixWorld);
    }
    this.projected.project(this.camera);
    const visible = this.projected.z >= -1 && this.projected.z <= 1
      && this.projected.x >= -1.15 && this.projected.x <= 1.15
      && this.projected.y >= -1.15 && this.projected.y <= 1.15;
    this.root.hidden = !visible;
    if (!visible) return;
    const x = (this.projected.x * 0.5 + 0.5) * rect.width;
    const y = (-this.projected.y * 0.5 + 0.5) * rect.height;
    this.root.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`;
  }
}
