import { ActuatorRuntime } from "./actuator-runtime.mjs";
import { ALL_OBJECT_MAP, LIVE_CONFIG } from "./live-config.mjs";
import { LivePollingClient } from "./live-client.mjs";
import { updateLivePanel } from "./live-panel.mjs";
import { LiveState } from "./live-state.mjs";

export function createLiveViewerIntegration({
  scene,
  panelRoot,
  sceneRegistry = null,
  warn = console.warn,
  onStateChange = () => {},
} = {}) {
  const state = new LiveState({ staleAfterMs: LIVE_CONFIG.staleAfterMs });
  const actuators = new ActuatorRuntime({ objectMap: ALL_OBJECT_MAP, warn });
  const mappingStatus = actuators.bindScene(scene, {
    registry: sceneRegistry?.controlRegistry,
    byName: sceneRegistry?.byName,
  });
  let lastUiSignature = null;
  let lastStatus = null;
  const syncUi = (now = Date.now()) => {
    const signature = JSON.stringify([state.lastReceivedAt, state.connectionStatus(now), state.lastError]);
    if (signature === lastUiSignature) return;
    lastUiSignature = signature;
    lastStatus = state.connectionStatus(now);
    updateLivePanel(panelRoot, state, now);
    onStateChange(state, mappingStatus);
  };
  const client = new LivePollingClient({
    onSnapshot(snapshot) {
      try {
        state.acceptSnapshot(snapshot);
        actuators.setTargets(state.actuators);
      } catch (error) {
        state.markRequestFailure(error);
      }
      syncUi();
    },
    onError(error, { firstFailure }) {
      state.markRequestFailure(error);
      if (firstFailure) warn(`[digital-twin] LIVE polling failed: ${state.lastError}`);
      syncUi();
    },
  });

  return {
    state,
    mappingStatus,
    registry: actuators.registry,
    start: () => client.start(),
    stop: () => client.stop(),
    update(deltaSeconds, now = Date.now()) {
      actuators.update(deltaSeconds);
      if (state.connectionStatus(now) !== lastStatus) syncUi(now);
    },
  };
}
