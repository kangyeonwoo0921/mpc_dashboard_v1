// Operations panel inside the 3D viewer: GHI now + forecast, screen recommendation, crop-plane
// direct beam estimate, and a "next 60 min" preview that drives the sun / light map.
// Data: GET /api/recommendation/screens/ (recommendation only; nothing is sent to the field).

import { cueChange } from "./motion-runtime.mjs";
import { buildOpsStatus, renderOpsStatus } from "./ops-status.mjs";
import { SCREEN_COLOR, cropLightText, cropUnavailableText, el, fmtTime, fmtW, moveText, renderGhiChart } from "./rec-common.mjs";

export const OPS_ENDPOINT = "/api/recommendation/screens/";
export const OPS_POLL_MS = 60_000;
export const PREVIEW_OFFSETS = Object.freeze([0, 15, 30, 45, 60]);

/** Inputs for the radiation API at +offset minutes: forecast GHI and the planned screen positions. */
export function previewRequest(payload, offsetMin) {
  if (!payload || !offsetMin) return null;
  const index = offsetMin / 5;
  const time = payload.plan_times?.[index];
  if (!time) return null;
  const horizon = (payload.forecast?.horizons ?? []).find((h) => h.horizon_min === offsetMin);
  const ghi = horizon?.ghi_w_m2 ?? null;
  const shade = payload.screens.shade_screen.plan_open_percent[index];
  const diffuse = payload.screens.diffuse_screen.plan_open_percent[index];
  return {
    time,
    params: { ghi, ghi_source: ghi === null ? null : "forecast", shade_screen_2: shade, shade_screen_1: diffuse },
    label: `+${offsetMin}분 미리보기 (${fmtTime(time)})`,
    detail: `예측 일사 ${ghi === null ? "없음" : `${fmtW(ghi)} W/m²`} · 추천 위치: 차광 열림 ${fmtW(shade)}% · 산광 열림 ${fmtW(diffuse)}%`,
  };
}

export class OpsPanel {
  constructor({ root, statusRoot, onPreview = () => {}, fetchImpl = globalThis.fetch?.bind(globalThis) }) {
    this.root = root;
    this.statusRoot = statusRoot;
    this.onPreview = onPreview;
    this.fetchImpl = fetchImpl;
    this.payload = null;
    this.error = false;
    this.live = null;
    this.previewOffset = 0;
    this.timer = null;
  }

  start() {
    this.refresh();
    this.timer = setInterval(() => this.refresh(), OPS_POLL_MS);
  }

  async refresh() {
    try {
      const response = await this.fetchImpl(OPS_ENDPOINT, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      this.payload = await response.json();
      this.error = false;
    } catch {
      this.error = true;
    }
    this.render();
    if (this.previewOffset > 0) this.#emitPreview();      // keep a running preview on the latest forecast
  }

  setLive(live) {
    this.live = live;
    this.#renderStatus();
    this.#renderNowGhi();
  }

  /** The 2 s LIVE value is newer than the 60 s recommendation snapshot, so "지금" follows LIVE when connected. */
  #nowGhi() {
    if (this.live?.status === "live" && this.live.ghi !== undefined) return this.live.ghi;
    return this.payload?.inputs?.solar_w_m2 ?? null;
  }

  #renderNowGhi() {
    const node = this.root.querySelector("[data-ops-now]");
    if (!node) return;
    const text = fmtW(this.#nowGhi());
    if (node.textContent !== text) {
      node.textContent = text;
      cueChange(node);
    }
  }

  /** Mark the active preview without emitting: 0 = live ("지금"), -1 = the day slider is in use. */
  markPreview(offset) {
    this.previewOffset = offset;
    this.#syncPreviewButtons();
  }

  #renderStatus() {
    renderOpsStatus(this.statusRoot, buildOpsStatus({ live: this.live, recommendation: this.payload, recommendationError: this.error }));
  }

  #emitPreview() {
    const request = this.previewOffset > 0 ? previewRequest(this.payload, this.previewOffset) : null;
    this.onPreview(request);
  }

  #syncPreviewButtons() {
    this.root.querySelectorAll("[data-preview]").forEach((button) => {
      button.setAttribute("aria-pressed", String(Number(button.dataset.preview) === this.previewOffset));
    });
  }

  render() {
    this.#renderStatus();
    const body = this.root.querySelector("[data-ops-body]");
    if (!body) return;
    if (this.error && !this.payload) {
      body.replaceChildren(el("p", { class: "ops-message", text: "추천 정보를 불러오지 못했습니다." }));
      return;
    }
    if (!this.payload) return;
    const p = this.payload;
    const hz = p.forecast?.horizons ?? [];
    const at = (minutes) => hz.find((h) => h.horizon_min === minutes)?.ghi_w_m2 ?? null;
    const nodes = [];

    nodes.push(el("section", { class: "ops-block" },
      el("h3", { text: "일사 (외부 센서 기준)" }),
      el("div", { class: "ops-ghi" },
        el("div", {}, el("small", { text: "지금" }), el("b", { "data-ops-now": true, text: fmtW(this.#nowGhi()) }), el("span", { text: " W/m²" })),
        ...[15, 30, 60].map((m) => el("div", {}, el("small", { text: `+${m}분` }), el("b", { text: fmtW(at(m)) })))),
      el("div", { class: "ops-chart", "data-ops-chart": true })));

    const screens = el("section", { class: "ops-block" }, el("h3", { text: "스크린 추천" }));
    for (const [key, screen] of Object.entries(p.screens)) {
      screens.append(el("div", { class: "ops-screen" },
        el("div", { class: "ops-screen-head" },
          el("i", { class: "ops-dot", style: `background:${SCREEN_COLOR[key]}` }),
          el("strong", { text: screen.label }),
          el("span", { class: `ops-action ${screen.action}`, text: screen.action_label })),
        el("div", { class: "ops-line", text: moveText(screen) })));   // next change and reasons: 추천 상세
    }
    nodes.push(screens);

    const crop = p.crop_light;
    const cropText = cropLightText(crop);
    nodes.push(el("section", { class: "ops-block" },
      el("h3", { text: "작물면 빛 (추정)" }),
      el("div", { class: "ops-line", text: cropText ?? cropUnavailableText(crop) })));   // method notes: 추천 상세

    nodes.push(el("section", { class: "ops-block" },
      el("h3", { text: "3D 미리보기 (태양·일조 지도)" }),
      el("div", { class: "ops-preview", role: "group", "aria-label": "미리보기 시각" },
        PREVIEW_OFFSETS.map((m) => el("button", { type: "button", "data-preview": m, "aria-pressed": String(m === this.previewOffset),
          text: m === 0 ? "지금" : `+${m}분` })))));

    nodes.push(el("a", { class: "ops-link", href: "/recommendation/", text: "추천 상세 · 설정 →" }));
    const previous = body.querySelector("[data-ops-chart]")?.dataset ?? {};   // keep a pinned point across refreshes
    const oldValues = [...body.querySelectorAll(".ops-ghi b")].map((b) => b.textContent);
    body.replaceChildren(...nodes);
    body.querySelectorAll(".ops-ghi b").forEach((b, i) => {
      if (oldValues.length && i > 0 && oldValues[i] !== b.textContent) cueChange(b);   // forecast values changed
    });
    const chart = body.querySelector("[data-ops-chart]");
    if (previous.pinned === "true") Object.assign(chart.dataset, { pinned: "true", selected: previous.selected });
    renderGhiChart(chart, p, { compact: true });
    body.querySelectorAll("[data-preview]").forEach((button) => {
      button.addEventListener("click", () => {
        this.previewOffset = Number(button.dataset.preview);
        this.#syncPreviewButtons();
        this.#emitPreview();
      });
    });
    const updated = this.root.querySelector("[data-ops-updated]");
    if (updated) updated.textContent = `${fmtTime(p.generated_at)} 기준`;
  }
}
