"use strict";

// The JEV Runtime page shows one dot per option of each question's latest
// request in the current run. It reads the fixed read-only summary route
// (GET /api/jev-options) instead of the 100-event Trace window, so every offered
// option survives a long run. A dot lights only when the summary marks that exact
// option as executed; the server derives that from a same-job game action whose
// Boundary status is success. Nothing on this page may infer execution from the
// model probability, a finished job, or a discarded proposal.

const JEV_OPTION_REFRESH_MS = 1000;
const jevById = (id) => document.getElementById(id);
const BRANCH_LABELS = { plant: "种植分支", collect: "收集分支" };
const QUESTION_LABELS = {
  should_collect_now: "是否立即收集",
  collect_target: "收集目标",
  construction_intent: "经营意图",
  next_construction_type: "下一建设类型",
  should_invest_economy: "是否投入经济",
  plant_target: "目标植物",
  plant_target_lane: "目标行",
};
const PLANT_OPTION_PATTERN = /^([^@\s]+)@r(\d+)c(\d+)$/;
const PLANT_LANE_TARGET_QUESTION_PATTERN = /^plant_target_lane_(\d+)$/;
const OPTION_STATE_LABELS = { true: "已证实执行", false: "未证实执行" };
// One matrix, colour tells you which question an option came from.
const PLANT_QUESTIONS = new Set(["plant_target", "plant_target_lane"]);
const COLLECT_QUESTIONS = new Set(["should_collect_now", "collect_target"]);
const MANAGE_QUESTIONS = new Set(["construction_intent", "next_construction_type", "should_invest_economy"]);
const CATEGORY_LABELS = { plant: "种植", collect: "收集", manage: "经营" };
function optionCategory(group) {
  const questionId = String(group?.question_id ?? "");
  if (MANAGE_QUESTIONS.has(questionId)) return "manage";
  if (COLLECT_QUESTIONS.has(questionId)) return "collect";
  if (PLANT_QUESTIONS.has(questionId) || PLANT_LANE_TARGET_QUESTION_PATTERN.test(questionId)) return "plant";
  return group?.branch_id === "collect" ? "collect" : "plant";
}
const OPTION_STATUS = {
  ok: ["本局候选", "每个节点代表本局某类问题最近一次请求中的一个选项；亮点只代表该选项已被同源成功动作证实执行。", "available"],
  legacy: ["历史 v1 记录", "v1 只记录周期结果，没有完整的问题选项，因此不显示决策网络。", "provisional"],
  unconfigured: ["尚未配置记录文件", "启动时指定 Loop 使用的同一文件。", "unavailable"],
  missing: ["等待记录文件", "文件尚未创建；运行 JEV Loop 并写入首条记录后会显示。", "unavailable"],
  empty: ["等待首个完整周期", "记录文件已配置，目前还没有完整事件。", "provisional"],
  error: ["记录暂时不可读", "请检查配置的文件；页面不会尝试读取其他路径。", "error"],
};
const OPTION_NOTICES = {
  ok: "本局还没有提出任何问题。",
  legacy: "历史 v1 记录没有完整的问题选项，不伪造节点。",
  unconfigured: "请配置记录文件路径。",
  missing: "等待 JEV Loop 创建记录并完成第一个周期。",
  empty: "记录文件已配置，目前还没有完整记录。",
  error: "记录内容或文件暂时无法读取。",
};
const NEW_RUN_NOTICE = "新一局正在启动；等待本局的第一个问题。";
let renderedMatrixKey = null;
let visibleRunId = null;
let previousRunId = null;
let awaitingNewRun = false;
let seenOptionKeys = new Set();
let runtimeBusy = false;

function jevText(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text === undefined || text === null ? "" : String(text);
  return element;
}

function questionTitle(group) {
  const questionId = String(group?.question_id ?? "");
  const lane = PLANT_LANE_TARGET_QUESTION_PATTERN.exec(questionId);
  const label = QUESTION_LABELS[questionId] || (lane ? `第 ${Number(lane[1]) + 1} 行目标植物` : questionId || "未知问题");
  const branch = BRANCH_LABELS[group?.branch_id] || (group?.branch_id ? String(group.branch_id) : null);
  return [branch, label].filter(Boolean).join(" · ");
}

// Plant options are identified by their type plus the one-based row/column they
// name; every other question keeps the option id the summary recorded.
function optionName(optionId) {
  const plant = PLANT_OPTION_PATTERN.exec(optionId);
  if (plant) return `${plant[1]} · 第 ${Number(plant[2]) + 1} 行第 ${Number(plant[3]) + 1} 列`;
  return optionId || "未命名 option";
}

function probabilityLabel(value) {
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : "未知";
}

function optionAccessibleName(group, option, executed) {
  return [
    CATEGORY_LABELS[optionCategory(group)],
    questionTitle(group),
    optionName(String(option?.option_id ?? "")),
    `模型概率 ${probabilityLabel(option?.probability)}`,
    OPTION_STATE_LABELS[String(executed)],
  ].join(" · ");
}

function setOptionStatus(status, groups) {
  // The HUD carries state through the controls and the network itself, so the
  // text panels are optional and every write below is guarded.
  const title = jevById("trace-status-title");
  const detail = jevById("trace-status-detail");
  const badge = jevById("trace-event-count");
  const [heading, message, badgeClass] = OPTION_STATUS[status] || OPTION_STATUS.error;
  if (title) title.textContent = heading;
  if (detail) detail.textContent = message;
  const optionCount = groups.reduce((total, group) => total + (Array.isArray(group?.options) ? group.options.length : 0), 0);
  if (badge) {
    badge.className = `state-badge ${badgeClass}`;
    badge.textContent = status === "ok" ? `${groups.length} 类问题 / ${optionCount} 个候选` : heading;
  }
}

function renderOptionNotice(status, text) {
  return jevText("p", `panel jev-empty-state jev-option-notice jev-option-notice-${status || "error"}`, text);
}

const INTENT_NODES = [
  { key: "collect", label: "收集" },
  { key: "plant", label: "种植" },
  { key: "cancel", label: "取消" },
];
const COLLECT_QUESTION_IDS = new Set(["should_collect_now", "collect_target"]);
const MANAGE_QUESTION_IDS = new Set(["construction_intent", "next_construction_type", "should_invest_economy"]);

function renderOptionDots(group, runId, freshKeys) {
  const options = Array.isArray(group?.options) ? group.options : [];
  const category = optionCategory(group);
  const dots = [];
  for (const option of options) {
    dots.push(makeOptionDot(group, option, category, runId, freshKeys));
  }
  return dots;
}

function makeOptionDot(group, option, category, runId, freshKeys) {
  const optionId = String(option?.option_id ?? "");
  const executed = option?.executed === true;
  const key = `${runId ?? ""}|${group?.question_id ?? ""}|${optionId}`;
  const dot = document.createElement("button");
  dot.type = "button";
  dot.className = `jev-decision-dot jev-dot-${category} ${executed ? "executed" : "pending"}`;
  if (freshKeys.has(key)) dot.classList.add("fresh");
  dot.dataset.optionKey = key;
  dot.dataset.questionId = String(group?.question_id ?? "");
  dot.dataset.optionId = optionId;
  dot.dataset.category = category;
  dot.dataset.executed = String(executed);
  const name = optionAccessibleName(group, option, executed);
  dot.setAttribute("aria-label", name);
  dot.title = name;
  return dot;
}

// The first layer is derived, not asked: which branch this cycle actually reached.
function deriveIntents(groups) {
  const questionIds = groups.map((group) => String(group?.question_id ?? ""));
  const plant = questionIds.some((id) => id.startsWith("plant_target"));
  const collect = questionIds.some((id) => COLLECT_QUESTION_IDS.has(id));
  const manage = questionIds.some((id) => MANAGE_QUESTION_IDS.has(id));
  return {
    collect: collect,
    plant: plant,
    // The cancel/manage path is live when a management question was asked, or when
    // this cycle reached neither of the two concrete branches.
    cancel: manage || (!plant && !collect),
  };
}


function matrixSignature(payload) {
  const groups = Array.isArray(payload?.questions) ? payload.questions : [];
  return JSON.stringify([
    payload?.status,
    payload?.schema_version,
    payload?.run_id,
    groups.map((group) => [
      group?.question_id,
      group?.job_id,
      (Array.isArray(group?.options) ? group.options : []).map((option) => [option?.option_id, option?.probability, option?.executed === true]),
    ]),
  ]);
}

function renderOptionMatrix(payload) {
  const timeline = jevById("jev-timeline");
  const status = payload?.status;
  const groups = Array.isArray(payload?.questions) ? payload.questions : [];
  const runId = typeof payload?.run_id === "string" ? payload.run_id : null;
  const startingNewRun = awaitingNewRun && (runId === null || runId === previousRunId);
  const signature = startingNewRun ? `starting:${runId}` : matrixSignature(payload);
  if (signature === renderedMatrixKey) return;
  const focusedKey = document.activeElement?.dataset?.optionKey || null;
  renderedMatrixKey = signature;
  if (startingNewRun) {
    setOptionStatus("empty", []);
    timeline.replaceChildren(renderOptionNotice("empty", NEW_RUN_NOTICE));
    return;
  }
  awaitingNewRun = false;
  if (runId !== visibleRunId) {
    // Another run owns its own matrix and lights; nothing carries over even when
    // the summary already dropped the old options.
    visibleRunId = runId;
    seenOptionKeys = new Set();
  }
  setOptionStatus(status, groups);
  if (status !== "ok" || groups.length === 0) {
    timeline.replaceChildren(renderOptionNotice(status, OPTION_NOTICES[status] || OPTION_NOTICES.error));
    return;
  }
  const currentKeys = new Set();
  for (const group of groups) {
    for (const option of (Array.isArray(group?.options) ? group.options : [])) {
      currentKeys.add(`${runId ?? ""}|${group?.question_id ?? ""}|${String(option?.option_id ?? "")}`);
    }
  }
  // Only truly newly appeared options animate; the first paint of a run is not a change.
  const freshKeys = seenOptionKeys.size === 0
    ? new Set()
    : new Set([...currentKeys].filter((key) => !seenOptionKeys.has(key)));
  seenOptionKeys = currentKeys;

  // Left to right: the derived intent layer, its links, then the concrete targets.
  const intents = deriveIntents(groups);
  const net = document.createElement("div");
  net.className = "jev-net";

  const intentColumn = document.createElement("div");
  intentColumn.className = "jev-net-intent";
  intentColumn.setAttribute("role", "group");
  intentColumn.setAttribute("aria-label", "本周期意图");
  for (const node of INTENT_NODES) {
    const active = intents[node.key] === true;
    const element = document.createElement("button");
    element.type = "button";
    element.className = `jev-intent-node jev-intent-${node.key} ${active ? "active" : "idle"}`;
    element.dataset.intent = node.key;
    element.dataset.active = String(active);
    const name = `${node.label}：本周期${active ? "已进入" : "未进入"}该分支`;
    element.setAttribute("aria-label", name);
    element.title = name;
    element.append(jevText("span", "jev-intent-core", ""));
    intentColumn.append(element);
  }

  const detail = document.createElement("div");
  detail.className = "jev-net-detail";
  // One dense mesh: every option of the run is a dot on a connected lattice.
  const mesh = document.createElement("div");
  mesh.className = "jev-mesh";
  mesh.setAttribute("role", "group");
  mesh.setAttribute("aria-label", "本局全部候选 option 点阵");
  for (const group of groups) {
    for (const dot of renderOptionDots(group, runId, freshKeys)) mesh.append(dot);
  }
  detail.append(mesh);
  net.append(intentColumn, detail);
  timeline.replaceChildren(net);
  if (focusedKey) {
    timeline.querySelectorAll(".jev-decision-dot").forEach((dot) => {
      if (dot.dataset.optionKey === focusedKey) dot.focus?.();
    });
  }
}

async function fetchOptionMatrix() {
  try {
    const response = await fetch("/api/jev-options", { cache: "no-store" });
    if (!response.ok) throw new Error("Option summary unavailable");
    renderOptionMatrix(await response.json());
  } catch {
    renderOptionMatrix({ status: "error", questions: [] });
  }
}

function renderRuntimeStatus(status) {
  // No status prose: the panel state drives the button lighting instead.
  const panel = jevById("jev-runtime");
  const state = status?.state || "unknown";
  if (panel) panel.dataset.state = state;
  const message = status?.message || "无法读取进程状态";
  const meta = `进程 ${status?.pid ?? "—"} · 退出码 ${status?.exit_code ?? "—"} · 游戏${status?.game_ready ? "进行中" : "未就绪"}`;
  const startButton = jevById("runtime-start");
  const stopButton = jevById("runtime-stop");
  if (startButton) {
    startButton.disabled = runtimeBusy || !status?.can_start;
    startButton.title = `启动 · ${message} · ${meta}`;
  }
  if (stopButton) {
    stopButton.disabled = runtimeBusy || !status?.can_stop;
    stopButton.title = `强制结束 · ${message} · ${meta}`;
  }
}

async function fetchRuntimeStatus() {
  try {
    const response = await fetch("/api/jev-runtime", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderRuntimeStatus(await response.json());
  } catch (error) {
    renderRuntimeStatus({ state: "failed", message: `进程状态不可读：${error}` });
  }
}

async function controlRuntime(command) {
  if (runtimeBusy) return;
  runtimeBusy = true;
  const startButton = jevById("runtime-start");
  const stopButton = jevById("runtime-stop");
  if (startButton) startButton.disabled = true;
  if (stopButton) stopButton.disabled = true;
  try {
    if (command === "start" && visibleRunId === null) await fetchOptionMatrix();
    const response = await fetch(`/api/jev-runtime/${command}`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-JEV-Control": "1" }, body: "{}", cache: "no-store",
    });
    const status = await response.json();
    if (command === "start" && response.ok) {
      previousRunId = visibleRunId;
      visibleRunId = null;
      awaitingNewRun = true;
      renderedMatrixKey = null;
      seenOptionKeys = new Set();
    }
    renderRuntimeStatus(status);
  } catch (error) {
    renderRuntimeStatus({ state: "failed", message: `控制请求失败：${error}` });
  } finally {
    runtimeBusy = false;
    await fetchRuntimeStatus();
    await fetchOptionMatrix();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const startButton = jevById("runtime-start");
  const stopButton = jevById("runtime-stop");
  if (startButton) startButton.addEventListener("click", () => controlRuntime("start"));
  if (stopButton) stopButton.addEventListener("click", () => controlRuntime("stop"));
  fetchRuntimeStatus();
  fetchOptionMatrix();
  window.setInterval(fetchRuntimeStatus, JEV_OPTION_REFRESH_MS);
  window.setInterval(fetchOptionMatrix, JEV_OPTION_REFRESH_MS);
});
