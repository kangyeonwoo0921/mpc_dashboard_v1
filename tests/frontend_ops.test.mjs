import assert from "node:assert/strict";
import test from "node:test";

import { buildOpsStatus } from "../digital_twin/static/digital_twin/js/ops-status.mjs";
import { previewRequest } from "../digital_twin/static/digital_twin/js/ops-panel.mjs";
import {
  cropLightText, forecastTableRows, ghiChartPoints, ghiPointLines, nextChange, nextChangeText,
} from "../digital_twin/static/digital_twin/js/rec-common.mjs";
import { normalizeSolarPayload } from "../digital_twin/static/digital_twin/js/solar-runtime.mjs";

const times = Array.from({ length: 13 }, (_, k) => `2026-10-12T12:${String(k * 5).padStart(2, "0")}:00+09:00`);

function recommendation({ status = "ok", forecastStatus = "ok", reason = null, statusReasons = [] } = {}) {
  return {
    status, status_reasons: statusReasons, plan_times: times,
    inputs: { forecast_status: forecastStatus, forecast_reason: reason },
    forecast: { horizons: [{ horizon_min: 30, ghi_w_m2: 720 }] },
    screens: {
      shade_screen: { plan_open_percent: [100, 100, 100, 100, 100, 100, 0, 0, 0, 0, 0, 0, 0] },
      diffuse_screen: { plan_open_percent: Array(13).fill(100) },
    },
  };
}

test("status bar: one overall verdict from live, forecast and recommendation", () => {
  const live = { source: "field_collector", status: "live", receivedAt: Date.UTC(2026, 9, 12, 3, 0, 0) };
  const ok = buildOpsStatus({ live, recommendation: recommendation() });
  assert.equal(ok.overall.level, "ok");
  assert.equal(ok.items.find((i) => i.key === "live").value, "현장 수집");

  const mock = buildOpsStatus({ live: { ...live, source: "mock_dynamic" }, recommendation: recommendation() });
  assert.deepEqual([mock.overall.level, mock.overall.text], ["warn", "모의 데이터"]);

  const night = buildOpsStatus({ live, recommendation: recommendation({ status: "degraded", forecastStatus: "unavailable", reason: "night",
    statusReasons: ["forecast_unavailable"] }) });
  assert.equal(night.overall.level, "ok", "no forecast at night is expected, not a fault");

  const stale = buildOpsStatus({ live, recommendation: recommendation({ status: "degraded", forecastStatus: "unavailable", reason: "data_stale",
    statusReasons: ["forecast_unavailable"] }) });
  assert.equal(stale.overall.level, "warn");
  assert.equal(stale.items.find((i) => i.key === "forecast").value, "현장 데이터 끊김");

  const alarm = buildOpsStatus({ live: { ...live, alarm: true }, recommendation: recommendation() });
  assert.deepEqual([alarm.overall.level, alarm.items.find((i) => i.key === "alarm")?.value], ["bad", "경보 발생"]);

  const down = buildOpsStatus({ live: { status: "disconnected" }, recommendationError: true });
  assert.deepEqual([down.overall.level, down.items[0].value], ["bad", "연결 끊김"]);
});

test("60-min preview asks the radiation model for forecast GHI and planned screens", () => {
  const request = previewRequest(recommendation(), 30);
  assert.equal(request.time, times[6]);
  assert.deepEqual(request.params, { ghi: 720, ghi_source: "forecast", shade_screen_2: 0, shade_screen_1: 100 });
  const noForecast = previewRequest(recommendation(), 15);
  assert.equal(noForecast.params.ghi, null);
  assert.equal(previewRequest(recommendation(), 0), null);
});

test("next planned change and crop light text", () => {
  const p = recommendation();
  assert.deepEqual(nextChange(p.screens.shade_screen, times), { time: times[6], open: 0, verb: "펼침" });
  assert.equal(nextChange(p.screens.diffuse_screen, times), null);
  assert.equal(nextChangeText(p.screens.diffuse_screen, times), "앞으로 60분 변화 없음");
  assert.equal(cropLightText({ status: "unavailable" }), null);
  assert.ok(cropLightText({ status: "ok", current_direct_mean_W_m2: 410, recommended_direct_mean_W_m2: 120 }).includes("120"));
});

test("v1 payload: estimated direct-beam map when diffuse optics are unknown", () => {
  const payload = {
    model: "radiation_v1", timestamp: "2026-10-12T12:00:00+09:00",
    solar: { altitude_deg: 46, azimuth_deg: 180, direction_threejs: [0, 1, 0], path_threejs: [] },
    inputs: { weather: { ghi_W_m2: 650, source: "field_collector" } },
    radiation: {
      status: "parameter_missing:cover.diffuse_transmittance", sunlit_fraction: 0.9, mean_W_m2: null,
      direct_resolved_mean_W_m2: 380, direct_resolved_fraction: 0.94,
      grid: { rows: 1, cols: 3, cell_size_m: 1, origin_xy_m: [0, 0], height_m: 3, sunlit: [true, false, null],
        total_W_m2: [null, null, null], direct_W_m2: [410, 0, null] },
    },
  };
  const normalized = normalizeSolarPayload(payload);
  assert.equal(normalized.grid.mode, "direct");
  assert.deepEqual(normalized.grid.values, [410, 0, null]);
  assert.equal(normalized.summary.directMean, 380);
  payload.solar.altitude_deg = -5;
  assert.equal(normalizeSolarPayload(payload).grid.mode, "sunlit");
});

test("GHI chart points and the tooltip text for a selected point", () => {
  const payload = {
    settings: { shade_threshold_w_m2: 700 },
    plan_times: times,
    screens: { shade_screen: { plan_open_percent: [100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] } },
    forecast: {
      recent_observations: [{ time: "2026-10-12T11:55:00+09:00", ghi_w_m2: 640, status: "observed" },
        { time: "2026-10-12T11:50:00+09:00", ghi_w_m2: null, status: "missing" }],
      horizons: [
        { horizon_min: 5, target_time: "2026-10-12T12:05:00+09:00", ghi_w_m2: 690.4, ghi_clear_w_m2: 760, method: "xgb_expanding" },
        { horizon_min: 10, target_time: "2026-10-12T12:10:00.000+09:00", ghi_w_m2: 712, ghi_clear_w_m2: 761, method: "xgb_expanding" },
        { horizon_min: 15, target_time: "2026-10-12T12:15:00+09:00", ghi_w_m2: null, ghi_clear_w_m2: 762, method: null },
      ],
    },
  };
  const points = ghiChartPoints(payload);
  assert.deepEqual(points.map((p) => p.kind), ["observed", "observed", "forecast", "forecast", "forecast"]);
  assert.equal(points[1].ghi, null, "missing stays null, not zero");

  const forecastLines = ghiPointLines(points[2], 700);
  assert.ok(forecastLines[0].includes("예측 (+5분)"));
  assert.ok(forecastLines.includes("일사 690 W/m²"));
  assert.ok(forecastLines.includes("차광 기준(700)까지 10"));
  assert.ok(forecastLines.includes("맑은 날 기준 760 W/m²"));
  assert.ok(forecastLines.includes("예측 방법: 모델 (XGBoost)"));
  assert.ok(ghiPointLines(points[3], 700).includes("차광 기준(700) 이상 +12"));
  assert.ok(ghiPointLines(points[0], 700)[0].includes("실측 (5분 평균)"));
  assert.ok(ghiPointLines(points[4], 700).includes("예측값 없음"));

  const rows = forecastTableRows(payload);
  assert.deepEqual(rows.map((r) => [r.horizonMin, r.overThreshold, r.shadeOpen]), [[5, false, 100], [10, true, 0], [15, null, 0]],
    "plan matched by timestamp even when the ISO text differs");
});

test("low sun is an expected forecast pause; crop reasons are words", async () => {
  const { cropUnavailableText } = await import("../digital_twin/static/digital_twin/js/rec-common.mjs");
  const live = { source: "field_collector", status: "live", receivedAt: 0 };
  const lowSun = buildOpsStatus({ live, recommendation: recommendation({ status: "degraded", forecastStatus: "unavailable",
    reason: "low_sun", statusReasons: ["forecast_unavailable"] }) });
  assert.equal(lowSun.overall.level, "ok");
  assert.equal(cropUnavailableText({ status: "unavailable", reason: "out_of_range:zenith_ge_85" }), "계산 불가 (해가 너무 낮음)");
  assert.equal(cropUnavailableText({ status: "unavailable", reason: "model_error:ValueError" }), "계산 불가 (모델 오류)");
});
