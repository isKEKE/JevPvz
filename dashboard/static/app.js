"use strict";

const REFRESH_MS = 500;
// Set only after comparing game-space X against this exact lawn layout.
const ZOMBIE_X_CALIBRATION = null;
const AVAILABILITY_LABELS = {
  available: "已核验",
  provisional: "待动态核验",
  unavailable: "未获取",
  error: "读取错误",
};
const FIELD_LABELS = {
  "sun_balance": "阳光余额",
  "plants": "植物列表",
  "zombies": "僵尸列表",
  "zombies.hp": "僵尸 HP",
  "items": "掉落物列表",
  "items.position": "掉落物坐标",
  "collectible_suns": "阳光掉落物识别",
  "cards": "卡槽与类型",
  "cards.cooldown": "卡牌冷却计数",
  "cards.cost": "卡牌费用（静态）",
  "game.phase": "游戏阶段",
  "game.scene": "游戏场景",
  "game.mode": "游戏模式",
  "game.background": "场地类型",
  "game.paused": "暂停标志",
  "game.level": "关卡编号",
  "game.wave": "已生成波数",
  "game.total_waves": "总波数",
  "game.level_complete": "关卡完成标志",
  "board.terrain": "地形",
  "board.plantability": "格子可种规则",
};

function byId(id) { return document.getElementById(id); }

function makeBadge(status) {
  const badge = document.createElement("span");
  badge.className = `state-badge ${status || "unavailable"}`;
  badge.textContent = AVAILABILITY_LABELS[status] || "未获取";
  return badge;
}

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function buildBoard() {
  const board = byId("board");
  if (board.children.length) return;
  board.append(makeElement("div", "board-corner", ""));
  for (let col = 0; col < 9; col += 1) board.append(makeElement("div", "column-label", col + 1));
  for (let row = 0; row < 5; row += 1) {
    board.append(makeElement("div", "row-label", `第 ${row + 1} 行`));
    for (let col = 0; col < 9; col += 1) {
      const cell = makeElement("div", "board-cell unknown");
      cell.dataset.row = row;
      cell.dataset.col = col;
      cell.id = `cell-${row}-${col}`;
      board.append(cell);
    }
  }
  const lawn = makeElement("div", "lawn-area");
  const layer = makeElement("div", "zombie-layer");
  layer.id = "zombie-layer";
  lawn.append(layer);
  board.append(lawn);
}

function projectZombieX(x) {
  if (!ZOMBIE_X_CALIBRATION || !Number.isFinite(Number(x))) return null;
  const span = ZOMBIE_X_CALIBRATION.max - ZOMBIE_X_CALIBRATION.min;
  if (!span) return null;
  return Math.max(0, Math.min(100, (Number(x) - ZOMBIE_X_CALIBRATION.min) / span * 100));
}

function renderBoard(state) {
  buildBoard();
  const cells = state.board && Array.isArray(state.board.cells) ? state.board.cells : [];
  const plantStatus = state.availability?.plants || state.availability?.["board.occupancy"] || "unavailable";
  const plantsReadable = Array.isArray(state.plants) && (plantStatus === "available" || plantStatus === "provisional");
  for (let row = 0; row < 5; row += 1) {
    for (let col = 0; col < 9; col += 1) {
      const cell = byId(`cell-${row}-${col}`);
      const plant = cells[row] && cells[row][col];
      cell.replaceChildren();
      cell.className = `board-cell ${plantsReadable ? (plant ? "occupied" : "empty") : "unknown"}`;
      if (!plantsReadable) {
        const label = plantStatus === "error" ? "植物读取失败" : "植物未获取";
        cell.append(makeElement("span", "plantability-label", label));
        cell.title = `${label}；无法判断当前格是否为空`;
      } else if (plant) {
        const occupants = Array.isArray(plant.plants) && plant.plants.length ? plant.plants : [plant];
        cell.append(makeElement("span", "plant-glyph", "♣"));
        for (const occupant of occupants) {
          const name = occupant.type_name && occupant.type_name !== "unknown" ? occupant.type_name : `植物 #${occupant.type_code}`;
          cell.append(makeElement("span", "plant-name", name));
        }
        cell.title = `${occupants.map((occupant) => `${occupant.type_name && occupant.type_name !== "unknown" ? occupant.type_name : "未知植物"} · 类型码 ${occupant.type_code}`).join("；")} · 第 ${row + 1} 行第 ${col + 1} 列`;
      } else {
        cell.append(makeElement("span", "empty-dot", "·"));
        cell.append(makeElement("span", "plantability-label", "可种未知"));
        cell.title = "当前无植物；可种规则未获取";
      }
    }
  }
  const layer = byId("zombie-layer");
  layer.replaceChildren();
  const zombies = Array.isArray(state.zombies) ? state.zombies : [];
  if (!ZOMBIE_X_CALIBRATION) {
    byId("overlay-status").textContent = zombies.length
      ? "位置未校准，未绘制僵尸覆盖图标；详情保留实测行与原始 X/Y。"
      : "僵尸位置覆盖层未校准；右侧保留原始行与 X/Y。";
    return;
  }
  byId("overlay-status").textContent = "覆盖图标按最近一次采样定位；不会在采样之间自行移动。";
  for (const zombie of zombies) {
    const left = projectZombieX(zombie.x);
    if (left === null || !Number.isInteger(zombie.row) || zombie.row < 0 || zombie.row > 4) continue;
    const marker = makeElement("span", "zombie-marker", `Z${zombie.type_code}`);
    marker.style.left = `${left}%`;
    marker.style.top = `${(zombie.row + 0.5) * 20}%`;
    const hpValue = (value) => Number.isInteger(value) ? value : "未获取";
    marker.title = `${zombie.type_name && zombie.type_name !== "unknown" ? zombie.type_name : "未知僵尸"} · 第 ${zombie.row + 1} 行 · X ${zombie.x} · Y ${zombie.y} · 本体 HP ${hpValue(zombie.body_hp ?? zombie.hp)} · 头盔 HP ${hpValue(zombie.helmet_hp)} · 盾牌 HP ${hpValue(zombie.shield_hp)} · 气球 HP ${hpValue(zombie.balloon_hp)} · 各部位 HP 合计（数值参考） ${hpValue(zombie.total_hp)}`;
    layer.append(marker);
  }
}

function renderCards(state) {
  const container = byId("cards-list");
  container.replaceChildren();
  const cards = Array.isArray(state.cards) ? state.cards : null;
  const oldBadge = byId("cards-status");
  const statusBadge = makeBadge(state.availability?.cards || "unavailable");
  statusBadge.id = "cards-status";
  oldBadge.replaceWith(statusBadge);
  if (!cards) {
    container.append(makeElement("p", "empty-message", "卡槽尚未读取"));
    return;
  }
  if (!cards.length) {
    container.append(makeElement("p", "empty-message", "当前没有卡牌槽"));
    return;
  }
  for (const card of cards) {
    const item = makeElement("article", "seed-card");
    item.append(makeElement("span", "seed-index", `槽位 ${Number(card.slot) + 1}`));
    const typeLabel = card.type_name && card.type_name !== "unknown" ? card.type_name : "未知植物";
    item.append(makeElement("strong", "seed-type", Number.isInteger(card.type_code) ? `${typeLabel} · #${card.type_code}` : "类型未知"));
    const cost = Number.isInteger(card.cost) ? card.cost : null;
    item.append(makeElement("span", "seed-cost", cost === null ? "费用：未获取" : `费用：${cost} 阳光`));
    const progress = Number(card.cooldown_progress_raw);
    const total = Number(card.cooldown_total_raw);
    const cooldown = makeElement("span", "seed-cooldown", Number.isFinite(progress) && Number.isFinite(total)
      ? `冷却原始计数 ${progress} / ${total}` : "冷却计数：未获取");
    item.append(cooldown);
    if (Number.isFinite(progress) && Number.isFinite(total) && total > 0) {
      const track = makeElement("div", "cooldown-track");
      const fill = makeElement("span", "cooldown-fill");
      fill.style.width = `${Math.max(0, Math.min(100, progress / total * 100))}%`;
      track.append(fill);
      item.append(track);
    }
    item.append(makeElement("span", "seed-evidence", AVAILABILITY_LABELS[state.availability?.["cards.cooldown"]] || "待动态核验"));
    container.append(item);
  }
}

function renderLanes(state) {
  const container = byId("lane-list");
  container.replaceChildren();
  const zombies = Array.isArray(state.zombies) ? state.zombies : null;
  const lanes = Array.isArray(state.lanes) ? state.lanes : [];
  const currentBadge = byId("zombies-status");
  const replacement = makeBadge(state.availability?.zombies || "unavailable");
  replacement.id = currentBadge.id;
  currentBadge.replaceWith(replacement);
  if (!zombies) {
    container.append(makeElement("p", "empty-message", "僵尸域读取失败或尚未映射"));
    return;
  }
  for (let row = 0; row < 5; row += 1) {
    const lane = lanes.find((candidate) => candidate.row === row);
    const laneZombies = zombies.filter((zombie) => zombie.row === row);
    const article = makeElement("article", "lane-row");
    const heading = makeElement("div", "lane-heading");
    heading.append(makeElement("strong", "", `第 ${row + 1} 行`));
    heading.append(makeElement("span", "lane-count", `${lane?.zombie_count ?? laneZombies.length} 只`));
    article.append(heading);
    if (!laneZombies.length) {
      article.append(makeElement("p", "lane-empty", "当前没有"));
    }
    for (const zombie of laneZombies) {
      const detail = makeElement("div", "zombie-detail");
      const typeLabel = zombie.type_name && zombie.type_name !== "unknown" ? zombie.type_name : "未知僵尸";
      detail.append(makeElement("strong", "zombie-name", `${typeLabel} · #${zombie.type_code}`));
      detail.append(makeElement("span", "", `X ${zombie.x} · Y ${zombie.y}`));
      const hpValue = (value) => Number.isInteger(value) ? value : "未获取";
      const hpParts = [
        `本体 ${hpValue(zombie.body_hp ?? zombie.hp)}`,
        `头盔 ${hpValue(zombie.helmet_hp)}`,
        `盾牌 ${hpValue(zombie.shield_hp)}`,
        `气球 ${hpValue(zombie.balloon_hp)}`,
      ];
      detail.append(makeElement("span", "", Number.isInteger(zombie.total_hp)
        ? `各部位 HP 合计（数值参考） ${zombie.total_hp}（${hpParts.join(" + ")}）`
        : `各部位 HP 合计（数值参考）未获取（${hpParts.join(" + ")}）`));
      detail.append(makeElement("span", "evidence-inline", AVAILABILITY_LABELS[state.availability?.["zombies.hp"]] || "待动态核验"));
      article.append(detail);
    }
    container.append(article);
  }
}

function renderItems(state) {
  const container = byId("items-list");
  container.replaceChildren();
  if (!Array.isArray(state.items)) {
    container.append(makeElement("p", "empty-message", state.availability?.items === "error" ? "掉落物读取错误" : "未获取"));
    return;
  }
  if (!state.items.length) {
    container.append(makeElement("p", "empty-message", "当前没有"));
    return;
  }
  for (const item of state.items) {
    const line = makeElement("div", "detail-row");
    const typeLabel = item.type_name && item.type_name !== "unknown" ? item.type_name : "未知掉落物";
    line.append(makeElement("strong", "", `${typeLabel} · #${item.type_code ?? "未知"}`));
    line.append(makeElement("span", "", `X ${item.x ?? "未知"} · Y ${item.y ?? "未知"}`));
    line.append(makeElement("span", "evidence-inline", item.type_meaning === "candidate" ? "类型映射待核验" : "类型含义未知"));
    container.append(line);
  }
}

function renderGame(state) {
  const container = byId("game-details");
  container.replaceChildren();
  const game = state.game || {};
  const codeValue = (value, code, unknownLabel) => {
    if (value !== null && value !== undefined) return code === null || code === undefined ? value : `${value}（码 ${code}）`;
    if (code !== null && code !== undefined) return `${unknownLabel}（码 ${code}）`;
    return null;
  };
  const waveValue = game.spawned_waves === null || game.spawned_waves === undefined
    ? null : `已生成 ${game.spawned_waves} 波 / 总计 ${Number.isInteger(game.total_waves) ? `${game.total_waves} 波` : "未获取"}`;
  const fields = [
    ["场景", codeValue(game.scene ?? game.phase, game.scene_code, "未知场景"), "game.scene"],
    ["模式", codeValue(game.mode, game.mode_code, "未知模式"), "game.mode"],
    ["场地", codeValue(game.background, game.background_code, "未知场地"), "game.background"],
    ["暂停", game.paused === null || game.paused === undefined
      ? (Number.isInteger(game.pause_raw_code) ? `原始标志异常（${game.pause_raw_code}）` : null)
      : (game.paused ? "是" : "否"), "game.paused"],
    ["关卡", game.level, "game.level"],
    ["波次", waveValue, "game.wave"],
    ["关卡完成", game.level_complete === null || game.level_complete === undefined
      ? (Number.isInteger(game.level_complete_raw_code) ? `原始标志异常（${game.level_complete_raw_code}）` : null)
      : (game.level_complete ? "是" : "否"), "game.level_complete"],
  ];
  for (const [label, value, key] of fields) {
    const row = makeElement("div", "detail-row");
    row.append(makeElement("strong", "", label));
    row.append(makeElement("span", "", value === null || value === undefined ? AVAILABILITY_LABELS[state.availability?.[key]] || "未获取" : value));
    row.append(makeBadge(state.availability?.[key] || "unavailable"));
    container.append(row);
  }
  const raw = game.progress_raw || {};
  const rawCodes = Object.entries(raw).map(([name, field]) => `${name}: ${field?.value ?? "—"}`).join(" · ");
  if (rawCodes) container.append(makeElement("p", "raw-candidate", `候选原始值：${rawCodes}`));
}

function renderCoverage(state) {
  const container = byId("missing-list");
  container.replaceChildren();
  const availability = state.availability || {};
  for (const [key, label] of Object.entries(FIELD_LABELS)) {
    const status = availability[key] || "unavailable";
    const row = makeElement("div", `coverage-row ${status}`);
    row.append(makeElement("span", "coverage-label", label));
    const statusLabel = key === "cards.cost" && status === "provisional" && state.evidence?.[key] === "static_catalog"
      ? "静态配置" : AVAILABILITY_LABELS[status] || "未获取";
    row.append(makeElement("span", "coverage-value", statusLabel));
    container.append(row);
  }
}

function renderDiagnostics(state) {
  const container = byId("sample-diagnostics");
  container.replaceChildren();
  const source = state.source || {};
  const rows = [
    ["状态", state.status || (state.valid ? "ok" : "error")],
    ["采样序号", state.sample_sequence ?? "—"],
    ["进程 PID", source.pid ?? "未连接"],
    ["目标版本", source.profile || "pvz-1.0.0.1051"],
    ["内部一致", state.valid ? "是" : "否"],
    ["决策就绪", state.decision_ready ? "是" : "否"],
  ];
  for (const [label, value] of rows) {
    const row = makeElement("div", "detail-row");
    row.append(makeElement("strong", "", label));
    row.append(makeElement("span", "", value));
    container.append(row);
  }
  for (const error of (Array.isArray(state.errors) ? state.errors : [])) {
    const line = makeElement("p", "error-line", `${error.scope || "错误"}：${error.message || "读取失败"}`);
    container.append(line);
  }
}

function renderState(state) {
  const pill = byId("connection-pill");
  pill.className = `connection-pill ${state.status === "disconnected" ? "disconnected" : state.valid ? "connected" : "warning"}`;
  byId("connection-label").textContent = state.status === "disconnected" ? "游戏未连接"
    : state.status === "connecting" ? "正在连接"
      : state.valid ? "采样已更新" : "采样存在错误";
  const sunStatus = state.availability?.sun_balance || "unavailable";
  byId("sun-value").textContent = state.sun_balance === null || state.sun_balance === undefined ? "—" : state.sun_balance.toLocaleString("zh-CN");
  byId("sun-status").textContent = AVAILABILITY_LABELS[sunStatus] || "未获取";
  byId("plant-count").textContent = Array.isArray(state.plants) ? state.plants.length : "—";
  byId("zombie-count").textContent = Array.isArray(state.zombies) ? state.zombies.length : "—";
  byId("item-count").textContent = Array.isArray(state.items) ? state.items.length : "—";
  byId("sample-time").textContent = state.observed_at_utc ? new Date(state.observed_at_utc).toLocaleTimeString("zh-CN", { hour12: false }) : "等待采样";
  byId("sample-age").textContent = state.observed_at_utc ? `样本 #${state.sample_sequence ?? "—"} · 页面每 ${REFRESH_MS} ms 刷新` : "尚未取得进程快照";
  renderCards(state);
  renderBoard(state);
  renderLanes(state);
  renderItems(state);
  renderGame(state);
  renderCoverage(state);
  renderDiagnostics(state);
  byId("raw-json").textContent = JSON.stringify(state, null, 2);
}

async function fetchState() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderState(await response.json());
  } catch (error) {
    renderState({
      schema_version: 1,
      status: "error",
      valid: false,
      decision_ready: false,
      availability: { sun_balance: "error" },
      errors: [{ scope: "dashboard", message: String(error) }],
      observed_at_utc: null,
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  buildBoard();
  fetchState();
  window.setInterval(fetchState, REFRESH_MS);
});
