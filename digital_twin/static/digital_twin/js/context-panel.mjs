import { displayTitle } from "./interaction-runtime.mjs";
import { formatValue, statusBadge } from "./live-panel.mjs";
import { mappedAssetContext } from "./live-config.mjs";

export const HISTORY_EMPTY_MESSAGE = "History is not available in the current mock-only phase. Historical logging will be added with the live data bridge.";

function percent(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "—";
}

function sourceLabel(state) {
  if (!state?.source) return "—";
  return state.source.startsWith("mock") ? "MOCK" : state.source.toUpperCase();
}

function updatedLabel(state) {
  return state?.lastReceivedAt == null ? "—" : new Date(state.lastReceivedAt).toLocaleTimeString();
}

function connectionLabel(state, now = Date.now()) {
  return typeof state?.connectionStatus === "function" ? statusBadge(state.connectionStatus(now)) : "DISCONNECTED";
}

function spanActuatorRows(spanAssets, state) {
  return [["roof_vent", "Roof Vent"], ["shade_screen", "Shade Screen"],
    ["diffuse_screen", "Diffuse Screen"], ["side_curtain", "Side Curtain"]].map(([type, label]) => {
    const entry = spanAssets.find((asset) => asset.type === type);
    const context = mappedAssetContext(entry, state);
    return { label, value: percent(context.openingPercent),
      note: context.channel ? context.channel + " · " + context.mappingStatus : "Not span-mapped" };
  });
}

function assetDetails(entry) {
  if (!entry) return [];
  const metadata = entry.owner.userData ?? {};
  const fields = [
    ["Name", entry.owner.name],
    ["Asset type", metadata.asset_type],
    ["Span index", metadata.span_index],
    ["Control variable", metadata.control_variable],
    ["Visual opening", typeof metadata.opening_percent === "number" ? `${metadata.opening_percent.toFixed(1)}%` : null],
    ["Source confidence", metadata.source_confidence],
    ["Geometry confidence", metadata.geometry_confidence],
    ["Position confidence", metadata.position_confidence],
    ["Verified position", typeof metadata.verified_position === "boolean" ? String(metadata.verified_position) : null],
    ["PLC tag verified", typeof metadata.plc_tag_verified === "boolean" ? String(metadata.plc_tag_verified) : null],
  ];
  return fields.filter(([, value]) => value !== null && value !== undefined && value !== "").map(([label, value]) => ({ label, value: String(value) }));
}

export function buildContextModel({ selection, liveState, assetEntry = null, assetContext = {}, spanAssets = [], now = Date.now() }) {
  const connection = connectionLabel(liveState, now);
  const source = sourceLabel(liveState);
  const updated = updatedLabel(liveState);
  if (selection.level === "greenhouse") {
    return {
      title: "GREENHOUSE OVERVIEW",
      breadcrumb: [{ level: "greenhouse", label: "Greenhouse" }],
      sections: [
        { title: "Environment", rows: [
          { label: "Indoor Temperature", value: formatValue(liveState?.environment?.indoor_temperature_c, "°C", 1) },
          { label: "Relative Humidity", value: formatValue(liveState?.environment?.indoor_rh_pct, "%", 1) },
          { label: "Solar Radiation", value: formatValue(liveState?.environment?.solar_w_m2, "W/m²", 0) },
        ] },
        { title: "System", rows: [
          { label: "Status", value: connection },
          { label: "Data Source", value: source },
          { label: "Last Update", value: updated },
          { label: "Alerts", value: "Not configured" },
        ] },
      ],
      details: [],
      detailsMessage: "Select a span or asset to inspect spatial metadata.",
      source,
      connection,
      updated,
      liveMessage: liveState?.lastReceivedAt == null ? "Waiting for data…" : null,
    };
  }

  if (selection.level === "span") {
    const label = `Span ${selection.spanId.slice(1)}`;
    return {
      title: label.toUpperCase(),
      breadcrumb: [
        { level: "greenhouse", label: "Greenhouse" },
        { level: "span", spanId: selection.spanId, label },
      ],
      sections: [
        { title: "Actuators", rows: spanActuatorRows(spanAssets, liveState) },
        { title: "Representative Environment", note: "House-level sensor · Not span-specific", rows: [
          { label: "Indoor Temperature", value: formatValue(liveState?.environment?.indoor_temperature_c, "°C", 1) },
          { label: "Relative Humidity", value: formatValue(liveState?.environment?.indoor_rh_pct, "%", 1) },
          { label: "VPD", value: formatValue(liveState?.environment?.vpd_kpa, "kPa", 3) },
        ] },
      ],
      details: [{ label: "Spatial context", value: selection.spanId }, { label: "Environment scope", value: "House-level representative" }],
      source,
      connection,
      updated,
    };
  }

  const owner = assetEntry?.owner;
  const spanLabel = selection.spanId ? `Span ${selection.spanId.slice(1)}` : null;
  const title = owner ? displayTitle(owner, assetEntry.type) : selection.assetId ?? "Asset";
  const breadcrumb = [{ level: "greenhouse", label: "Greenhouse" }];
  if (selection.spanId) breadcrumb.push({ level: "span", spanId: selection.spanId, label: spanLabel });
  breadcrumb.push({ level: "asset", label: title });
  const liveRows = [];
  if (typeof assetContext.openingPercent === "number") liveRows.push({ label: "Opening", value: percent(assetContext.openingPercent) });
  if (owner?.userData?.control_variable) liveRows.push({ label: "Control", value: owner.userData.control_variable });
  if (selection.spanId) liveRows.push({ label: "Span", value: selection.spanId });
  if (assetContext.channel) liveRows.push({ label: "Mapped Channel", value: assetContext.channel });
  if (assetContext.channel) liveRows.push({ label: "Source", value: source });
  if (assetContext.channel) liveRows.push({ label: "Last Update", value: updated });
  if (assetContext.mappingStatus) liveRows.push({ label: "Mapping", value: assetContext.mappingStatus });
  if (!assetContext.channel && owner?.userData?.control_variable) {
    liveRows.push({ label: "LIVE mapping", value: "Not configured" });
  }
  return {
    title: title.toUpperCase(),
    breadcrumb,
    sections: liveRows.length ? [{ title: "LIVE Asset State", rows: liveRows }] : [],
    liveMessage: liveRows.length ? null : assetEntry?.type === "crop_zone"
      ? "Crop Zone is available for focus and visibility only. No crop analytics are configured."
      : "No verified LIVE mapping is available for this asset.",
    details: assetDetails(assetEntry),
    source,
    connection,
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
      event.currentTarget.setAttribute("aria-label", collapsed ? "Expand Context Panel" : "Collapse Context Panel");
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
    if (source) source.textContent = model.source === "MOCK" ? "LIVE — MOCK DATA" : model.source;
    if (connection) connection.textContent = model.connection;
    if (updated) updated.textContent = model.updated;
    this.root.dataset.connection = model.connection.toLowerCase();

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
      empty.innerHTML = "<strong>History unavailable</strong>";
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
        message.textContent = model.detailsMessage ?? "No additional metadata is available.";
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
