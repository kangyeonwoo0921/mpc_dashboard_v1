import { LIVE_CONFIG } from "./live-config.mjs";

export class LivePollingClient {
  constructor({
    config = LIVE_CONFIG,
    fetchImpl = globalThis.fetch?.bind(globalThis),
    onSnapshot = () => {},
    onError = () => {},
    scheduler = globalThis,
  } = {}) {
    if (!fetchImpl) throw new Error("fetch is required for LIVE polling");
    this.config = config;
    this.fetchImpl = fetchImpl;
    this.onSnapshot = onSnapshot;
    this.onError = onError;
    this.scheduler = scheduler;
    this.running = false;
    this.timer = null;
    this.failureReported = false;
  }

  start() {
    if (this.running) return;
    this.running = true;
    void this.#poll();
  }

  stop() {
    this.running = false;
    if (this.timer !== null) this.scheduler.clearTimeout(this.timer);
    this.timer = null;
  }

  async pollOnce() {
    const response = await this.fetchImpl(this.config.endpoint, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`LIVE API returned HTTP ${response.status}`);
    return response.json();
  }

  async #poll() {
    try {
      const snapshot = await this.pollOnce();
      this.failureReported = false;
      this.onSnapshot(snapshot);
    } catch (error) {
      this.onError(error, { firstFailure: !this.failureReported });
      this.failureReported = true;
    } finally {
      if (this.running) {
        this.timer = this.scheduler.setTimeout(() => void this.#poll(), this.config.pollIntervalMs);
      }
    }
  }
}
