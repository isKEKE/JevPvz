"use strict";

const REFRESH_MS = 500;
const AVAILABILITY_LABELS = {
  available: "已核验",
  provisional: "待动态核验",
  unavailable: "未获取",
  error: "读取错误",
  partial: "部分字段未获取",
};
const FIELD_LABELS = {
  "sun_balance": "阳光余额",
  "plants": "植物列表",
  "zombies": "僵尸列表",
  "zombies.hp": "僵尸 HP",
  "zombies.distance_to_house_px": "僵尸到房屋距离（像素）",
  "zombies.distance_to_house_cells": "僵尸到房屋格距",
  "lanes.nearest_zombie_distance_to_house_px": "行内最近僵尸距离（像素）",
  "lanes.nearest_zombie_distance_to_house_cells": "行内最近僵尸格距",
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
const PLANT_ZH = ["豌豆射手","向日葵","樱桃炸弹","坚果","土豆地雷","寒冰射手","大嘴花","双发射手","小喷菇","阳光菇","大喷菇","墓碑吞噬者","魅惑菇","胆小菇","寒冰菇","毁灭菇","睡莲","窝瓜","三线射手","缠绕海草","火爆辣椒","地刺","火炬树桩","高坚果","海蘑菇","路灯花","仙人掌","三叶草","裂荚射手","杨桃","南瓜头","磁力菇","卷心菜投手","花盆","玉米投手","咖啡豆","大蒜","叶子保护伞","金盏花","西瓜投手","机枪射手","双子向日葵","忧郁菇","香蒲","冰西瓜","吸金磁","地刺王","玉米加农炮","模仿者"];
const ZOMBIE_ZH = ["普通僵尸","旗帜僵尸","路障僵尸","撑杆跳僵尸","铁桶僵尸","读报僵尸","铁门僵尸","橄榄球僵尸","舞王僵尸","伴舞僵尸","救生圈僵尸","潜水僵尸","冰车僵尸","雪橇僵尸","海豚骑士僵尸","玩偶匣僵尸","气球僵尸","矿工僵尸","跳跳僵尸","雪人僵尸","蹦极僵尸","扶梯僵尸","投石车僵尸","巨人僵尸","小鬼僵尸","僵王博士","豌豆射手僵尸","坚果僵尸","火爆辣椒僵尸","机枪射手僵尸","窝瓜僵尸","高坚果僵尸","红眼巨人僵尸","自定义形象僵尸"];
const ITEM_ZH = ["无","银币","金币","钻石","阳光","小阳光","大阳光","关卡种子包","奖杯","铲子","植物图鉴","车钥匙","花瓶","水壶","玉米卷","便条","可使用种子包","植物礼盒","奖励钱袋","奖励礼盒","钻石袋奖励","银向日葵奖杯","金向日葵奖杯","巧克力","巧克力奖励","小游戏礼盒","解谜模式礼盒","生存模式礼盒"];
const SCENE_ZH = {loading:"正在加载",menu:"主菜单",level_intro:"关卡介绍",playing:"正在游玩",zombies_win:"僵尸获胜",level_award:"关卡奖励",credits:"制作人员名单",challenge:"挑战场景"};
const BACKGROUND_ZH = {day:"白天",night:"夜晚",pool:"泳池",fog:"浓雾",roof:"屋顶",boss_arena:"僵王战场",mushroom_garden:"蘑菇花园",greenhouse:"温室",zombiquarium:"僵尸水族馆",tree_of_wisdom:"智慧树"};
const MODE_ZH = {adventure:"冒险模式",tree_of_wisdom:"智慧树",war_and_peas:"战争与豌豆",wall_nut_bowling:"坚果保龄球",slot_machine:"老虎机","it's_raining_seeds":"雨中播种",beghouled:"宝石迷阵",invisighoul:"隐形僵尸",seeing_stars:"观星",zombiquarium:"僵尸水族馆",beghouled_twist:"宝石迷阵转转乐",big_trouble_little_zombie:"小鬼大麻烦",portal_combat:"传送门战斗",column_like_you_see:"列队",bobsled_bonanza:"雪橇僵尸大作战",speed:"极速",whack_a_zombie:"打僵尸",last_stand:"最后一搏",pogo_party:"跳跳舞会",boss_rush:"最终 Boss",art_challenge_wall_nut:"美术坚果",sunny_day:"阳光日",grave_danger:"翻土",heavy_rain:"大块头",art_challenge_sunflower:"美术向日葵",air_raid:"空袭",ice_level:"冰冻",zen_garden:"禅境花园",high_gravity:"高重力",graveyard:"墓地危机",shovel:"铲子",stormy_night:"暴风雨夜",bungee_blitz:"蹦极闪电战",squirrel:"松鼠",intro:"开场模式",promotion:"促销模式"};
function localizedType(kind, code, name) {
  const map = kind === "plant" ? PLANT_ZH : kind === "zombie" ? ZOMBIE_ZH : ITEM_ZH;
  return name && name !== "unknown" ? (map[code] || `未知${kind === "plant" ? "植物" : kind === "zombie" ? "僵尸" : "掉落物"} #${code}`) : `未知${kind === "plant" ? "植物" : kind === "zombie" ? "僵尸" : "掉落物"} #${code ?? "?"}`;
}
function localizedGame(kind, value) {
  if (kind === "scene") return SCENE_ZH[value] || `未知场景 (${value})`;
  if (kind === "background") return BACKGROUND_ZH[value] || `未知场地 (${value})`;
  if (kind === "mode") {
    const stage = /^(survival_(?:normal|hard|endless)_stage)_(\d+)$/.exec(value || "");
    if (stage) return `生存模式（${stage[1].endsWith("normal_stage") ? "普通" : stage[1].endsWith("hard_stage") ? "困难" : "无尽"}，第 ${stage[2]} 阶段）`;
    const vase = /^vasebreaker_stage_(\d+)$/.exec(value || "");
    const iz = /^i_zombie_stage_(\d+)$/.exec(value || "");
    return vase ? `砸罐子（第 ${vase[1]} 关）` : iz ? `我是僵尸（第 ${iz[1]} 关）` : MODE_ZH[value] || `未知模式 (${value})`;
  }
  return value;
}

function byId(id) { return document.getElementById(id); }

function makeBadge(status) {
  const badge = document.createElement("span");
  badge.className = `state-badge ${status || "unavailable"}`;
  badge.textContent = AVAILABILITY_LABELS[status] || "未获取";
  return badge;
}

function cardGroupStatus(availability) {
  const statuses = ["cards.cost", "cards.cooldown_ready", "cards.usable"]
    .map((key) => availability?.[key] || "unavailable");
  if (statuses.every((status) => status === "available")) return "available";
  if (statuses.includes("error")) return "error";
  if (statuses.includes("provisional")) return "provisional";
  if (statuses.includes("available")) return "partial";
  return "unavailable";
}

function cardDisplayModel(card, availability) {
  const cost = Number.isInteger(card?.cost) && card.cost >= 0 ? card.cost : null;
  const costStatus = availability?.["cards.cost"] || "unavailable";
  const costText = cost === null
    ? `费用：${costStatus === "error" ? "读取错误" : "未获取"}`
    : costStatus === "available" ? `费用：${cost} 阳光`
      : costStatus === "provisional" ? `费用（暂定）：${cost} 阳光`
        : `费用候选：${cost} 阳光`;

  const readiness = typeof card?.cooldown_ready === "boolean"
    ? (card.cooldown_ready ? "已就绪" : "冷却中")
    : "未获取";
  const usable = typeof card?.usable === "boolean"
    ? (card.usable ? "是" : "否")
    : "未知";
  return {
    costText,
    stateText: `冷却：${readiness} · 卡牌可选：${usable}`,
  };
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

function zombieGridPosition(zombie, availability) {
  if (availability?.["zombies.distance_to_house_cells"] !== "available") return null;
  if (!Number.isInteger(zombie?.row) || zombie.row < 0 || zombie.row > 4) return null;
  if (!Number.isInteger(zombie.distance_to_house_cells)
      || zombie.distance_to_house_cells < 0 || zombie.distance_to_house_cells > 8) return null;
  return {
    left: ((zombie.distance_to_house_cells + 0.5) / 9) * 100,
    top: (zombie.row + 0.5) * 20,
    gridIndex: zombie.distance_to_house_cells,
  };
}

function zombiePositionsForState(state) {
  const zombies = Array.isArray(state.zombies) ? state.zombies : [];
  const availability = state.availability || {};
  return zombies.map((zombie) => zombieGridPosition(zombie, availability));
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
          const name = localizedType("plant", occupant.type_code, occupant.type_name);
          cell.append(makeElement("span", "plant-name", name));
        }
        cell.title = `${occupants.map((occupant) => `${localizedType("plant", occupant.type_code, occupant.type_name)} · 类型码 ${occupant.type_code}`).join("；")} · 第 ${row + 1} 行第 ${col + 1} 列`;
      } else {
        cell.append(makeElement("span", "empty-dot", "·"));
        cell.title = "当前无植物；可种规则未获取";
      }
    }
  }
  const layer = byId("zombie-layer");
  layer.replaceChildren();
  const zombies = Array.isArray(state.zombies) ? state.zombies : [];
  const positions = zombiePositionsForState(state);
  let markerCount = 0;
  for (const [index, zombie] of zombies.entries()) {
    const position = positions[index];
    if (!position) continue;
    const marker = makeElement("span", "zombie-marker", `Z${zombie.type_code}`);
    marker.style.left = `${position.left}%`;
    marker.style.top = `${position.top}%`;
    marker.setAttribute("role", "img");
    const typeName = localizedType("zombie", zombie.type_code, zombie.type_name);
    const pixelDistance = Number.isFinite(zombie.distance_to_house_px)
      ? `，距房屋 ${zombie.distance_to_house_px} 像素` : "";
    marker.setAttribute("aria-label", `${typeName}，第 ${zombie.row + 1} 行，房屋侧第 ${position.gridIndex + 1} 列（格距 ${position.gridIndex}）${pixelDistance}；不代表植物格占用`);
    marker.title = `${typeName} · 第 ${zombie.row + 1} 行 · 房屋侧第 ${position.gridIndex + 1} 列（格距 ${position.gridIndex}）${pixelDistance} · 不代表植物格占用`;
    layer.append(marker);
    markerCount += 1;
  }
  byId("overlay-status").textContent = markerCount
    ? "僵尸按房屋侧格距标记到对应列；标记仅为位置区间，不代表占据植物格。"
    : "当前无可用格距位置；未绘制标记，右侧保留逐行详情。";
}

function renderCards(state) {
  const container = byId("cards-list");
  container.replaceChildren();
  const cards = Array.isArray(state.cards) ? state.cards : null;
  const oldBadge = byId("cards-status");
  const statusBadge = makeBadge(cardGroupStatus(state.availability));
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
    const typeLabel = localizedType("plant", card.type_code, card.type_name);
    item.append(makeElement("strong", "seed-type", Number.isInteger(card.type_code) ? `${typeLabel} · #${card.type_code}` : "类型未知"));
    const display = cardDisplayModel(card, state.availability);
    item.append(makeElement("span", "seed-cost", display.costText));
    item.append(makeElement("span", "seed-cooldown", display.stateText));
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
    if (laneZombies.length) {
      const pixelDistance = Number.isFinite(lane?.nearest_zombie_distance_to_house_px)
        ? `${lane.nearest_zombie_distance_to_house_px} px` : "像素距离未获取";
      const gridDistance = Number.isInteger(lane?.nearest_zombie_distance_to_house_cells)
        ? `距屋 ${lane.nearest_zombie_distance_to_house_cells} 格` : "格距未获取";
      heading.append(makeElement("span", "lane-distance", `最近：${pixelDistance} · ${gridDistance}`));
    }
    article.append(heading);
    if (!laneZombies.length) {
      article.append(makeElement("p", "lane-empty", "当前没有"));
    }
    for (const zombie of laneZombies) {
      const detail = makeElement("div", "zombie-detail");
      const typeLabel = localizedType("zombie", zombie.type_code, zombie.type_name);
      detail.append(makeElement("strong", "zombie-name", `${typeLabel} · #${zombie.type_code}`));
      detail.append(makeElement("span", "", `X ${zombie.x} · Y ${zombie.y}`));
      if (Number.isFinite(zombie.distance_to_house_px) && Number.isInteger(zombie.distance_to_house_cells)) {
        detail.append(makeElement("span", "", `距房屋 ${zombie.distance_to_house_px} px · 格距 ${zombie.distance_to_house_cells}（房屋侧第 ${zombie.distance_to_house_cells + 1} 列）`));
      }
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
    const typeLabel = localizedType("item", item.type_code, item.type_name);
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
    ["场景", codeValue(localizedGame("scene", game.scene ?? game.phase), game.scene_code, "未知场景"), "game.scene"],
    ["模式", codeValue(localizedGame("mode", game.mode), game.mode_code, "未知模式"), "game.mode"],
    ["场地", codeValue(localizedGame("background", game.background), game.background_code, "未知场地"), "game.background"],
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
  const game = state.game || {};
  byId("level-value").textContent = game.level ?? "—";
  byId("wave-value").textContent = game.spawned_waves === null || game.spawned_waves === undefined
    ? "—" : `${game.spawned_waves} / ${game.total_waves ?? "?"}`;
  byId("scene-value").textContent = [localizedGame("scene", game.scene ?? game.phase), localizedGame("mode", game.mode)]
    .filter((value) => value && !value.startsWith("未知")).join(" · ") || "—";
  byId("run-state-value").textContent = game.paused === true ? "已暂停"
    : game.level_complete === true ? "已通关"
      : game.paused === false && game.level_complete === false ? "进行中" : "状态未知";
  renderCards(state);
  renderBoard(state);
  renderLanes(state);
  renderItems(state);
  renderGame(state);
  renderCoverage(state);
  renderDiagnostics(state);
  byId("raw-json").textContent = JSON.stringify(state, null, 2);
  byId("copy-raw-json").disabled = false;
}

async function copyRawStateJson() {
  const text = byId("raw-json").textContent;
  const status = byId("raw-copy-status");
  try {
    const clipboard = globalThis.navigator?.clipboard;
    if (!clipboard?.writeText) throw new Error("Clipboard API unavailable");
    await clipboard.writeText(text);
    status.textContent = "已复制";
  } catch {
    status.textContent = "复制失败，请检查浏览器剪贴板权限";
  }
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

if (typeof module !== "undefined" && module.exports) module.exports = {
  cardDisplayModel,
  cardGroupStatus,
  zombieGridPosition,
  zombiePositionsForState,
};

if (typeof document !== "undefined") document.addEventListener("DOMContentLoaded", () => {
  buildBoard();
  byId("copy-raw-json").addEventListener("click", copyRawStateJson);
  document.querySelectorAll("[data-state-view]").forEach((button) => button.addEventListener("click", () => {
    const jsonMode = button.dataset.stateView === "json";
    byId("dashboard-structured").hidden = jsonMode;
    byId("dashboard-json").hidden = !jsonMode;
    document.querySelectorAll("[data-state-view]").forEach((item) => {
      const selected = item === button;
      item.classList.toggle("selected", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
  }));
  document.querySelectorAll("[data-observation-tab]").forEach((button) => button.addEventListener("click", () => {
    const selectedTab = button.dataset.observationTab;
    document.querySelectorAll("[data-observation-tab]").forEach((item) => {
      const selected = item === button;
      item.classList.toggle("selected", selected);
      item.setAttribute("aria-selected", String(selected));
    });
    document.querySelectorAll("[data-observation-pane]").forEach((pane) => {
      const selected = pane.dataset.observationPane === selectedTab;
      pane.hidden = !selected;
      pane.classList.toggle("active", selected);
    });
  }));
  fetchState();
  window.setInterval(fetchState, REFRESH_MS);
});
