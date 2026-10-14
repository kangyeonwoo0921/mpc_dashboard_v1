// One status bar for the 3D viewer and the recommendation page: "can I trust what I see now?"
// Inputs: the LIVE connection (viewer: 2 s polling; recommendation page: recommendation inputs)
// and the screen recommendation payload (forecast status, recommendation status).
// All text is set with textContent.

export const FORECAST_REASON = Object.freeze({
  data_stale: "현장 데이터 끊김", night: "밤", low_sun: "태양고도 20° 미만", ghi_not_observed: "일사 측정 없음",
  forecast_too_old: "예측 갱신 멈춤", no_forecast_file: "예측 파일 없음", forecast_not_configured: "예측 미연결",
  issue_bin_not_processed: "처리 대기",
});

const LEVEL_RANK = { ok: 0, info: 0, warn: 2, bad: 3 };   // "info" items never lower the overall verdict

export function sourceText(source) {
  if (!source) return "—";
  if (source.startsWith("mock")) return "모의 데이터";
  if (source === "field_collector") return "현장 수집";
  return source;
}

function clock(ms) {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  return new Date(ms).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

/**
 * live: { source, status: "live" | "stale" | "disconnected", receivedAt (ms) }
 * recommendation: /api/recommendation/screens/ payload, or null while loading / on error.
 */
export function buildOpsStatus({ live, recommendation = null, recommendationError = false }) {
  const items = [];
  const mock = live?.source?.startsWith("mock");
  const liveLevel = live?.status === "live" ? (mock ? "warn" : "ok") : live?.status === "stale" ? "warn" : "bad";
  const liveValue = live?.status === "disconnected" || !live?.status
    ? "연결 끊김"
    : `${sourceText(live.source)}${live.status === "stale" ? " · 지연" : ""}`;
  items.push({ key: "live", label: "데이터", value: liveValue, level: liveLevel,
    title: mock ? "현장 장치가 아닌 시험용 모의 데이터입니다" : "현장 수집기에서 받은 값입니다" });
  items.push({ key: "received", label: "수신", value: clock(live?.receivedAt), level: "info" });

  if (recommendationError) {
    items.push({ key: "forecast", label: "일사 예측", value: "불러오기 실패", level: "bad" });
    items.push({ key: "recommendation", label: "추천", value: "불러오기 실패", level: "bad" });
  } else if (recommendation) {
    const inp = recommendation.inputs ?? {};
    const forecastOk = inp.forecast_status === "ok";
    items.push({ key: "forecast", label: "일사 예측",
      value: forecastOk ? "정상" : FORECAST_REASON[inp.forecast_reason] ?? inp.forecast_reason ?? "없음",
      level: forecastOk || inp.forecast_reason === "night" ? "ok" : "warn" });
    // At night the forecast is off by design; that alone does not degrade the recommendation.
    const reasons = recommendation.status_reasons ?? [];
    const nightOnly = inp.forecast_reason === "night" && reasons.every((r) => r.startsWith("forecast_"));
    const ok = recommendation.status === "ok" || nightOnly;
    items.push({ key: "recommendation", label: "추천",
      value: ok ? "정상" : recommendation.status === "degraded" ? "일부 정보로 판단" : "판단 불가",
      level: ok ? "ok" : recommendation.status === "degraded" ? "warn" : "bad" });
  } else {
    items.push({ key: "forecast", label: "일사 예측", value: "불러오는 중", level: "info" });
    items.push({ key: "recommendation", label: "추천", value: "불러오는 중", level: "info" });
  }
  const worst = items.reduce((acc, item) => (LEVEL_RANK[item.level] > LEVEL_RANK[acc] ? item.level : acc), "ok");
  const overall = worst === "ok"
    ? { level: "ok", text: "정상" }
    : worst === "bad"
      ? { level: "bad", text: "확인 필요" }
      : { level: "warn", text: mock ? "모의 데이터" : "일부 제한" };
  return { overall, items, mode: "추천만 · 장치 제어 안 함" };
}

export function renderOpsStatus(root, model) {
  if (!root) return;
  const chip = (cls, label, value, title) => {
    const node = document.createElement("span");
    node.className = cls;
    if (title) node.title = title;
    if (label) {
      const name = document.createElement("small");
      name.textContent = label;
      node.append(name);
    }
    const strong = document.createElement("b");
    strong.textContent = value;
    node.append(strong);
    return node;
  };
  const nodes = [chip(`ops-chip ops-overall ops-${model.overall.level}`, "상태", model.overall.text)];
  for (const item of model.items) nodes.push(chip(`ops-chip ops-${item.level}`, item.label, item.value, item.title));
  nodes.push(chip("ops-chip ops-mode", null, model.mode, "이 화면은 추천만 보여 주며 현장 장치를 움직이지 않습니다"));
  root.replaceChildren(...nodes);
}
