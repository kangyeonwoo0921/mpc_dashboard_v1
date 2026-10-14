export const LIVE_CONFIG = Object.freeze({
  endpoint: "/api/digital-twin/live/",
  pollIntervalMs: 2000,
  staleAfterMs: 10000,
  smoothingTimeSeconds: 0.23,
  roofVentMaxAngleDeg: 90,
});

// Each span has a +Y (_01) and -Y (_02) ridge vent leaf. L = +Y (left when
// facing +X from the X1 front) is provisional until the Growlink L/R
// convention is confirmed on site.
export const OBJECT_MAP = Object.freeze({
  roofVentLeft: Object.freeze({
    names: Object.freeze(["GH_VENT_S01_01_PIVOT", "GH_VENT_S02_01_PIVOT", "GH_VENT_S03_01_PIVOT", "GH_VENT_S04_01_PIVOT"]),
    dtoKey: "roof_vent_left_pct",
    kind: "roofVent",
    direction: 1,
    provisional: true,
  }),
  roofVentRight: Object.freeze({
    names: Object.freeze(["GH_VENT_S01_02_PIVOT", "GH_VENT_S02_02_PIVOT", "GH_VENT_S03_02_PIVOT", "GH_VENT_S04_02_PIVOT"]),
    dtoKey: "roof_vent_right_pct",
    kind: "roofVent",
    direction: -1,
    provisional: true,
  }),
  shadeScreen1: Object.freeze({
    names: Object.freeze([
      "GH_DIFFUSE_SCREEN_S01_N_PIVOT",
      "GH_DIFFUSE_SCREEN_S01_P_PIVOT",
      "GH_DIFFUSE_SCREEN_S02_N_PIVOT",
      "GH_DIFFUSE_SCREEN_S02_P_PIVOT",
      "GH_DIFFUSE_SCREEN_S03_N_PIVOT",
      "GH_DIFFUSE_SCREEN_S03_P_PIVOT",
      "GH_DIFFUSE_SCREEN_S04_N_PIVOT",
      "GH_DIFFUSE_SCREEN_S04_P_PIVOT",
    ]),
    dtoKey: "shade_screen_1_pct",
    kind: "screen",
    direction: "across_span",
    provisional: false,
  }),
  shadeScreen2: Object.freeze({
    names: Object.freeze([
      "GH_SHADE_SCREEN_S01_N_PIVOT",
      "GH_SHADE_SCREEN_S01_P_PIVOT",
      "GH_SHADE_SCREEN_S02_N_PIVOT",
      "GH_SHADE_SCREEN_S02_P_PIVOT",
      "GH_SHADE_SCREEN_S03_N_PIVOT",
      "GH_SHADE_SCREEN_S03_P_PIVOT",
      "GH_SHADE_SCREEN_S04_N_PIVOT",
      "GH_SHADE_SCREEN_S04_P_PIVOT",
    ]),
    dtoKey: "shade_screen_2_pct",
    kind: "screen",
    direction: "across_span",
    provisional: false,
  }),
});

export const CHANNEL_LABELS = Object.freeze({
  roofVentLeft: "RoofVent_L", roofVentRight: "RoofVent_R",
  shadeScreen1: "ShadeScreen_01", shadeScreen2: "ShadeScreen_02",
});

export function mappedAssetContext(entry, state) {
  for (let object = entry?.owner; object; object = object.parent) {
    for (const [key, mapping] of Object.entries(OBJECT_MAP)) {
      if (!mapping.names.includes(object.name)) continue;
      const value = state?.actuators?.[mapping.dtoKey];
      return {
        openingPercent: typeof value === "number" && Number.isFinite(value) ? value : null,
        channel: CHANNEL_LABELS[key],
        mappingStatus: mapping.provisional ? "잠정" : "연결됨",
        mappingNote: mapping.provisional ? CHANNEL_LABELS[key] + " 연결 잠정" : null,
      };
    }
  }
  return {};
}
