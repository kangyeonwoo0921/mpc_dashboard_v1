import { LIVE_CONFIG, OBJECT_MAP } from "./live-config.mjs";

const DEG_TO_RAD = Math.PI / 180;

function clampPercent(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.min(100, Math.max(0, value))
    : null;
}

function findByName(scene, name) {
  if (typeof scene.getObjectByName === "function") return scene.getObjectByName(name);
  let found = null;
  if (typeof scene.traverse === "function") {
    scene.traverse((object) => {
      if (!found && object.name === name) found = object;
    });
  }
  return found;
}

export function buildControllableRegistry(scene) {
  const registry = {
    roofVents: [],
    shadeScreens: [],
    diffuseScreens: [],
    sideCurtains: [],
  };
  if (!scene || typeof scene.traverse !== "function") return registry;
  scene.traverse((object) => {
    const name = object.name ?? "";
    const metadata = object.userData ?? {};
    if (
      name.endsWith("_PIVOT")
      && (metadata.asset_type === "vent_pivot" || /^GH_VENT_S\d+_\d{2}_PIVOT$/.test(name))
    ) {
      registry.roofVents.push(object);
    } else if (
      name.endsWith("_PIVOT")
      && metadata.asset_type === "screen_pivot"
      && (metadata.screen_type === "shade_screen" || name.startsWith("GH_SHADE_SCREEN_"))
    ) {
      registry.shadeScreens.push(object);
    } else if (
      name.endsWith("_PIVOT")
      && metadata.asset_type === "screen_pivot"
      && (metadata.screen_type === "diffuse_screen" || name.startsWith("GH_DIFFUSE_SCREEN_"))
    ) {
      registry.diffuseScreens.push(object);
    } else if (
      metadata.asset_type === "side_curtain"
      || name === "GH_SIDE_CURTAIN_LEFT"
      || name === "GH_SIDE_CURTAIN_RIGHT"
    ) {
      registry.sideCurtains.push(object);
    }
  });
  return registry;
}

export class ActuatorRuntime {
  constructor({ objectMap = OBJECT_MAP, config = LIVE_CONFIG, warn = console.warn } = {}) {
    this.objectMap = objectMap;
    this.config = config;
    this.warn = warn;
    this.warnedNames = new Set();
    this.channels = new Map();
    this.registry = { roofVents: [], shadeScreens: [], diffuseScreens: [], sideCurtains: [] };
  }

  bindScene(scene, { registry = null, byName = null } = {}) {
    this.channels.clear();
    this.registry = registry ?? buildControllableRegistry(scene);
    for (const [channelName, mapping] of Object.entries(this.objectMap)) {
      const objects = mapping.names.map((name) => {
        const object = byName?.get(name) ?? findByName(scene, name);
        if (!object && !this.warnedNames.has(name)) {
          this.warnedNames.add(name);
          this.warn(`[digital-twin] GLB object not found: ${name}`);
        }
        return object;
      }).filter(Boolean);

      const initial = this.#inferCurrent(mapping, objects[0]);
      this.channels.set(channelName, {
        mapping,
        objects,
        current: initial,
        target: initial,
        bases: objects.map((object) => this.#captureBase(mapping, object)),
      });
    }
    return this.mappingStatus();
  }

  mappingStatus() {
    return Object.fromEntries(
      [...this.channels].map(([name, channel]) => [name, {
        found: channel.objects.length,
        expected: channel.mapping.names.length,
        provisional: Boolean(channel.mapping.provisional),
      }]),
    );
  }

  setTargets(actuators) {
    if (!actuators || typeof actuators !== "object") return;
    for (const channel of this.channels.values()) {
      const value = clampPercent(actuators[channel.mapping.dtoKey]);
      if (value !== null) channel.target = value;
    }
  }

  update(deltaSeconds) {
    const delta = Number.isFinite(deltaSeconds) ? Math.max(0, deltaSeconds) : 0;
    const factor = 1 - Math.exp(-delta / this.config.smoothingTimeSeconds);
    for (const channel of this.channels.values()) {
      channel.current += (channel.target - channel.current) * factor;
      channel.objects.forEach((object, index) => {
        this.#apply(channel.mapping, object, channel.bases[index], channel.current);
      });
    }
  }

  #inferCurrent(mapping, object) {
    const sourceOpening = object?.userData?.opening_percent;
    if (typeof sourceOpening !== "number") return 0;
    return sourceOpening;
  }

  #captureBase(mapping, object) {
    if (mapping.kind === "roofVent") {
      const sourceOpening = typeof object.userData?.opening_percent === "number"
        ? object.userData.opening_percent
        : 0;
      const maxAngle = typeof object.userData?.max_open_angle_deg === "number"
        ? object.userData.max_open_angle_deg
        : this.config.roofVentMaxAngleDeg;
      const metadataDirection = object.userData?.side === "negative_y"
        ? -1
        : object.userData?.side === "positive_y"
          ? 1
          : mapping.direction;
      const direction = typeof metadataDirection === "number" ? metadataDirection : 1;
      return {
        closedRotationX: object.rotation.x - direction * sourceOpening / 100 * maxAngle * DEG_TO_RAD,
        maxAngleDeg: maxAngle,
        direction,
      };
    }
    // Blender local Y (across-span travel) exports as glTF local Z.
    return { fullScale: 1, scaleAxis: object.userData?.retract_axis === "y" ? "z" : "x" };
  }

  #apply(mapping, object, base, percent) {
    if (mapping.kind === "roofVent") {
      object.rotation.x = base.closedRotationX
        + base.direction * percent / 100 * base.maxAngleDeg * DEG_TO_RAD;
      return;
    }
    if (mapping.kind === "screen") {
      object.scale[base.scaleAxis] = Math.max(0.000001, (1 - percent / 100) * base.fullScale);
    }
  }
}
