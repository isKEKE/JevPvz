"use strict";

const STATE_REFRESH_MS = 500;
const stateById = (id) => document.getElementById(id);
let currentStateJson = null;
let selectedProfile = "jev";
let renderedProfile = null;
const expandedPathsByProfile = {
  jev: new Set(["[]"]),
  all: new Set(["[]"]),
};

function updateProfileLabel() {
  const name = selectedProfile === "jev" ? "JEV State" : "All State";
  stateById("state-profile-label").textContent = `当前：${name}`;
  stateById("state-json-title").textContent = `${name} 快照`;
  stateById("state-copy-button").setAttribute("aria-label", `复制当前 ${name} JSON`);
  for (const button of document.querySelectorAll("[data-state-profile]")) {
    const active = button.dataset.stateProfile === selectedProfile;
    button.setAttribute("aria-pressed", String(active));
    button.classList.toggle("selected", active);
  }
}

function appendJsonText(parent, className, text) {
  const span = document.createElement("span");
  span.className = className;
  span.textContent = text;
  parent.append(span);
  return span;
}

function appendJsonKey(parent, key) {
  appendJsonText(parent, "json-key", JSON.stringify(key));
  appendJsonText(parent, "json-punctuation", ": ");
}

function renderJsonEntry(value, key, path, isRoot, isLast, isArrayEntry = false) {
  const entry = document.createElement("div");
  entry.className = "json-entry";

  if (value !== null && typeof value === "object") {
    const array = Array.isArray(value);
    const children = array
      ? value.map((child, index) => [index, child])
      : Object.entries(value);
    const openToken = array ? "[" : "{";
    const closeToken = array ? "]" : "}";

    if (children.length === 0) {
      const line = document.createElement("div");
      line.className = "json-line";
      if (!isRoot && !isArrayEntry) appendJsonKey(line, key);
      appendJsonText(line, "json-punctuation", `${openToken}${closeToken}`);
      entry.append(line);
    } else {
      const pathKey = JSON.stringify(path);
      const details = document.createElement("details");
      details.className = "json-composite";
      details.dataset.jsonPath = pathKey;
      details.open = expandedPathsByProfile[selectedProfile].has(pathKey);

      const summary = document.createElement("summary");
      summary.className = "json-line json-composite-summary";
      if (!isRoot && !isArrayEntry) appendJsonKey(summary, key);
      appendJsonText(summary, "json-punctuation", openToken);
      appendJsonText(summary, "json-collapsed-hint", "…");
      appendJsonText(summary, "json-collapsed-close", closeToken);
      details.append(summary);

      const nested = document.createElement("div");
      nested.className = "json-children";
      const keyWidth = array ? 0 : children.reduce(
        (longest, [childKey]) => Math.max(longest, JSON.stringify(childKey).length), 0,
      );
      nested.style.setProperty("--json-key-width", `${keyWidth}ch`);
      for (const [childIndex, [childKey, childValue]] of children.entries()) {
        nested.append(renderJsonEntry(
          childValue,
          childKey,
          [...path, [array ? "index" : "key", childKey]],
          false,
          childIndex === children.length - 1,
          array,
        ));
      }
      details.append(nested);

      const closing = document.createElement("div");
      closing.className = "json-line json-closing";
      appendJsonText(closing, "json-punctuation", closeToken);
      details.append(closing);
      entry.append(details);
    }
  } else {
    const line = document.createElement("div");
    line.className = "json-line";
    if (!isRoot && !isArrayEntry) appendJsonKey(line, key);
    if (value === null) {
      appendJsonText(line, "json-null", "null");
    } else if (typeof value === "string") {
      appendJsonText(line, "json-string", JSON.stringify(value));
    } else if (typeof value === "number") {
      appendJsonText(line, "json-number", String(value));
    } else {
      appendJsonText(line, "json-boolean", String(value));
    }
    entry.append(line);
  }

  if (!isLast) appendJsonText(entry, "json-punctuation json-comma", ",");
  return entry;
}

function captureExpandedPaths(container, profile) {
  const expanded = expandedPathsByProfile[profile];
  for (const details of container.querySelectorAll("details[data-json-path]")) {
    const path = details.dataset.jsonPath;
    if (details.open) expanded.add(path);
    else expanded.delete(path);
  }
}

function clearJsonTree(message) {
  const container = stateById("state-json");
  container.replaceChildren();
  container.textContent = message;
  renderedProfile = null;
}

function renderJsonTree(state) {
  const container = stateById("state-json");
  if (renderedProfile === selectedProfile) captureExpandedPaths(container, selectedProfile);
  container.replaceChildren(renderJsonEntry(state, null, [], true, true));
  renderedProfile = selectedProfile;
}

function renderObservedState(state) {
  const ok = state?.status === "ok" && state.valid === true;
  stateById("state-status").textContent = state?.status === "disconnected" ? "游戏未连接"
    : state?.status === "connecting" ? "等待首次采样"
      : state?.status === "unreachable" ? "服务不可达" : ok ? "采样正常" : "State 错误";
  stateById("state-time").textContent = state?.observed_at_utc || "尚未采样";
  stateById("state-sequence").textContent = state?.sample_sequence ?? "—";
  stateById("state-valid").textContent = `${state?.valid === true ? "是" : "否"} / ${state?.decision_ready === true ? "是" : "否"}`;
  const error = stateById("state-error");
  const errors = Array.isArray(state?.errors) ? state.errors : [];
  error.hidden = ok && errors.length === 0;
  error.textContent = errors.length
    ? `${state?.status === "unreachable" ? "服务不可达" : "State 错误"}：${errors.map((item) => `${item.scope || "错误"}：${item.message || "读取失败"}`).join("；")}`
    : state?.status === "disconnected" ? "游戏进程当前未连接。" : state?.status === "connecting" ? "等待后台采样器取得第一个快照。" : ok ? "" : "State 尚不可用。";
  const badge = stateById("state-availability");
  badge.className = `state-badge ${ok ? "available" : "error"}`;
  badge.textContent = ok ? "最新快照" : "无有效快照";
  // Keep this exact selected-profile JSON for copying; the DOM tree is presentation only.
  currentStateJson = ok ? JSON.stringify(state, null, 2) : null;
  stateById("state-copy-button").disabled = currentStateJson === null;
  if (currentStateJson === null) {
    stateById("state-copy-status").textContent = "";
    clearJsonTree("当前没有有效快照；旧样本已清除。");
  } else {
    renderJsonTree(state);
  }
}

async function copyObservedStateJson() {
  if (!currentStateJson) return;
  const status = stateById("state-copy-status");
  try {
    const clipboard = globalThis.navigator?.clipboard;
    if (!clipboard?.writeText) throw new Error("Clipboard API unavailable");
    await clipboard.writeText(currentStateJson);
    status.textContent = "已复制当前快照";
  } catch {
    status.textContent = "复制失败，请检查浏览器剪贴板权限";
  }
}

async function fetchObservedState() {
  const profile = selectedProfile;
  try {
    const response = await fetch(profile === "jev" ? "/api/jev-state" : "/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const state = await response.json();
    if (profile === selectedProfile) renderObservedState(state);
  } catch (error) {
    if (profile === selectedProfile) renderObservedState({ status: "unreachable", valid: false, decision_ready: false,
      errors: [{ scope: "服务不可达", message: String(error) }] });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  stateById("state-copy-button").addEventListener("click", copyObservedStateJson);
  for (const button of document.querySelectorAll("[data-state-profile]")) {
    button.addEventListener("click", () => {
      captureExpandedPaths(stateById("state-json"), selectedProfile);
      selectedProfile = button.dataset.stateProfile;
      currentStateJson = null;
      stateById("state-copy-button").disabled = true;
      stateById("state-copy-status").textContent = "";
      clearJsonTree("等待所选 State profile 的最新快照…");
      stateById("state-status").textContent = "正在获取所选 State";
      stateById("state-error").hidden = true;
      stateById("state-availability").textContent = "等待采样";
      updateProfileLabel();
      fetchObservedState();
    });
  }
  updateProfileLabel();
  fetchObservedState();
  window.setInterval(fetchObservedState, STATE_REFRESH_MS);
});
