"use strict";

const JEV_TRACE_REFRESH_MS = 1000;
const jevById = (id) => document.getElementById(id);
const ACTION_LABELS = { wait: "等待", collect: "收集", plant: "种植", shovel: "铲除", place_plant: "种植", collect_item: "收集", shovel_cell: "铲除" };
const BRANCH_LABELS = { plant: "种植分支", collect: "收集分支" };
const RUNTIME_EVENT_LABELS = {
  job_start: "任务开始",
  request_result: "请求结果",
  proposal_discarded: "提案作废",
  action_result: "动作结果",
  job_end: "任务结束",
  runtime_stop: "运行停止",
};
const TRACE_EMPTY_MESSAGES = {
  unconfigured: "请在 Dashboard 启动参数中配置 JSONL Trace 路径。",
  missing: "等待 JEV Loop 创建 Trace 并完成第一个周期。",
  empty: "第一个决策周期完成后，时间线会显示在这里。",
  error: "Trace 内容或文件暂时无法读取。",
};

function jevText(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text === undefined || text === null ? "" : String(text);
  return element;
}

function actionLabel(action) {
  return ACTION_LABELS[action] || (action ? String(action).replaceAll("_", " ") : "未执行");
}

function probability(value) {
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : "—";
}

function sampleLabel(sequence) {
  return Number.isInteger(sequence) ? `State #${sequence}` : "无 State 样本";
}

function formatTimestamp(value) {
  if (typeof value !== "string") return "时间未知";
  return value.replace("T", " ").replace(/\.\d{3}Z$/, " UTC").replace(/Z$/, " UTC");
}

function renderCycle(event) {
  const card = document.createElement("article");
  card.className = "panel jev-cycle-card";

  const header = document.createElement("div");
  header.className = "jev-cycle-heading";
  const cycle = Number.isInteger(event?.cycle) ? event.cycle : "—";
  header.append(jevText("h3", "", `周期 ${cycle} · ${sampleLabel(event?.sample_sequence)}`));
  header.append(jevText("time", "jev-cycle-time", formatTimestamp(event?.timestamp_utc)));
  card.append(header);

  const state = event?.state || {};
  const game = state.game || {};
  const phase = game.phase ? String(game.phase).replaceAll("_", " ") : "阶段未知";
  card.append(jevText("p", "jev-state-line", `${phase} · 阳光 ${Number.isInteger(state.sun_balance) ? state.sun_balance : "—"}`));

  const router = event?.router;
  if (router?.response) {
    const response = router.response;
    const candidates = Array.isArray(response.candidates) ? response.candidates : [];
    const scores = response.noul_probabilities || {};
    const candidateText = candidates.length
      ? candidates.map((candidate) => `${actionLabel(candidate)} ${probability(scores[candidate])}`).join("、")
      : "无候选动作";
    const choice = `${actionLabel(response.choice)}（confidence ${probability(response.confidence)}）`;
    card.append(jevText("p", "jev-decision-line", `Router 候选：${candidateText} · 下一步：${choice}`));
  } else {
    card.append(jevText("p", "jev-decision-line", "Router 未调用"));
  }

  const action = event?.action;
  if (action) {
    const target = action.target;
    const targetText = target
      ? target.action === "place_plant" ? `${target.type_name || "植物"} · 第 ${(Number.isInteger(target.row) ? target.row + 1 : "?")} 行第 ${(Number.isInteger(target.col) ? target.col + 1 : "?")} 列`
        : target.action === "shovel_cell" ? `第 ${(Number.isInteger(target.row) ? target.row + 1 : "?")} 行第 ${(Number.isInteger(target.col) ? target.col + 1 : "?")} 列`
          : target.type_name || "已选择目标"
      : action.status === "skipped_no_targets" ? "没有有效目标，未请求 Action"
        : action.fallback_reason ? `转为等待：${String(action.fallback_reason).replaceAll("_", " ")}` : "没有执行目标";
    card.append(jevText("p", "jev-action-line", `Action：${actionLabel(action.intent)} · ${targetText}`));
  } else if (event?.effective_decision === "wait" || event?.outcome === "not_ready") {
    card.append(jevText("p", "jev-action-line", "Action：未请求"));
  }

  const boundary = event?.boundary;
  if (boundary) {
    card.append(jevText("p", "jev-result-line", `动作边界：${boundary.status || "未知"} · ${actionLabel(boundary.action)}`));
  } else {
    card.append(jevText("p", "jev-result-line", `周期结果：${String(event?.outcome || "未知").replaceAll("_", " ")}`));
  }

  if (event?.error_code) card.append(jevText("p", "jev-error-line", `错误类型：${event.error_code}`));
  if (event?.router?.fallback_reason) {
    card.append(jevText("p", "jev-fallback-line", `Router 回退：${String(event.router.fallback_reason).replaceAll("_", " ")}`));
  }
  const nextSequence = event?.next_observation?.sample_sequence;
  card.append(jevText("p", "jev-next-line", `下一观察：${Number.isInteger(nextSequence) ? `State #${nextSequence}` : "本次运行结束"}`));
  return card;
}

function setTraceStatus(status, count = 0, unit = "周期") {
  const title = jevById("trace-status-title");
  const detail = jevById("trace-status-detail");
  const badge = jevById("trace-event-count");
  const labels = {
    ok: ["Trace 已连接", `显示最近 ${count} 个完整${unit}。`, "available"],
    unconfigured: ["尚未配置 Trace", "启动 Dashboard 时通过 --jev-trace-file 指定 Loop 使用的同一文件。", "unavailable"],
    missing: ["等待 Trace 文件", "文件尚未创建；运行 JEV Loop 并写入首条记录后会显示。", "unavailable"],
    empty: ["等待首个完整周期", "Trace 文件已配置，目前还没有完整事件。", "provisional"],
    error: ["Trace 暂时不可读", "请检查配置的 Trace 文件；页面不会尝试读取其他路径。", "error"],
  };
  const [heading, message, badgeClass] = labels[status] || labels.error;
  title.textContent = heading;
  detail.textContent = message;
  badge.className = `state-badge ${badgeClass}`;
  badge.textContent = status === "ok" ? `${count} 个${unit}` : heading;
}

function renderEmptyTraceTimeline(timeline, status) {
  timeline.append(jevText("p", "panel jev-empty-state", TRACE_EMPTY_MESSAGES[status] || TRACE_EMPTY_MESSAGES.error));
}

function renderCycleTrace(payload, events) {
  const timeline = jevById("jev-timeline");
  setTraceStatus(payload?.status, events.length);
  timeline.replaceChildren();
  if (events.length === 0) {
    renderEmptyTraceTimeline(timeline, payload?.status);
    return;
  }
  for (const event of [...events].reverse()) timeline.append(renderCycle(event));
}

// --------------------------------------------------------- v2 runtime trace

function branchLabel(branch) {
  return BRANCH_LABELS[branch] || (branch ? String(branch) : "未知分支");
}

function jobIndex(events, name) {
  const index = {};
  events.filter((event) => event?.event === name).forEach((event, position) => {
    if (event.job_id && !(event.job_id in index)) index[event.job_id] = position + 1;
  });
  return index;
}

// The decision that finishes first is not always the action that runs first: the
// scheduler orders ready proposals by urgency while job_end follows completion
// order. These two helpers keep both orders visible and separate.
function decisionCompletionOrderText(events) {
  const completions = events.filter((event) => event?.event === "job_end");
  if (!completions.length) return "决策完成顺序：暂无已完成决策";
  return `决策完成顺序：${completions.map((event, position) => `${position + 1}.${branchLabel(event.branch_id)}(${event.job_id || "未编号"})`).join(" → ")}`;
}

function executionOrderText(events) {
  const executions = events.filter((event) => event?.event === "action_result");
  if (!executions.length) return "实际执行顺序：本轮没有已执行动作";
  return `实际执行顺序：${executions.map((event, position) => `${position + 1}.${branchLabel(event.branch_id)}(${event.execution_id || "未编号"})`).join(" → ")}`;
}

function runtimeEventDetail(event) {
  if (event.event === "job_start") {
    const strategy = event.strategy || {};
    const phase = strategy.phase ? String(strategy.phase).replaceAll("_", " ") : "阶段未知";
    const age = Number.isInteger(event.sample_age_ms) ? `${event.sample_age_ms} ms` : "未知";
    return `${sampleLabel(event.sample_sequence)} · 样本年龄 ${age} · 阶段 ${phase}`;
  }
  if (event.event === "request_result") {
    const merge = event.merge || {};
    if (event.branch_id === "collect" && event.state?.current_intent) {
      const intent = event.state.current_intent;
      return `自主经营 · 意图 ${intent.type_name || "无"} · 来源版本 ${intent.version ?? "—"}`;
    }
    const rows = Array.isArray(merge.needed_rows) ? merge.needed_rows.join("、") : "无";
    const reranked = merge.reranked === true ? " · 约束下重排" : "";
    const rejected = merge.rejected_option ? ` · 重排前候选 ${merge.rejected_option}` : "";
    const latency = Number.isInteger(event.latency_ms) ? `${event.latency_ms} ms` : "未知";
    return `延迟 ${latency} · 目标规则 ${event.target_choice_rule || "未知"} · 需要响应的行 ${rows} · 选中 ${merge.chosen_option || "无"} → ${merge.selected_option || "无"}${reranked}${rejected}`;
  }
  if (event.event === "proposal_discarded") {
    const queue = Number.isInteger(event.queue_delay_ms) ? `${event.queue_delay_ms} ms` : "未知";
    return `目标 ${actionLabel(event.effective_action)} · 作废原因 ${String(event.discard_reason || "未知").replaceAll("_", " ")} · 排队 ${queue}`;
  }
  if (event.event === "action_result") {
    const boundary = event.boundary || {};
    const queue = Number.isInteger(event.queue_delay_ms) ? `${event.queue_delay_ms} ms` : "未知";
    return `目标 ${actionLabel(event.effective_action)} · 边界 ${boundary.status || "未知"} ${actionLabel(boundary.action)} · 排队 ${queue}`;
  }
  if (event.event === "job_end") {
    const reason = event.error_code ? ` · 错误类型 ${event.error_code}` : "";
    return `结果 ${String(event.outcome || "未知").replaceAll("_", " ")}${reason}`;
  }
  const pending = Array.isArray(event.pending_proposals) ? event.pending_proposals.length : 0;
  return `原因 ${String(event.stop_reason || "未知").replaceAll("_", " ")} · 未处理提案 ${pending}`;
}

function renderRuntimeEvent(event) {
  const sequence = Number.isInteger(event?.event_sequence) ? `#${event.event_sequence}` : "#—";
  const name = RUNTIME_EVENT_LABELS[event?.event] || String(event?.event || "事件");
  const line = jevText(
    "p",
    `jev-runtime-event jev-runtime-${event?.event || "unknown"}`,
    `${sequence} ${name} · ${runtimeEventDetail(event || {})}`,
  );
  return line;
}

function renderRuntimeJob(jobId, branch, events, completions, executions) {
  const card = document.createElement("article");
  card.className = "panel jev-cycle-card jev-runtime-job";
  const header = document.createElement("div");
  header.className = "jev-cycle-heading";
  header.append(jevText("h3", "", `任务 ${jobId} · ${branchLabel(branch)}`));
  const completed = completions[jobId] ? `#${completions[jobId]}` : "未完成";
  const dispatched = executions[jobId] ? `#${executions[jobId]}` : "未执行";
  header.append(jevText("time", "jev-cycle-time", `决策完成顺序 ${completed} · 实际执行顺序 ${dispatched}`));
  card.append(header);
  for (const event of events) card.append(renderRuntimeEvent(event));
  return card;
}

function renderRuntimeTrace(payload, events) {
  const timeline = jevById("jev-timeline");
  setTraceStatus(payload?.status, events.length, "事件");
  timeline.replaceChildren();
  if (events.length === 0) {
    renderEmptyTraceTimeline(timeline, payload?.status);
    return;
  }
  timeline.append(jevText("p", "panel jev-runtime-order", decisionCompletionOrderText(events)));
  timeline.append(jevText("p", "panel jev-runtime-order", executionOrderText(events)));
  const completions = jobIndex(events, "job_end");
  const executions = jobIndex(events, "action_result");
  const jobs = [];
  const byJob = new Map();
  for (const event of events) {
    if (event?.event === "runtime_stop") continue;
    const key = event?.job_id || "无任务";
    if (!byJob.has(key)) {
      byJob.set(key, { branch: event?.branch_id, events: [] });
      jobs.push(key);
    }
    byJob.get(key).events.push(event);
  }
  for (const jobId of [...jobs].reverse()) {
    const job = byJob.get(jobId);
    timeline.append(renderRuntimeJob(jobId, job.branch, job.events, completions, executions));
  }
  for (const event of [...events].filter((item) => item?.event === "runtime_stop").reverse()) {
    timeline.append(renderRuntimeEvent(event));
  }
}

function renderTrace(payload) {
  const events = Array.isArray(payload?.events) ? payload.events : [];
  if (payload?.schema_version === 2) renderRuntimeTrace(payload, events);
  else renderCycleTrace(payload, events);
}

async function fetchJevTrace() {
  try {
    const response = await fetch("/api/jev-trace", { cache: "no-store" });
    if (!response.ok) throw new Error("Trace API unavailable");
    renderTrace(await response.json());
  } catch {
    renderTrace({ status: "error", events: [] });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  fetchJevTrace();
  window.setInterval(fetchJevTrace, JEV_TRACE_REFRESH_MS);
});
