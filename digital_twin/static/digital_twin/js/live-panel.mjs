const FIELDS = Object.freeze({
  indoorTemperature: ["environment", "indoor_temperature_c", "°C", 1],
  indoorRh: ["environment", "indoor_rh_pct", "%", 1],
  vpd: ["environment", "vpd_kpa", "kPa", 3],
  co2: ["environment", "co2_ppm", "ppm", 0],
  dewPoint: ["environment", "dew_point_c", "°C", 1],
  setpointTemperature: ["environment", "setpoint_temperature_c", "°C", 1],
  outdoorTemperature: ["environment", "outdoor_temperature_c", "°C", 1],
  solar: ["environment", "solar_w_m2", "W/m²", 0],
  windSpeed: ["environment", "wind_speed_m_s", "m/s", 1],
  windDirection: ["environment", "wind_direction_text", "", null],
  roofVentLeft: ["actuators", "roof_vent_left_pct", "%", 1],
  roofVentRight: ["actuators", "roof_vent_right_pct", "%", 1],
  shadeScreen1: ["actuators", "shade_screen_1_pct", "%", 1],
  shadeScreen2: ["actuators", "shade_screen_2_pct", "%", 1],
});

export function formatValue(value, unit, digits) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return `${value.toFixed(digits ?? 0)} ${unit}`.trim();
  return `${value} ${unit}`.trim();
}

export function statusBadge(status) {
  return ({ live: "연결됨", stale: "지연", disconnected: "연결 끊김" })[status] ?? "연결 끊김";
}

function forEachNode(root, selector, callback) {
  if (typeof root.querySelectorAll === "function") {
    const nodes = root.querySelectorAll(selector);
    if (nodes.length) {
      nodes.forEach(callback);
      return;
    }
  }
  const node = root.querySelector?.(selector);
  if (node) callback(node);
}

function setText(root, field, value) {
  forEachNode(root, `[data-live-field="${field}"]`, (node) => { node.textContent = value; });
}

export function updateLivePanel(root, state, now = Date.now()) {
  if (!root) return;
  const status = state.connectionStatus(now);
  root.dataset.connection = status;
  root.dataset.hasData = state.lastReceivedAt === null ? "false" : "true";
  setText(root, "connection", statusBadge(status));
  setText(root, "source", state.source?.startsWith("mock") ? "실시간 — 모의 데이터" : "실시간 — 현장");
  const updated = state.lastReceivedAt === null ? "—" : new Date(state.lastReceivedAt).toLocaleTimeString("en-GB", { hour12: false });
  setText(root, "lastUpdate", updated);
  setText(root, "dataMessage", state.lastReceivedAt === null
    ? "데이터를 기다리는 중…"
    : status === "stale"
      ? `마지막 정상 수신 ${updated}`
      : status === "disconnected"
        ? `마지막 정상 수신 ${updated}`
        : "실시간 수신 중");
  for (const [field, [group, key, unit, digits]] of Object.entries(FIELDS)) {
    setText(root, field, formatValue(state[group][key], unit, digits));
  }
  const meterFields = {
    roofVentLeft: "roof_vent_left_pct",
    roofVentRight: "roof_vent_right_pct",
    shadeScreen1: "shade_screen_1_pct",
    shadeScreen2: "shade_screen_2_pct",
  };
  for (const [field, key] of Object.entries(meterFields)) {
    const value = state.actuators[key];
    forEachNode(root, `[data-live-meter="${field}"]`, (node) => {
      const percent = typeof value === "number" && Number.isFinite(value)
        ? Math.min(100, Math.max(0, value))
        : 0;
      node.style?.setProperty?.("--meter-value", `${percent}%`);
      node.setAttribute?.("aria-valuenow", typeof value === "number" ? String(value) : "");
    });
  }
}
