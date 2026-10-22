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

/**
 * Every selectable point of the GHI chart, oldest first: measured 5-min bins of the last hour, then the
 * forecast horizons. ghi / clear stay null when missing (never zero).
 */
export function ghiChartPoints(payload) {
  const fc = payload.forecast ?? {};
  const observed = (fc.recent_observations ?? []).map((o) => ({
    time: o.time, kind: "observed", ghi: o.ghi_w_m2 ?? null, clear: null, horizonMin: null, method: null,
  }));
  const forecast = (fc.horizons ?? []).map((h) => ({
    time: h.target_time, kind: "forecast", ghi: h.ghi_w_m2 ?? null, clear: h.ghi_clear_w_m2 ?? null,
    horizonMin: h.horizon_min ?? null, method: h.method ?? null,
  }));
  return [...observed, ...forecast].filter((point) => point.time);
}

function methodLabel(method) {
  if (!method) return null;
  if (method.startsWith("xgb")) return "모델 (XGBoost)";
  if (method.includes("cc") || method.includes("reference") || method.includes("clim")) return "기준 방법";
  return method;
}

/** Text lines for one selected point (tooltip and tests). */
export function ghiPointLines(point, threshold) {
  const head = point.kind === "forecast"
    ? `${fmtTime(point.time)} · 예측${point.horizonMin ? ` (+${point.horizonMin}분)` : ""}`
    : `${fmtTime(point.time)} · 실측 (5분 평균)`;
  const lines = [head];
  if (point.ghi === null) {
    lines.push(point.kind === "forecast" ? "예측값 없음" : "측정값 없음");
  } else {
    lines.push(`일사 ${fmtW(point.ghi)} W/m²`);
    const gap = Math.round(point.ghi - threshold);
    lines.push(gap >= 0 ? `차광 기준(${threshold}) 이상 +${gap}` : `차광 기준(${threshold})까지 ${-gap}`);
  }
  if (point.clear !== null) lines.push(`맑은 날 기준 ${fmtW(point.clear)} W/m²`);
  const method = methodLabel(point.method);
  if (method) lines.push(`예측 방법: ${method}`);
  return lines;
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
  const font = 12;                                  // --fs-xs
  const W = host.clientWidth || (compact ? 280 : 800), H = host.clientHeight || (compact ? 120 : 260);
  const L = compact ? 34 : 46, R = 8, T = 10, B = compact ? 18 : 26;
  const x = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
  const y = (v) => T + (1 - v / ymax) * (H - T - B);
  const { svg, add } = svgHost(host, W, H);
  const step = compact ? 400 : 200;
  for (let v = 0; v <= ymax; v += step) {
    add("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#1f2f4a", "stroke-width": 1 });
    add("text", { x: L - 5, y: y(v) + 4, "text-anchor": "end", fill: "#8b9ab0", "font-size": font }, v);
  }
  const tick = compact ? 1_800_000 : 900_000;
  for (let t = new Date(Math.ceil(t0 / tick) * tick); t <= t1; t = new Date(t.getTime() + tick)) {
    // the last label sits at the right edge: anchor it at its end so it is not clipped
    add("text", { x: x(t), y: H - 5, "text-anchor": x(t) > W - R - 20 ? "end" : "middle", fill: "#8b9ab0", "font-size": font }, fmtTime(t.toISOString()));
  }
  add("line", { x1: x(issue), x2: x(issue), y1: T, y2: H - B, stroke: "#8a6a4c", "stroke-dasharray": "3 3" });
  add("text", { x: x(issue) + 4, y: T + 9, fill: "#a8b5c7", "font-size": font }, "지금");
  const path = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  if (clear.length) add("path", { d: path(clear), fill: "none", stroke: "#7f8f97", "stroke-width": 1.4, "stroke-dasharray": "5 4" });
  add("line", { x1: L, x2: W - R, y1: y(threshold), y2: y(threshold), stroke: "#d4aa5c", "stroke-width": 1.4 });
  if (!compact) add("text", { x: W - R - 2, y: y(threshold) - 4, "text-anchor": "end", fill: "#d4aa5c", "font-size": font }, `차광 기준 ${threshold}`);
  if (obs.length) add("path", { d: path(obs), fill: "none", stroke: "#e6edf0", "stroke-width": 2 });
  if (pred.length) {
    const joined = obs.length ? [obs[obs.length - 1], ...pred] : pred;
    add("path", { d: path(joined), fill: "none", stroke: "#5b9bd5", "stroke-width": 2.5 });
  }
  if (!obs.length && !pred.length) {
    add("text", { x: (L + W - R) / 2, y: (T + H - B) / 2, "text-anchor": "middle", fill: "#a8b5c7", "font-size": compact ? 12 : 14 },
      "표시할 일사 데이터가 없습니다");
  }
  // Selectable points: small dots on the forecast, a cursor and a tooltip on hover / click / arrow keys.
  const points = ghiChartPoints(payload).filter((point) => {
    const t = new Date(point.time);
    return t >= t0 && t <= t1;
  });
  for (const point of points) {
    if (point.kind === "forecast" && point.ghi !== null) {
      add("circle", { cx: x(new Date(point.time)), cy: y(point.ghi), r: compact ? 2 : 2.5, fill: "#5b9bd5" });
    }
  }
  const cursor = add("line", { y1: T, y2: H - B, stroke: "#cfd8dc", "stroke-width": 1, visibility: "hidden" });
  const marker = add("circle", { r: compact ? 4 : 5, fill: "#11191f", "stroke-width": 2, visibility: "hidden" });
  const tip = el("div", { class: "chart-tip", role: "status", hidden: true });
  host.classList.add("chart-interactive");
  host.replaceChildren(svg, tip);
  if (!points.length) return;

  svg.setAttribute("tabindex", "0");
  svg.setAttribute("aria-label", "일사 그래프: 마우스를 올리거나 누르면 값이 보입니다. 좌우 화살표로 이동, Esc로 닫기");
  const nearest = (clientX) => {
    const box = svg.getBoundingClientRect();
    const px = ((clientX - box.left) / Math.max(box.width, 1)) * W;
    let best = 0;
    points.forEach((point, i) => {
      if (Math.abs(x(new Date(point.time)) - px) < Math.abs(x(new Date(points[best].time)) - px)) best = i;
    });
    return best;
  };
  const show = (index) => {
    const point = points[index];
    const px = x(new Date(point.time));
    cursor.setAttribute("x1", px);
    cursor.setAttribute("x2", px);
    cursor.setAttribute("visibility", "visible");
    if (point.ghi !== null) {
      marker.setAttribute("cx", px);
      marker.setAttribute("cy", y(point.ghi));
      marker.setAttribute("stroke", point.kind === "forecast" ? "#5b9bd5" : "#e6edf0");
      marker.setAttribute("visibility", "visible");
    } else {
      marker.setAttribute("visibility", "hidden");
    }
    tip.replaceChildren(...ghiPointLines(point, threshold).map((line, i) => el(i ? "span" : "strong", { text: line })));
    tip.hidden = false;
    const share = px / W;
    tip.style.left = `${share * 100}%`;
    tip.style.transform = share > 0.6 ? "translateX(calc(-100% - 10px))" : "translateX(10px)";
    host.dataset.selected = point.time;
  };
  const hide = () => {
    cursor.setAttribute("visibility", "hidden");
    marker.setAttribute("visibility", "hidden");
    tip.hidden = true;
  };
  let pinned = host.dataset.pinned === "true" ? points.findIndex((p) => p.time === host.dataset.selected) : -1;
  if (pinned >= 0) show(pinned);
  else host.dataset.pinned = "false";
  svg.addEventListener("pointermove", (event) => { if (pinned < 0) show(nearest(event.clientX)); });
  svg.addEventListener("pointerleave", () => { if (pinned < 0) hide(); });
  svg.addEventListener("click", (event) => {
    const index = nearest(event.clientX);
    pinned = pinned === index ? -1 : index;              // clicking the pinned point again releases it
    host.dataset.pinned = String(pinned >= 0);
    show(index);
  });
  svg.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      pinned = -1;
      host.dataset.pinned = "false";
      hide();
      return;
    }
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const start = pinned >= 0 ? pinned : points.findIndex((p) => p.kind === "forecast");
    pinned = Math.min(points.length - 1, Math.max(0, (start < 0 ? 0 : start) + (event.key === "ArrowRight" ? 1 : -1)));
    host.dataset.pinned = "true";
    show(pinned);
  });
}

/** Rows for the forecast table: one per horizon, with the planned shade-screen position at that time. */
export function forecastTableRows(payload) {
  const threshold = Number(payload.settings.shade_threshold_w_m2);
  const plan = payload.screens?.shade_screen?.plan_open_percent ?? [];
  return (payload.forecast?.horizons ?? []).map((h) => {
    const index = (payload.plan_times ?? []).findIndex((t) => Date.parse(t) === Date.parse(h.target_time));
    return {
      time: h.target_time, horizonMin: h.horizon_min, ghi: h.ghi_w_m2 ?? null, clear: h.ghi_clear_w_m2 ?? null,
      overThreshold: h.ghi_w_m2 === null || h.ghi_w_m2 === undefined ? null : h.ghi_w_m2 >= threshold,
      shadeOpen: index >= 0 ? plan[index] ?? null : null,
    };
  });
}

/** 60-min recommended open % per screen as step lines (top = 걷힘 100 %, bottom = 펼침 0 %). */
export function renderPlanChart(host, payload) {
  const times = payload.plan_times.map((t) => new Date(t));
  // same size and margins as the full GHI chart, so both plot areas line up
  const W = host.clientWidth || 800, H = host.clientHeight || 260, L = 46, R = 8, T = 10, B = 26;
  const t0 = times[0], t1 = times[times.length - 1];
  const x = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
  const y = (v) => T + (1 - v / 100) * (H - T - B);
  const { svg, add } = svgHost(host, W, H);
  for (const v of [100, 50, 0]) {
    add("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#1f2f4a", "stroke-width": 1 });
    add("text", { x: L - 5, y: y(v) + 4, "text-anchor": "end", fill: "#8b9ab0", "font-size": 12 }, v);
  }
  add("text", { x: L - 5, y: y(100) + 18, "text-anchor": "end", fill: "#8b9ab0", "font-size": 12 }, "걷힘");
  add("text", { x: L - 5, y: y(0) - 10, "text-anchor": "end", fill: "#8b9ab0", "font-size": 12 }, "펼침");
  times.forEach((t, i) => {
    if (i % 3 === 0) add("text", { x: x(t), y: H - 5, "text-anchor": x(t) > W - R - 20 ? "end" : "middle", fill: "#8b9ab0", "font-size": 12 }, fmtTime(t.toISOString()));
  });
  const entries = Object.entries(payload.screens);
  for (const [key, screen] of entries) {
    const plan = screen.plan_open_percent;
    let d = "";
    plan.forEach((v, i) => {
      if (v === null || v === undefined) return;
      const px = x(times[i]);
      const nx = i + 1 < times.length ? x(times[i + 1]) : px;
      d += `${d ? "L" : "M"}${px.toFixed(1)},${y(v).toFixed(1)} L${nx.toFixed(1)},${y(v).toFixed(1)} `;
    });
    if (d) add("path", { d, fill: "none", stroke: SCREEN_COLOR[key] ?? "#ccc", "stroke-width": 2.5 });
  }
  // Current positions: filled marker + "현재 n%" tag; markers/tags that would overlap are set side by side /
  // stacked; a dotted arrow shows the move when the recommendation differs from the current position.
  const current = entries
    .filter(([, screen]) => typeof screen.current_open_percent === "number")
    .map(([key, screen]) => ({ key, color: SCREEN_COLOR[key] ?? "#ccc", value: screen.current_open_percent,
                               target: screen.plan_open_percent?.[0] }))
    .sort((a, b) => b.value - a.value);
  const tagHeight = 18;
  let lastTagY = -Infinity;
  current.forEach((item, i) => {
    const overlapping = i > 0 && Math.abs(y(item.value) - y(current[i - 1].value)) < 12;
    const mx = L + 9 + (overlapping ? 14 : 0);                         // clear of the axis labels
    const my = y(item.value);
    if (typeof item.target === "number" && Math.abs(item.target - item.value) > MOVE_TOLERANCE) {
      const ty = y(item.target);
      const dir = ty > my ? 1 : -1;
      add("line", { x1: mx, x2: mx, y1: my + dir * 7, y2: ty - dir * 7, stroke: item.color, "stroke-width": 1.5, "stroke-dasharray": "3 3" });
      add("path", { d: `M${mx - 4},${ty - dir * 9} L${mx + 4},${ty - dir * 9} L${mx},${ty - dir * 3} Z`, fill: item.color });
    }
    add("circle", { cx: mx, cy: my, r: 6, fill: item.color, stroke: "#0e1f38", "stroke-width": 2 });
    let tagY = Math.max(my, lastTagY + tagHeight + 2);                 // stack tags that would overlap
    tagY = Math.min(Math.max(tagY, T + tagHeight / 2), H - B - tagHeight / 2);
    lastTagY = tagY;
    const text = `현재 ${fmtPct(item.value)}%`;
    const tx = L + 36;
    // approximate text width at 12 px: Hangul ~12 px, digits / symbols ~7.5 px (the svg is not in the DOM yet)
    const width = [...text].reduce((w, ch) => w + (/[ㄱ-힝]/.test(ch) ? 12 : ch === " " ? 3.5 : 7.5), 0);
    add("rect", { x: tx - 7, y: tagY - tagHeight / 2, width: width + 14, height: tagHeight, rx: 9,
                  fill: "#0e1f38", stroke: item.color, "stroke-width": 1 });
    add("text", { x: tx, y: tagY + 4, fill: item.color, "font-size": 12, "font-weight": 600 }, text);
  });
  host.replaceChildren(svg);
}

const CROP_REASON = Object.freeze({
  no_ghi: "외부 일사 없음", night: "밤", "out_of_range:zenith_ge_85": "해가 너무 낮음", missing_input: "외부 일사 없음",
});

/** Why the crop-plane estimate is missing, in words. */
export function cropUnavailableText(crop) {
  const reason = crop?.reason;
  if (reason && reason.startsWith("model_error")) return "계산 불가 (모델 오류)";
  return `계산 불가 (${CROP_REASON[reason] ?? "정보 없음"})`;
}

/** Crop-plane direct beam line, or null when the estimate is not available. */
export function cropLightText(crop) {
  if (!crop || crop.status !== "ok") return null;
  const now = `${fmtW(crop.current_direct_mean_W_m2)} W/m²`;
  if (crop.recommended_direct_mean_W_m2 === crop.current_direct_mean_W_m2) return `작물면 직달광 ${now} (추천대로 해도 같음)`;
  return `작물면 직달광 ${now} → 추천대로 하면 ${fmtW(crop.recommended_direct_mean_W_m2)} W/m²`;
}
