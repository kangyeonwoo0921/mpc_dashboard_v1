import { SPAN_IDS } from "./viewer-config.mjs";

export const GREENHOUSE_SELECTION = Object.freeze({
  level: "greenhouse",
  spanId: null,
  assetId: null,
  assetType: null,
});

export function normalizeSpanId(value) {
  if (typeof value === "number" && Number.isInteger(value)) value = `S${String(value).padStart(2, "0")}`;
  if (typeof value === "string") {
    const match = value.toUpperCase().match(/^S0?([1-4])$/);
    if (match) return `S0${match[1]}`;
  }
  return null;
}

function freezeState(state) {
  return Object.freeze({
    level: state.level,
    spanId: state.spanId ?? null,
    assetId: state.assetId ?? null,
    assetType: state.assetType ?? null,
  });
}

export class SelectionRuntime {
  constructor() {
    this.state = GREENHOUSE_SELECTION;
    this.listeners = new Set();
  }

  subscribe(listener, { emitCurrent = true } = {}) {
    this.listeners.add(listener);
    if (emitCurrent) listener(this.state, null);
    return () => this.listeners.delete(listener);
  }

  selectGreenhouse() {
    return this.#set(GREENHOUSE_SELECTION);
  }

  selectSpan(spanId) {
    const normalized = normalizeSpanId(spanId);
    if (!normalized || !SPAN_IDS.includes(normalized)) throw new RangeError(`Unknown span: ${spanId}`);
    return this.#set({ level: "span", spanId: normalized, assetId: null, assetType: null });
  }

  selectAsset(assetEntry) {
    if (!assetEntry?.id || !assetEntry?.type) throw new TypeError("A registered asset entry is required");
    return this.#set({
      level: "asset",
      spanId: normalizeSpanId(assetEntry.spanId),
      assetId: assetEntry.id,
      assetType: assetEntry.type,
    });
  }

  back() {
    if (this.state.level === "asset" && this.state.spanId) return this.selectSpan(this.state.spanId);
    return this.selectGreenhouse();
  }

  #set(next) {
    const previous = this.state;
    const state = freezeState(next);
    if (JSON.stringify(previous) === JSON.stringify(state)) return state;
    this.state = state;
    this.listeners.forEach((listener) => listener(state, previous));
    return state;
  }
}
