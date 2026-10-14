export const CAMERA_FIT_MARGIN = 0.97;
export const CAMERA_TRANSITION_MS = 600;
export const SPAN_IDS = Object.freeze(["S01", "S02", "S03", "S04"]);

export const SCENE_COLORS = Object.freeze({
  background: 0x18232b,
  fog: 0x18232b,
  hover: 0x5fbca9,
  selected: 0x79c9b5,
});

export const CAMERA_PRESETS = Object.freeze({
  overview: Object.freeze({
    label: "전체",
    mode: "fit",
    focus: "model",
    direction: Object.freeze([1, 0.62, 0.92]),
    visibility: "exterior",
    margin: CAMERA_FIT_MARGIN,
  }),
  front: Object.freeze({
    label: "앞면",
    mode: "fit",
    focus: "model",
    direction: Object.freeze([-1, 0.08, 0]),
    visibility: "exterior",
    margin: 1.18,
  }),
  rear: Object.freeze({
    label: "뒷면",
    mode: "fit",
    focus: "model",
    direction: Object.freeze([1, 0.08, 0]),
    visibility: "exterior",
    margin: 1.18,
  }),
  roof: Object.freeze({
    label: "지붕",
    mode: "fit",
    focus: "model",
    direction: Object.freeze([0.34, 1.75, 0.52]),
    visibility: "exterior",
    margin: 1.1,
  }),
  interior: Object.freeze({
    label: "내부",
    mode: "interior",
    focus: "interior",
    visibility: "interior",
  }),
  equipment: Object.freeze({
    label: "설비",
    mode: "fit",
    focus: "equipment",
    direction: Object.freeze([-1, 0.48, 0.9]),
    visibility: "equipment",
    margin: 1.45,
  }),
  control: Object.freeze({
    label: "제어 장치",
    mode: "fit",
    focus: "controls",
    direction: Object.freeze([0.55, 1.15, 0.82]),
    visibility: "control_devices",
    margin: 1.08,
  }),
});

export const VIEW_PRESET_ORDER = Object.freeze([
  "overview",
  "front",
  "rear",
  "roof",
  "interior",
  "equipment",
  "control",
]);

export const LAYER_NODE_NAMES = Object.freeze({
  cover: Object.freeze(["GH_ROOF_COVER"]),
  crops: Object.freeze(["GH_CROPS", "GH_BEDS"]),
  equipment: Object.freeze(["GH_FERTIGATION"]),
  sensors: Object.freeze(["GH_SENSORS"]),
  controls: Object.freeze([
    "GH_VENTS",
    "GH_SCREENS",
    "GH_SIDE_CURTAIN_LEFT",
    "GH_SIDE_CURTAIN_RIGHT",
  ]),
});

export const FOCUS_NODE_NAMES = Object.freeze({
  interior: Object.freeze(["GH_CROPS", "GH_BEDS"]),
  equipment: Object.freeze(["GH_FERTIGATION_UNIT"]),
  controls: Object.freeze([
    "GH_VENTS",
    "GH_SCREENS",
    "GH_SIDE_CURTAIN_LEFT",
    "GH_SIDE_CURTAIN_RIGHT",
    "GH_SENSORS",
  ]),
});

export const VISIBILITY_PRESETS = Object.freeze({
  exterior: Object.freeze({ cover: true, crops: true, equipment: true, sensors: true, controls: true }),
  interior: Object.freeze({ cover: false, crops: true, equipment: true, sensors: true, controls: true }),
  equipment: Object.freeze({ cover: false, crops: false, equipment: true, sensors: false, controls: false }),
  control_devices: Object.freeze({ cover: false, crops: true, equipment: false, sensors: true, controls: true }),
});

export const INTERACTABLE_ASSET_TYPES = Object.freeze(new Set([
  "roof_vent",
  "shade_screen",
  "diffuse_screen",
  "side_curtain",
  "sensor",
  "sensor_anchor",
  "crop_bed",
  "tank",
  "pump",
  "blower",
  "filter",
  "control_panel",
  "purifier",
  "flow_meter",
  "pressure_gauge",
  "valve",
]));

export const SPAN_PICK_ASSET_TYPES = Object.freeze(new Set([
  "roof_cover",
  "roof_frame",
]));

export const SPAN_EMPHASIS_ASSET_TYPES = Object.freeze(new Set([
  "roof_cover",
  "roof_frame",
  "roof_vent",
  "vent_frame",
  "shade_screen",
  "diffuse_screen",
  "crop_bed",
  "rafter",
  "truss",
]));

export const ASSET_LABELS = Object.freeze({
  roof_vent: "천창",
  shade_screen: "차광 스크린",
  diffuse_screen: "산광 스크린",
  side_curtain: "측창 커튼",
  sensor: "센서",
  sensor_anchor: "센서 거치대",
  crop_bed: "재배 구역",
  tank: "탱크",
  pump: "양액 펌프",
  blower: "링 블로워",
  filter: "필터",
  control_panel: "제어반",
  purifier: "정수기",
  flow_meter: "유량계",
  pressure_gauge: "압력계",
  valve: "밸브",
});

export const VIEWER_UI_CONFIG = Object.freeze({
  panelTransitionMs: 200,
  staleUiRefreshMs: 1000,
  maxPixelRatio: 2,
});
