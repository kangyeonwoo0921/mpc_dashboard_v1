// Screen recommendation page: what to do now, the next planned change and why; GHI and plan charts;
// crop-plane light estimate; operating settings (collapsed).
// Data: GET /api/recommendation/screens/, GET|POST /api/recommendation/settings/, POST .../settings/reset/.
// All server text is inserted with textContent (never innerHTML). Values are "open %" (100 = 걷힘).

import { FORECAST_REASON, buildOpsStatus, renderOpsStatus } from "./ops-status.mjs";
import {
  MODE_LABEL, SCREEN_COLOR, STAGE_LABEL, STATE_LABEL, cropLightText, el, fmtPct, fmtTime, fmtW, nextChangeText,
  renderGhiChart, renderPlanChart,
} from "./rec-common.mjs";

const API = {
  screens: "/api/recommendation/screens/",
  settings: "/api/recommendation/settings/",
  reset: "/api/recommendation/settings/reset/",
};
const POLL_MS = 60_000;
const $ = (id) => document.getElementById(id);
let lastPayload = null;

async function fetchJSON(url, options) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(`HTTP ${response.status}`), { body });
  return body;
}

// ---------------------------------------------------------------- recommendation

function liveStatusFrom(inputs) {
  if (!inputs.live_connected) return { source: inputs.live_source, status: "disconnected", receivedAt: null };
  const received = inputs.live_timestamp ? Date.parse(inputs.live_timestamp) : null;
  return { source: inputs.live_source, status: "live", receivedAt: Number.isFinite(received) ? received : null };
}

/** Open-% bar: 0 (펼침) on the left, 100 (걷힘) on the right; fill = recommended, marker = current. */
function openBar(screen) {
  const bar = el("div", { class: "open-bar", role: "img",
    "aria-label": `현재 열림 ${fmtPct(screen.current_open_percent)}%, 추천 열림 ${fmtPct(screen.recommended_open_percent)}%` });
  if (screen.recommended_open_percent !== null && screen.recommended_open_percent !== undefined) {
    bar.append(el("i", { class: "open-fill", style: `width:${screen.recommended_open_percent}%` }));
  }
  if (screen.current_open_percent !== null && screen.current_open_percent !== undefined) {
    bar.append(el("b", { class: "open-now", style: `left:${screen.current_open_percent}%`, title: "현재 위치" }));
  }
  return el("div", { class: "open-wrap" }, bar,
    el("div", { class: "bar-label" }, el("span", { text: "펼침 0" }), el("span", { text: "열림 %" }), el("span", { text: "걷힘 100" })));
}

function renderScreen(key, screen, times) {
  const card = $(`card-${key}`);
  card.style.setProperty("--screen", SCREEN_COLOR[key]);
  const reasons = screen.reasons ?? [];
  card.replaceChildren(...[
    el("div", { class: "screen-head" },
      el("h3", { text: screen.label }),
      el("span", { class: "screen-state", text: STATE_LABEL[screen.state] ?? screen.state })),
    el("div", { class: "screen-main" },
      el("span", { class: `action ${screen.action}`, text: screen.action_label }),
      el("div", { class: "move" },
        el("span", { text: "열림 " }), el("strong", { text: fmtPct(screen.current_open_percent) }), el("span", { text: "% → " }),
        el("strong", { text: fmtPct(screen.recommended_open_percent) }), el("span", { text: "%" }))),
    openBar(screen),
    el("p", { class: "next", text: `다음: ${nextChangeText(screen, times)}` }),
    reasons.length ? el("p", { class: "why", text: reasons[0] }) : null,
    reasons.length > 1
      ? el("details", { class: "why-more" }, el("summary", { text: `판단 근거 ${reasons.length}개 모두 보기` }),
        el("ul", {}, reasons.map((r) => el("li", { text: r }))))
      : null,
  ].filter(Boolean));
}

function renderCropLight(crop) {
  const text = cropLightText(crop);
  $("crop-main").textContent = text ?? `계산 불가 (${crop?.reason === "no_ghi" ? "외부 일사 없음" : crop?.reason ?? "정보 없음"})`;
  const rows = [];
  if (crop && crop.status === "ok") {
    rows.push(["직달 일사 (DNI, 추정)", `${fmtW(crop.dni_W_m2)} W/m²`], ["산란 일사 (DHI, 추정)", `${fmtW(crop.dhi_W_m2)} W/m²`],
      ["직달광이 닿는 작물면", `${Math.round(crop.sunlit_fraction * 100)}%`],
      ["계산된 작물면", `${Math.round(crop.resolved_fraction * 100)}% (측창·방풍벽 광학값 없음)`]);
  }
  $("crop-rows").replaceChildren(...rows.map(([k, v]) => el("div", {}, el("dt", { text: k }), el("dd", { text: v }))));
}

function renderRecommendation(p) {
  lastPayload = p;
  const inp = p.inputs;
  renderOpsStatus($("ops-status"), buildOpsStatus({ live: liveStatusFrom(inp), recommendation: p }));
  $("updated-at").textContent = fmtTime(p.generated_at);
  $("sum-stage").textContent = `${STAGE_LABEL[p.settings.growth_stage] ?? p.settings.growth_stage} (잠정)`;
  $("sum-days").textContent = `${p.settings.days_after_transplant}일`;
  $("sum-mode").textContent = MODE_LABEL[p.settings.operation_mode] ?? p.settings.operation_mode;
  $("sum-sun").textContent = `${fmtTime(inp.sunrise)} · ${fmtTime(inp.sunset)}`;
  $("sum-tout").textContent = inp.outdoor_temperature_c === null ? "—" : `${inp.outdoor_temperature_c.toFixed(1)} °C`;
  $("sum-ghi").textContent = inp.solar_w_m2 === null ? "—" : `${Math.round(inp.solar_w_m2)} W/m²`;
  $("guide-note").textContent = p.settings.growth_guide ? `참고: ${p.settings.growth_guide}` : "";
  for (const key of ["shade_screen", "diffuse_screen"]) renderScreen(key, p.screens[key], p.plan_times);
  renderGhiChart($("chart"), p);
  renderPlanChart($("plan-chart"), p);
  const reason = inp.forecast_status === "ok" ? "" : ` 예측 없음: ${FORECAST_REASON[inp.forecast_reason] ?? inp.forecast_reason ?? inp.forecast_status}.`;
  $("chart-note").textContent = `5분 평균 · 피복 위 외부 센서 기준.${reason}`;
  $("advisories").replaceChildren(...p.advisories.map((a) => el("li", { text: a })));
  renderCropLight(p.crop_light);
}

async function refresh() {
  try {
    renderRecommendation(await fetchJSON(API.screens));
  } catch {
    renderOpsStatus($("ops-status"), buildOpsStatus({ live: null, recommendationError: true }));
  }
}

// ---------------------------------------------------------------- settings

let settingsState = null;
const pending = new Map();

function fieldValue(meta) {
  return pending.has(meta.key) ? pending.get(meta.key) : settingsState.values[meta.key];
}

function renderSettings(desc) {
  settingsState = desc;
  pending.clear();
  const form = $("settings-form");
  form.replaceChildren();
  for (const group of desc.groups) {
    const fs = el("fieldset", {}, el("legend", { text: group.label }));
    for (const meta of desc.fields.filter((f) => f.group === group.key)) fs.append(renderField(meta));
    form.append(fs);
  }
  $("settings-updated").textContent = desc.updated_at ? `마지막 변경 ${new Date(desc.updated_at).toLocaleString("ko-KR")}${desc.updated_by ? ` · ${desc.updated_by}` : ""}` : "기본값 사용 중";
  $("history").replaceChildren(...(desc.history.length ? desc.history.map((h) => el("li", {
    text: `${new Date(h.time).toLocaleString("ko-KR")} · ${h.by ?? "익명"} · ` +
      Object.entries(h.changes).map(([k, c]) => `${labelOf(k)}: ${c.from} → ${c.to}`).join(", ") + (h.note ? ` (${h.note})` : ""),
  })) : [el("li", { text: "기록 없음" })]));
  updateSaveButton();
}

const labelOf = (key) => settingsState?.fields.find((f) => f.key === key)?.label ?? key;

function renderField(meta) {
  const id = `f-${meta.key}`;
  const value = fieldValue(meta);
  let input;
  if (meta.kind === "choice") {
    input = el("select", { id }, meta.choices.map((c) => el("option", { value: c.value, text: c.label, selected: c.value === value })));
  } else if (meta.kind === "date") {
    input = el("input", { id, type: "date", value });
  } else {
    input = el("input", { id, type: "number", inputmode: "decimal", min: meta.min, max: meta.max, step: meta.step, value });
  }
  const isDefault = String(value) === String(meta.default);
  const resetBtn = el("button", { type: "button", class: "link-btn", text: "기본값", disabled: isDefault, title: `기본값: ${meta.default}` });
  const row = el("div", { class: "field", "data-key": meta.key },
    el("label", { for: id, text: meta.label }, meta.provisional ? el("span", { class: "tag tag-prov", text: "잠정" }) : null),
    el("div", { class: "ctrl" }, input, meta.unit ? el("span", { class: "unit", text: meta.unit }) : null, resetBtn),
    el("div", { class: "meta" }, el("span", { text: meta.help }), el("span", { class: "src", text: `출처: ${meta.source}` })));
  const onChange = () => {
    const raw = input.value;
    const v = meta.kind === "number" ? (raw === "" ? raw : Number(raw)) : raw;
    if (String(v) === String(settingsState.values[meta.key])) pending.delete(meta.key);
    else pending.set(meta.key, v);
    row.classList.toggle("changed", pending.has(meta.key));
    row.classList.remove("error");
    row.querySelector(".err")?.remove();
    resetBtn.disabled = String(v) === String(meta.default);
    updateSaveButton();
  };
  input.addEventListener("input", onChange);
  input.addEventListener("change", onChange);
  resetBtn.addEventListener("click", () => { input.value = meta.default; onChange(); });
  return row;
}

function updateSaveButton() {
  $("btn-save").disabled = pending.size === 0;
  $("btn-save").textContent = pending.size ? `저장 (${pending.size})` : "저장";
}

function showMessage(text, level) {
  const node = $("form-message");
  node.textContent = text;
  node.className = `form-message ${level}`;
}

async function save() {
  const body = { values: Object.fromEntries(pending), changed_by: $("changed-by").value, note: $("change-note").value };
  try {
    renderSettings(await fetchJSON(API.settings, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }));
    $("change-note").value = "";
    showMessage("저장했습니다. 추천에 바로 반영됩니다.", "ok");
    refresh();
  } catch (error) {
    const errors = error.body?.errors ?? {};
    for (const [key, message] of Object.entries(errors)) {
      const row = document.querySelector(`.field[data-key="${CSS.escape(key)}"]`);
      if (!row) continue;
      row.classList.add("error");
      row.querySelector(".err")?.remove();
      row.append(el("div", { class: "err", text: message }));
    }
    showMessage("저장하지 못했습니다. 표시된 항목을 확인하세요.", "bad");
  }
}

async function resetAll() {
  if (!window.confirm("모든 설정을 기본값으로 되돌릴까요?")) return;
  try {
    renderSettings(await fetchJSON(API.reset, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ changed_by: $("changed-by").value }) }));
    showMessage("기본값으로 되돌렸습니다.", "ok");
    refresh();
  } catch {
    showMessage("되돌리지 못했습니다.", "bad");
  }
}

async function init() {
  $("btn-save").addEventListener("click", save);
  $("btn-reset-all").addEventListener("click", resetAll);
  window.addEventListener("beforeunload", (event) => { if (pending.size) event.preventDefault(); });
  try {
    renderSettings(await fetchJSON(API.settings));
  } catch {
    showMessage("설정을 불러오지 못했습니다.", "bad");
  }
  await refresh();
  setInterval(refresh, POLL_MS);
  let resizeTimer;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (lastPayload) renderRecommendation(lastPayload); }, 250); });
}

init();
