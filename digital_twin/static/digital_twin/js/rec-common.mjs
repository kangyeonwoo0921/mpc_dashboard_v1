// Shared pieces of the screen recommendation UI (3D viewer panel and /recommendation/ page).
// Every value is "open %": 100 = retracted (걷힘), 0 = fully deployed (펼침).
// Server text is always inserted with textContent.

export const STATE_LABEL = Object.freeze({
  SAFETY_OVERRIDE: "안전 우선", NIGHT_INSULATION: "밤 보온", NIGHT_OPEN: "밤 · 보온 안 함",
  DAY_LIGHT_PRESERVATION: "낮 · 빛 보존", DAY_SHADE_ASSIST: "낮 · 차광", DAY_VENTILATION: "낮 · 차광 불필요",
  DAY_HOLD: "낮 · 유지", DAY: "낮", NO_DATA: "데이터 없음",
});
export const MODE_LABEL = Object.freeze({ auto: "자동", hot: "고온기", cold: "저온기" });
export const STAGE_LABEL = Object.freeze({ establishment: "활착기", vegetative: "생육기", flowering: "개화·착과기", harvest: "수확기" });
export const SCREEN_COLOR = Object.freeze({ shade_screen: "#d4aa5c", diffuse_screen: "#6ba7d6" });
const MOVE_TOLERANCE = 5;

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined) node.append(c);
  return node;
}

export const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }) : "—");
export const fmtPct = (v) => (v === null || v === undefined ? "—" : `${Math.round(v)}`);
export const fmtW = (v) => (v === null || v === undefined ? "—" : `${Math.round(v)}`);

/** First planned change after now: { time, open, verb } or null when the plan stays put. */
export function nextChange(screen, times) {
  const plan = screen?.plan_open_percent ?? [];
  const base = plan[0];
  if (base === null || base === undefined) return null;
  for (let i = 1; i < plan.length; i += 1) {
    const v = plan[i];
    if (v !== null && v !== undefined && Math.abs(v - base) > MOVE_TOLERANCE) {
      return { time: times[i], open: v, verb: v < base ? "펼침" : "걷음" };
    }
  }
  return null;
}

export function nextChangeText(screen, times) {
  const change = nextChange(screen, times);
  return change ? `${fmtTime(change.time)} ${change.verb} 예정 (열림 ${fmtPct(change.open)}%)` : "앞으로 60분 변화 없음";
}

/** "열림 100% → 0%" line for the current and recommended position. */
export function moveText(screen) {
  return `열림 ${fmtPct(screen.current_open_percent)}% → ${fmtPct(screen.recommended_open_percent)}%`;
}

function svgHost(host, width, height) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const add = (tag, attrs, text) => {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (text !== undefined) node.textContent = text;
    svg.append(node);
    return node;
  };
  return { svg, add };
}

/** Measured (last hour) and forecast (next hour) GHI with clear-sky and the shading threshold. */
export function renderGhiChart(host, payload, { compact = false } = {}) {
  const fc = payload.forecast ?? {};
  const obs = (fc.recent_observations ?? []).filter((o) => o.ghi_w_m2 !== null).map((o) => [new Date(o.time), o.ghi_w_m2]);
  const hz = fc.horizons ?? [];
  const pred = hz.filter((h) => h.ghi_w_m2 !== null).map((h) => [new Date(h.target_time), h.ghi_w_m2]);
  const clear = hz.filter((h) => h.ghi_clear_w_m2 !== null).map((h) => [new Date(h.target_time), h.ghi_clear_w_m2]);
  const threshold = Number(payload.settings.shade_threshold_w_m2);
  const issue = new Date(payload.issue_time);
  const t0 = obs.length ? obs[0][0] : new Date(issue.getTime() - 55 * 60_000);
  const t1 = new Date(issue.getTime() + 60 * 60_000);
  const ymax = Math.max(compact ? 800 : 1000, threshold * 1.15, ...obs.map((p) => p[1]), ...pred.map((p) => p[1]), ...clear.map((p) => p[1]));
  const font = compact ? 10 : 11;
  const W = host.clientWidth || (compact ? 280 : 800), H = host.clientHeight || (compact ? 120 : 260);
  const L = compact ? 34 : 46, R = 8, T = 10, B = compact ? 18 : 26;
  const x = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
  const y = (v) => T + (1 - v / ymax) * (H - T - B);
  const { svg, add } = svgHost(host, W, H);
  const step = compact ? 400 : 200;
  for (let v = 0; v <= ymax; v += step) {
    add("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#26343d", "stroke-width": 1 });
    add("text", { x: L - 5, y: y(v) + 4, "text-anchor": "end", fill: "#8b9ba3", "font-size": font }, v);
  }
  const tick = compact ? 1_800_000 : 900_000;
  for (let t = new Date(Math.ceil(t0 / tick) * tick); t <= t1; t = new Date(t.getTime() + tick)) {
    add("text", { x: x(t), y: H - 5, "text-anchor": "middle", fill: "#8b9ba3", "font-size": font }, fmtTime(t.toISOString()));
  }
  add("line", { x1: x(issue), x2: x(issue), y1: T, y2: H - B, stroke: "#4b5d67", "stroke-dasharray": "3 3" });
  add("text", { x: x(issue) + 4, y: T + 9, fill: "#a6b4bb", "font-size": font }, "지금");
  const path = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  if (clear.length) add("path", { d: path(clear), fill: "none", stroke: "#7f8f97", "stroke-width": 1.4, "stroke-dasharray": "5 4" });
  add("line", { x1: L, x2: W - R, y1: y(threshold), y2: y(threshold), stroke: "#d4aa5c", "stroke-width": 1.4 });
  if (!compact) add("text", { x: W - R - 2, y: y(threshold) - 4, "text-anchor": "end", fill: "#d4aa5c", "font-size": font }, `차광 기준 ${threshold}`);
  if (obs.length) add("path", { d: path(obs), fill: "none", stroke: "#e6edf0", "stroke-width": 2 });
  if (pred.length) {
    const joined = obs.length ? [obs[obs.length - 1], ...pred] : pred;
    add("path", { d: path(joined), fill: "none", stroke: "#65ae9e", "stroke-width": 2.5 });
  }
  if (!obs.length && !pred.length) {
    add("text", { x: (L + W - R) / 2, y: (T + H - B) / 2, "text-anchor": "middle", fill: "#a6b4bb", "font-size": compact ? 11 : 14 },
      "표시할 일사 데이터가 없습니다");
  }
  host.replaceChildren(svg);
}

/** 60-min recommended open % per screen as step lines (top = 걷힘 100 %, bottom = 펼침 0 %). */
export function renderPlanChart(host, payload) {
  const times = payload.plan_times.map((t) => new Date(t));
  const W = host.clientWidth || 800, H = host.clientHeight || 150, L = 46, R = 12, T = 10, B = 24;
  const t0 = times[0], t1 = times[times.length - 1];
  const x = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
  const y = (v) => T + (1 - v / 100) * (H - T - B);
  const { svg, add } = svgHost(host, W, H);
  for (const [v, label] of [[100, "걷힘 100"], [50, "50"], [0, "펼침 0"]]) {
    add("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#26343d", "stroke-width": 1 });
    add("text", { x: L - 5, y: y(v) + 4, "text-anchor": "end", fill: "#8b9ba3", "font-size": 11 }, label);
  }
  times.forEach((t, i) => {
    if (i % 3 === 0) add("text", { x: x(t), y: H - 5, "text-anchor": "middle", fill: "#8b9ba3", "font-size": 11 }, fmtTime(t.toISOString()));
  });
  for (const [key, screen] of Object.entries(payload.screens)) {
    const plan = screen.plan_open_percent;
    let d = "";
    plan.forEach((v, i) => {
      if (v === null || v === undefined) return;
      const px = x(times[i]);
      const nx = i + 1 < times.length ? x(times[i + 1]) : px;
      d += `${d ? "L" : "M"}${px.toFixed(1)},${y(v).toFixed(1)} L${nx.toFixed(1)},${y(v).toFixed(1)} `;
    });
    if (d) add("path", { d, fill: "none", stroke: SCREEN_COLOR[key] ?? "#ccc", "stroke-width": 2.5 });
    if (screen.current_open_percent !== null && screen.current_open_percent !== undefined) {
      add("circle", { cx: x(t0), cy: y(screen.current_open_percent), r: 4, fill: "none", stroke: SCREEN_COLOR[key] ?? "#ccc", "stroke-width": 2 });
    }
  }
  host.replaceChildren(svg);
}

/** Crop-plane direct beam line, or null when the estimate is not available. */
export function cropLightText(crop) {
  if (!crop || crop.status !== "ok") return null;
  const now = `${fmtW(crop.current_direct_mean_W_m2)} W/m²`;
  if (crop.recommended_direct_mean_W_m2 === crop.current_direct_mean_W_m2) return `작물면 직달광 ${now} (추천대로 해도 같음)`;
  return `작물면 직달광 ${now} → 추천대로 하면 ${fmtW(crop.recommended_direct_mean_W_m2)} W/m²`;
}
