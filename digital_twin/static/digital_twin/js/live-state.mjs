const ENVIRONMENT_KEYS = Object.freeze([
  "indoor_temperature_c",
  "indoor_rh_pct",
  "vpd_kpa",
  "co2_ppm",
  "dew_point_c",
  "setpoint_temperature_c",
  "outdoor_temperature_c",
  "solar_w_m2",
  "wind_speed_m_s",
  "wind_direction_text",
  "accumulated_solar",
]);

const ACTUATOR_KEYS = Object.freeze([
  "roof_vent_left_pct",
  "roof_vent_right_pct",
  "side_vent_front_pct",
  "side_vent_rear_pct",
  "side_vent_left_pct",
  "side_vent_right_pct",
  "vertical_curtain_front_pct",
  "vertical_curtain_rear_pct",
  "vertical_curtain_left_pct",
  "vertical_curtain_right_pct",
  "shade_screen_1_pct",
  "shade_screen_2_pct",
  "boiler_on",
  "circulation_fan_on",
  "exhaust_fan_on",
]);

function emptyRecord(keys) {
  return Object.fromEntries(keys.map((key) => [key, null]));
}

export function isNormalizedSnapshot(value) {
  return Boolean(
    value &&
      typeof value === "object" &&
      typeof value.source === "string" &&
      typeof value.connected === "boolean" &&
      value.environment &&
      typeof value.environment === "object" &&
      value.actuators &&
      typeof value.actuators === "object",
  );
}

export class LiveState {
  constructor({ staleAfterMs = 10000 } = {}) {
    this.staleAfterMs = staleAfterMs;
    this.source = null;
    this.connected = false;
    this.transportConnected = false;
    this.timestamp = null;
    this.lastReceivedAt = null;
    this.environment = emptyRecord(ENVIRONMENT_KEYS);
    this.actuators = emptyRecord(ACTUATOR_KEYS);
    this.lastError = null;
  }

  acceptSnapshot(snapshot, receivedAt = Date.now()) {
    if (!isNormalizedSnapshot(snapshot)) {
      throw new TypeError("LIVE API returned an invalid normalized DTO");
    }
    this.source = snapshot.source;
    this.connected = snapshot.connected;
    this.transportConnected = true;
    this.timestamp = typeof snapshot.timestamp === "string" ? snapshot.timestamp : null;
    this.lastReceivedAt = receivedAt;
    this.environment = { ...emptyRecord(ENVIRONMENT_KEYS), ...snapshot.environment };
    this.actuators = { ...emptyRecord(ACTUATOR_KEYS), ...snapshot.actuators };
    this.lastError = null;
  }

  markRequestFailure(error) {
    this.transportConnected = false;
    this.lastError = error instanceof Error ? error.message : String(error);
    // Last valid environment and actuator values intentionally remain intact.
  }

  connectionStatus(now = Date.now()) {
    if (!this.transportConnected || !this.connected) return "disconnected";
    if (this.lastReceivedAt === null || now - this.lastReceivedAt > this.staleAfterMs) return "stale";
    return "live";
  }
}
