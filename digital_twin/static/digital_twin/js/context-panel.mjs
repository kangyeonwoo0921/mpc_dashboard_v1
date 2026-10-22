import { displayTitle } from "./interaction-runtime.mjs";
import { formatValue, statusBadge } from "./live-panel.mjs";
import { mappedAssetContext } from "./live-config.mjs";

export const HISTORY_EMPTY_MESSAGE = "기록 보기는 아직 없습니다. 현장 데이터 기록이 쌓이면 추가합니다.";

function percent(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "—";
}

function sourceLabel(state) {
  if (!state?.source) return "—";
  return state.source.startsWith("mock") ? "모의 데이터" : state.source === "field_collector" ? "현장 수집" : state.source.toUpperCase();
}

function updatedLabel(state) {
  return state?.lastReceivedAt == null ? "—" : new Date(state.lastReceivedAt).toLocaleTimeString("en-GB", { hour12: false });
}

function connectionLabel(state, now = Date.now()) {
  return typeof state?.connectionStatus === "function" ? statusBadge(state.connectionStatus(now)) : statusBadge("disconnected");
}

function spanActuatorRows(spanAssets, state) {
  return [["roof_vent", "천창"], ["shade_screen", "차광 스크린"],
    ["diffuse_screen", "산광 스크린"], ["side_curtain", "측창"]].map(([type, label]) => {
    const entry = spanAssets.find((asset) => asset.type === type);
    const context = mappedAssetContext(entry, state);
    return { label, value: percent(context.openingPercent),
      note: context.channel ? context.channel + " · " + context.mappingStatus : "동별 연결 없음" };
  });
}

function assetDetails(entry) {
  if (!entry) return [];
  const metadata = entry.owner.userData ?? {};
  const fields = [
    ["이름", entry.owner.name],
    ["종류", metadata.asset_type],
    ["동 번호", metadata.span_index],
    ["제어 변수", metadata.control_variable],
    ["표시 개도", typeof metadata.opening_percent === "number" ? `${metadata.opening_percent.toFixed(1)}%` : null],
    ["출처 신뢰도", metadata.source_confidence],
    ["형상 신뢰도", metadata.geometry_confidence],
    ["위치 신뢰도", metadata.position_confidence],
    ["위치 확인", typeof metadata.verified_position === "boolean" ? String(metadata.verified_position) : null],
    ["PLC 태그 확인", typeof metadata.plc_tag_verified === "boolean" ? String(metadata.plc_tag_verified) : null],
  ];
  return fields.filter(([, value]) => value !== null && value !== undefined && value !== "").map(([label, value]) => ({ label, value: String(value) }));
}

const RH_SENSOR_STUCK = 99;   // indoor RH at or above this is the known stuck sensor (99.9 %), not a reading

function num(value, digits = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : null;
}

function joinParts(parts, unit) {
  const shown = parts.filter(([, v]) => v !== null);
  return shown.length ? `${shown.map(([k, v]) => (k ? `${k} ${v}` : v)).join(" · ")}${unit}` : "—";
}

/** Greenhouse-level live sections: indoor, outdoor, actuators, field status. Faulty or unknown values are
 *  shown as a state or left out instead of as a misleading number. */
export function greenhouseSections(liveState) {
  const env = liveState?.environment ?? {};
  const act = liveState?.actuators ?? {};
  const st = liveState?.status ?? {};
  const indoor = [];
  const t = num(env.indoor_temperature_c, 1);
  const setpoint = num(env.setpoint_temperature_c, 1);
  indoor.push({ label: "온도", value: t === null ? "—" : `${t} °C`, note: setpoint === null ? null : `설정 ${setpoint} °C` });
  const rh = env.indoor_rh_pct;
  if (typeof rh === "number" && rh >= RH_SENSOR_STUCK) {
    indoor.push({ label: "습도", value: "센서 점검 필요", note: `${num(rh, 1)} % 고정` });
  } else if (typeof rh === "number") {
    const extra = [num(env.dew_point_c, 1) && `이슬점 ${num(env.dew_point_c, 1)} °C`, num(env.vpd_kpa, 2) && `VPD ${num(env.vpd_kpa, 2)} kPa`].filter(Boolean);
    indoor.push({ label: "습도", value: `${num(rh, 1)} %`, note: extra.join(" · ") || null });
  }
  if (typeof env.co2_ppm === "number" && env.co2_ppm > 0) indoor.push({ label: "CO₂", value: `${num(env.co2_ppm)} ppm` });

  const outdoor = [];
  const tout = num(env.outdoor_temperature_c, 1);
  if (tout !== null) outdoor.push({ label: "기온", value: `${tout} °C` });
  const wind = num(env.wind_speed_m_s, 1);
  if (wind !== null) outdoor.push({ label: "바람", value: `${wind} m/s`, note: env.wind_direction_text || null });
  if (st.rain !== null && st.rain !== undefined) outdoor.push({ label: "비", value: st.rain ? "비 옴" : "없음" });
  if (st.strong_wind) outdoor.push({ label: "강풍", value: "강풍 감지" });

  const pct = (key) => num(act[key]);
  const devices = [
    { label: "천창", value: joinParts([["좌", pct("roof_vent_left_pct")], ["우", pct("roof_vent_right_pct")]], " %") },
    { label: "측창", value: joinParts([["전", pct("side_vent_front_pct")], ["후", pct("side_vent_rear_pct")], ["좌", pct("side_vent_left_pct")], ["우", pct("side_vent_right_pct")]], " %") },
    { label: "수직커튼", value: joinParts([["전", pct("vertical_curtain_front_pct")], ["후", pct("vertical_curtain_rear_pct")], ["좌", pct("vertical_curtain_left_pct")], ["우", pct("vertical_curtain_right_pct")]], " %") },
    { label: "차광 · 산광", value: joinParts([["", pct("shade_screen_2_pct")], ["", pct("shade_screen_1_pct")]], " %") },
  ];
  for (const [key, label] of [["boiler_on", "보일러"], ["circulation_fan_on", "순환팬"], ["exhaust_fan_on", "배기팬"]]) {
    if (typeof act[key] === "boolean") devices.push({ label, value: act[key] ? "켜짐" : "꺼짐" });
  }

  const field = [];
  if (st.operation_mode) field.push({ label: "운전 모드", value: st.operation_mode });
  if (st.alarm !== null && st.alarm !== undefined) {
    const count = typeof st.alarm_count === "number" && st.alarm_count > 0 ? ` (${st.alarm_count}건)` : "";
    field.push({ label: "경보", value: st.alarm ? `경보 발생${count}` : st.caution ? "주의" : "없음" });
  }

  return [
    { title: "실내", rows: indoor },
    outdoor.length ? { title: "외부", rows: outdoor } : null,
    { title: "장치 (%)", rows: devices },
    field.length ? { title: "운전 상태", rows: field } : null,
  ].filter(Boolean);
}

export function buildContextModel({ selection, liveState, assetEntry = null, assetContext = {}, spanAssets = [], now = Date.now() }) {
  const connection = connectionLabel(liveState, now);
  const connectionStatus = typeof liveState?.connectionStatus === "function" ? liveState.connectionStatus(now) : "disconnected";
  const source = sourceLabel(liveState);
  const updated = updatedLabel(liveState);
  if (selection.level === "greenhouse") {
    return {
      title: "온실 전체",
      breadcrumb: [{ level: "greenhouse", label: "온실" }],
      sections: greenhouseSections(liveState),
      details: [],
      detailsMessage: "동이나 장치를 선택하면 상세 정보가 보입니다.",
      source,
      connection,
      connectionStatus,
      updated,
      liveMessage: liveState?.lastReceivedAt == null ? "데이터를 기다리는 중…" : null,
    };
  }

  if (selection.level === "span") {
    const label = `${Number(selection.spanId.slice(1))}동`;
    return {
      title: label.toUpperCase(),
      breadcrumb: [
        { level: "greenhouse", label: "온실" },
        { level: "span", spanId: selection.spanId, label },
      ],
      sections: [
        { title: "장치", rows: spanActuatorRows(spanAssets, liveState) },
        { title: "대표 환경", note: "온실 전체 센서 1개 · 동별 값이 아닙니다", rows: [
          { label: "실내 온도", value: formatValue(liveState?.environment?.indoor_temperature_c, "°C", 1) },
          { label: "실내 습도", value: formatValue(liveState?.environment?.indoor_rh_pct, "%", 1) },
          { label: "VPD", value: formatValue(liveState?.environment?.vpd_kpa, "kPa", 3) },
        ] },
      ],
      details: [{ label: "공간", value: selection.spanId }, { label: "환경 범위", value: "온실 대표값" }],
      source,
      connection,
      connectionStatus,
      updated,
    };
  }

  const owner = assetEntry?.owner;
  const spanLabel = selection.spanId ? `${Number(selection.spanId.slice(1))}동` : null;
  const title = owner ? displayTitle(owner, assetEntry.type) : selection.assetId ?? "장치";
  const breadcrumb = [{ level: "greenhouse", label: "온실" }];
  if (selection.spanId) breadcrumb.push({ level: "span", spanId: selection.spanId, label: spanLabel });
  breadcrumb.push({ level: "asset", label: title });
  const liveRows = [];
  if (typeof assetContext.openingPercent === "number") liveRows.push({ label: "열림", value: percent(assetContext.openingPercent) });
  if (owner?.userData?.control_variable) liveRows.push({ label: "제어 변수", value: owner.userData.control_variable });
  if (selection.spanId) liveRows.push({ label: "동", value: selection.spanId });
  if (assetContext.channel) liveRows.push({ label: "연결 채널", value: assetContext.channel });
  if (assetContext.mappingStatus) liveRows.push({ label: "연결 상태", value: assetContext.mappingStatus });
  if (!assetContext.channel && owner?.userData?.control_variable) {
    liveRows.push({ label: "실시간 연결", value: "미설정" });
  }
  return {
    title: title.toUpperCase(),
    breadcrumb,
    sections: liveRows.length ? [{ title: "실시간 장치 상태", rows: liveRows }] : [],
    liveMessage: liveRows.length ? null : assetEntry?.type === "crop_zone"
      ? "재배 구역은 보기·확대만 지원합니다. 작물 분석은 없습니다."
      : "확인된 실시간 연결이 없는 장치입니다.",
    details: assetDetails(assetEntry),
    source,
    connection,
    connectionStatus,
    updated,
  };
}

function appendRows(container, rows) {
  const list = document.createElement("dl");
  list.className = "context-rows";
  for (const row of rows) {
    const item = document.createElement("div");
    const term = document.createElement("dt");
    const valueWrap = document.createElement("dd");
    const value = document.createElement("strong");
    term.textContent = row.label;
    value.textContent = row.value ?? "—";
    valueWrap.append(value);
    if (row.note) {
      const note = document.createElement("small");
      note.textContent = row.note;
      valueWrap.append(note);
    }
    item.append(term, valueWrap);
    list.append(item);
  }
  container.append(list);
}

export class ContextPanelRuntime {
  constructor(root, { onNavigate = () => {} } = {}) {
    this.root = root;
    this.onNavigate = onNavigate;
    this.activeTab = "live";
    this.input = null;
    root.querySelectorAll("[data-context-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        this.activeTab = button.dataset.contextTab;
        this.render();
      });
    });
    root.querySelector("[data-context-collapse]")?.addEventListener("click", (event) => {
      const collapsed = root.dataset.collapsed !== "true";
      root.dataset.collapsed = String(collapsed);
      event.currentTarget.setAttribute("aria-expanded", String(!collapsed));
      event.currentTarget.setAttribute("aria-label", collapsed ? "패널 펼치기" : "패널 접기");
    });
  }

  update(input) {
    this.input = input;
    this.render();
  }

  render() {
    if (!this.input) return;
    const model = buildContextModel(this.input);
    this.root.dataset.selectionLevel = this.input.selection.level;
    const title = this.root.querySelector("[data-context-title]");
    if (title) title.textContent = model.title;
    const source = this.root.querySelector('[data-live-field="source"]');
    const connection = this.root.querySelector('[data-live-field="connection"]');
    const updated = this.root.querySelector('[data-live-field="lastUpdate"]');
    if (source) source.textContent = `실시간 — ${model.source}`;
    if (connection) connection.textContent = model.connection;
    if (updated) updated.textContent = model.updated;
    this.root.dataset.connection = model.connectionStatus;

    const breadcrumb = this.root.querySelector("[data-context-breadcrumb]");
    breadcrumb.replaceChildren();
    model.breadcrumb.forEach((item, index) => {
      if (index) {
        const separator = document.createElement("span");
        separator.textContent = "/";
        breadcrumb.append(separator);
      }
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.label;
      button.disabled = index === model.breadcrumb.length - 1;
      button.addEventListener("click", () => this.onNavigate(item));
      breadcrumb.append(button);
    });

    this.root.querySelectorAll("[data-context-tab]").forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.contextTab === this.activeTab));
    });
    const content = this.root.querySelector("[data-context-content]");
    content.replaceChildren();
    if (this.activeTab === "history") {
      const empty = document.createElement("div");
      empty.className = "context-empty";
      empty.append(Object.assign(document.createElement("strong"), { textContent: "기록 없음" }));
      const text = document.createElement("p");
      text.textContent = HISTORY_EMPTY_MESSAGE;
      empty.append(text);
      content.append(empty);
      return;
    }
    if (this.activeTab === "details") {
      if (model.details.length) appendRows(content, model.details);
      else {
        const message = document.createElement("p");
        message.className = "context-message";
        message.textContent = model.detailsMessage ?? "추가 정보가 없습니다.";
        content.append(message);
      }
      return;
    }
    if (model.liveMessage) {
      const message = document.createElement("p");
      message.className = "context-message";
      message.textContent = model.liveMessage;
      content.append(message);
    }
    for (const section of model.sections) {
      const node = document.createElement("section");
      node.className = "context-section";
      const heading = document.createElement("h3");
      heading.textContent = section.title;
      node.append(heading);
      if (section.note) {
        const note = document.createElement("p");
        note.className = "context-scope-note";
        note.textContent = section.note;
        node.append(note);
      }
      appendRows(node, section.rows);
      content.append(node);
    }
  }
}
