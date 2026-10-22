// Surroundings for the 3D view (trial, display only): a wide ground that fades into a hazy horizon, a sky
// gradient and, from the sun altitude, the time of day (day -> golden hour -> dusk -> night with stars).
// Nothing here is site data. Roll back: remove the addEnvironment(...) call in viewer.mjs (or open the
// viewer with ?env=0).

import * as THREE from "../vendor/three/three.module.js";

// Looks by sun altitude (deg), blended linearly between neighbours. "day" is the original trial look.
export const SKY_KEYFRAMES = Object.freeze([
  { altitude: -12, zenith: 0x040914, horizon: 0x16223a, ground: 0x161b16, pad: 0x2c2b27, light: 0.42, exposure: 0.5, stars: 1 },
  { altitude: -4, zenith: 0x0c1430, horizon: 0x5b4a68, ground: 0x23261f, pad: 0x403d37, light: 0.6, exposure: 0.75, stars: 0.35 },
  { altitude: 3, zenith: 0x1a2a4c, horizon: 0xc8875a, ground: 0x4a4434, pad: 0x786a56, light: 1.0, exposure: 1.02, stars: 0 },
  { altitude: 12, zenith: 0x0d1d36, horizon: 0x4a6380, ground: 0x3d4536, pad: 0x6a675c, light: 1.0, exposure: 1.08, stars: 0 },
]);

export const ENVIRONMENT_CONFIG = Object.freeze({
  groundRadiusM: 1400,
  fogDensity: 0.0024,        // ~30 % haze at 250 m, ~90 % at 650 m; the greenhouse (< 100 m) stays clear
  starCount: 700,
});

export function environmentEnabled(search = typeof location === "object" ? location.search : "") {
  return new URLSearchParams(search).get("env") !== "0";
}

/** The look at a sun altitude: colours as THREE.Color, light = hemisphere-light factor, stars = opacity. */
export function lookAt(altitudeDeg, keyframes = SKY_KEYFRAMES) {
  const a = Number.isFinite(altitudeDeg) ? altitudeDeg : keyframes[keyframes.length - 1].altitude;
  let i = keyframes.findIndex((k) => k.altitude >= a);
  if (i === -1) i = keyframes.length - 1;
  const hi = keyframes[Math.max(0, i)];
  const lo = keyframes[Math.max(0, i - 1)];
  const t = hi === lo ? 1 : Math.min(1, Math.max(0, (a - lo.altitude) / (hi.altitude - lo.altitude)));
  const color = (key) => new THREE.Color(lo[key]).lerp(new THREE.Color(hi[key]), t);
  const number = (key) => lo[key] + (hi[key] - lo[key]) * t;
  return { zenith: color("zenith"), horizon: color("horizon"), ground: color("ground"), pad: color("pad"),
    light: number("light"), exposure: number("exposure"), stars: number("stars") };
}

function skyDome() {
  const material = new THREE.ShaderMaterial({
    uniforms: { zenith: { value: new THREE.Color() }, horizon: { value: new THREE.Color() } },
    vertexShader: "varying vec3 vDir; void main() { vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: `uniform vec3 zenith; uniform vec3 horizon; varying vec3 vDir;
      void main() { float t = pow(clamp(vDir.y, 0.0, 1.0), 0.55); gl_FragColor = vec4(mix(horizon, zenith, t), 1.0);
      #include <colorspace_fragment>
      }`,
    side: THREE.BackSide, depthWrite: false, fog: false,
  });
  // Drawn first without depth, so it only needs to stay inside the camera's far plane (>= 500 m).
  const dome = new THREE.Mesh(new THREE.SphereGeometry(400, 32, 16), material);
  dome.name = "VIEWER_SKY";
  dome.renderOrder = -1;
  dome.frustumCulled = false;
  return dome;
}

function starField(count) {
  // Deterministic scatter over the upper sky (golden-angle spiral), denser towards the zenith.
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    const y = 0.08 + 0.92 * Math.sqrt((i + 0.5) / count);
    const r = Math.sqrt(1 - y * y);
    const phi = i * 2.399963;
    positions.set([Math.cos(phi) * r * 380, y * 380, Math.sin(phi) * r * 380], i * 3);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const stars = new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xdfe8ff, size: 2.2, sizeAttenuation: false,
    transparent: true, opacity: 0, depthWrite: false, fog: false }));
  stars.name = "VIEWER_STARS";
  stars.renderOrder = -1;
  stars.frustumCulled = false;
  return stars;
}

/**
 * Adds sky, stars, ground and haze around the model. Returns { setSunAltitude(deg), remove() }; remove()
 * restores the scene, the ground-plane colour, the hemisphere light and the exposure exactly.
 */
export function addEnvironment({ scene, model, hemisphere = null, renderer = null, config = ENVIRONMENT_CONFIG }) {
  const previous = { background: scene.background, fog: scene.fog, light: hemisphere?.intensity,
    exposure: renderer?.toneMappingExposure };
  const background = new THREE.Color();
  scene.background = background;
  scene.fog = new THREE.FogExp2(0x000000, config.fogDensity);

  const sky = skyDome();
  const stars = starField(config.starCount);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(config.groundRadiusM, 96),
    new THREE.MeshStandardMaterial({ roughness: 1, metalness: 0 }));
  ground.name = "VIEWER_GROUND";
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.03;           // just under the GLB ground plane
  ground.receiveShadow = true;
  // sky and stars follow the camera so the horizon never shows an edge
  const follow = (object) => { object.onBeforeRender = (_r, _s, viewCamera) => object.position.copy(viewCamera.position); };
  follow(sky);
  follow(stars);
  scene.add(sky, stars, ground);

  const pad = model?.getObjectByName("GH_GROUND_PLANE");
  const padColor = pad?.material?.color?.getHex();
  let shown = null;

  const setSunAltitude = (altitudeDeg) => {
    const key = Number.isFinite(altitudeDeg) ? Math.round(altitudeDeg * 4) / 4 : null;
    if (key === shown) return;
    shown = key;
    const look = lookAt(key);
    sky.material.uniforms.zenith.value.copy(look.zenith);
    sky.material.uniforms.horizon.value.copy(look.horizon);
    background.copy(look.horizon);
    scene.fog.color.copy(look.horizon);
    ground.material.color.copy(look.ground);
    if (pad?.material?.color) pad.material.color.copy(look.pad);
    stars.material.opacity = look.stars;
    stars.visible = look.stars > 0.01;
    if (hemisphere && previous.light !== undefined) hemisphere.intensity = previous.light * look.light;
    if (renderer && previous.exposure !== undefined) renderer.toneMappingExposure = look.exposure;
  };
  setSunAltitude(null);

  const remove = () => {
    scene.remove(sky, stars, ground);
    scene.background = previous.background;
    scene.fog = previous.fog;
    if (pad?.material?.color && padColor !== undefined) pad.material.color.setHex(padColor);
    if (hemisphere && previous.light !== undefined) hemisphere.intensity = previous.light;
    if (renderer && previous.exposure !== undefined) renderer.toneMappingExposure = previous.exposure;
  };
  return { setSunAltitude, remove };
}
