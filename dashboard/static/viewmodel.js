/* ============================================================================
 * RuntimeViewModel —— 唯一的 schema 适配层。
 *
 * 设计约束：
 *   1. 只有本文件可以读取后端原始 schema（/api/state、/api/jev-options、
 *      /api/catalog、/api/jev-runtime）。组件层只消费本文件产出的
 *      RuntimeViewModel，不得再出现 `state.availability["zombies..."]` 这类路径。
 *   2. 显示名一律来自 /api/catalog（configs/*.py 是唯一真源），本文件不复制
 *      植物/僵尸/掉落的名称表。
 *   3. mockup 里的 THREAT / ETA / SPD / REASON 在真实 Trace 中不存在，
 *      因此不产出、不伪造。
 *   4. 决策场与候选轨只取“最新那一次决策”（按 job_id 排序）。同一 run 里
 *      不同问题的 group 来自不同 job，混在一起会把多次决策说成一次。
 * ========================================================================= */

(function (root) {
  "use strict";

  /* ------------------------------------------------------------ catalog --- */

  /** 由 /api/catalog 安装的类型目录，按 code 与英文 name 双向可查。 */
  let catalog = { plants: null, zombies: null, items: null };

  function installCatalog(payload) {
    if (!payload || typeof payload !== "object") return;
    catalog = {
      plants: payload.plants || catalog.plants,
      zombies: payload.zombies || catalog.zombies,
      items: payload.items || catalog.items,
    };
  }

  function catalogTables(kind) {
    return catalog[kind === "plant" ? "plants" : kind === "zombie" ? "zombies" : "items"];
  }

  function catalogEntry(kind, code, name) {
    const table = catalogTables(kind);
    if (!table) return null;
    if (Number.isInteger(code) && table.byCode && table.byCode[String(code)]) {
      const byName = table.byName[table.byCode[String(code)]];
      if (byName) return byName;
    }
    if (typeof name === "string" && table.byName && table.byName[name]) return table.byName[name];
    return null;
  }

  /** 显示名：优先目录中文名，回退英文名，再回退占位符。 */
  function localizedType(kind, code, name) {
    const entry = catalogEntry(kind, code, name);
    if (entry) return entry.zh || entry.name;
    if (typeof name === "string" && name) return name;
    return "未知";
  }

  const SCENE_ZH = { loading: "正在加载", menu: "主菜单", level_intro: "关卡介绍", playing: "正在游玩", zombies_win: "僵尸获胜", level_award: "关卡奖励", credits: "制作人员名单", challenge: "挑战场景" };
  const BACKGROUND_ZH = { day: "白天", night: "夜晚", pool: "泳池", fog: "浓雾", roof: "屋顶", boss_arena: "僵王战场", mushroom_garden: "蘑菇花园", greenhouse: "温室", zombiquarium: "僵尸水族馆", tree_of_wisdom: "智慧树" };
  const MODE_ZH = { adventure: "冒险模式", tree_of_wisdom: "智慧树", war_and_peas: "战争与豌豆", wall_nut_bowling: "坚果保龄球", slot_machine: "老虎机", "it's_raining_seeds": "雨中播种", beghouled: "宝石迷阵", invisighoul: "隐形僵尸", seeing_stars: "观星", zombiquarium: "僵尸水族馆", beghouled_twist: "宝石迷阵转转乐", big_trouble_little_zombie: "小鬼大麻烦", portal_combat: "传送门战斗", column_like_you_see: "列队", bobsled_bonanza: "雪橇僵尸大作战", speed: "极速", whack_a_zombie: "打僵尸", last_stand: "最后一搏", pogo_party: "跳跳舞会", boss_rush: "最终 Boss", art_challenge_wall_nut: "美术坚果", sunny_day: "阳光日", grave_danger: "翻土", heavy_rain: "大块头", art_challenge_sunflower: "美术向日葵", air_raid: "空袭", ice_level: "冰冻", zen_garden: "禅境花园", high_gravity: "高重力", graveyard: "墓地危机", shovel: "铲子", stormy_night: "暴风雨夜", bungee_blitz: "蹦极闪电战", squirrel: "松鼠", intro: "开场模式", promotion: "促销模式" };

  function localizedGame(kind, value) {
    const table = kind === "scene" ? SCENE_ZH : kind === "mode" ? MODE_ZH : BACKGROUND_ZH;
    if (typeof value !== "string") return null;
    return table[value] || value;
  }

  /* ------------------------------------------------------------ options --- */

  const CELL_OPTION = /^([^@\s]+)@r(\d+)c(\d+)$/;
  const SHOVEL_OPTION = /^remove@r(\d+)c(\d+)$/;
  const LANE_OPTION = /^lane_(\d+)$/;
  /** 空间问题：选项自带 row/col，构成 5×9 决策场的格点。铲除层问的也是“哪一格”，
   * 所以与放置层同场呈现，不另开图层。 */
  const SPATIAL_QUESTION = /^(plant_target|plant_target_lane_\d+|shovel_target|collect_target)$/;
  const SHOVEL_TARGET_QUESTION = "shovel_target";
  /** 候选轨问题按“最能体现三路选择”的顺序。 */
  const RAIL_PRIORITY = ["construction_intent", "next_construction_type", "plant_target_lane", "should_collect_now"];
  const QUESTION_LABELS = {
    construction_intent: "营建意图",
    next_construction_type: "营建类型",
    plant_target_lane: "目标行",
    should_collect_now: "是否收集",
    should_invest_economy: "经济投入",
    collect_target: "收集目标",
  };
  /** 非植物类选项的中文名（植物名一律查 catalog）。 */
  const CHOICE_ZH = {
    replace: "替换种植", keep: "保留现状", cancel: "取消",
    none_of_the_above: "以上都不是", true: "收集", false: "暂不收集",
    wait: "等待", collect: "收集阳光", plant: "种植", shovel: "铲除",
  };
  const ACTION_ZH = { place_plant: "种植", collect_item: "收集掉落物", collect_sun: "收集阳光", shovel: "铲除", shovel_cell: "铲除", wait: "等待" };
  const STAGE_ZH = { "plant-decision": "种植决策", "collect-decision": "收集决策", "manage-decision": "经营决策" };
  const STATUS_ZH = { selected: "已选定", model_wait: "模型等待", ok: "已选定", wait: "等待" };
  const FALLBACK_ZH = {
    noul_gate_below_threshold: "无候选过阈值（Noul 门限）",
    none_of_the_above: "模型选择弃权",
    no_candidate: "无可用候选",
  };
  const BRANCH_ZH = { plant: "种植分支", collect: "收集分支" };
  /** 展示用缩写：仅少数常用植物有约定写法，其余回退到英文首字母。 */
  const ABBR = {
    sunflower: "SF", peashooter: "PS", wall_nut: "WN", cherry_bomb: "CB", snow_pea: "SP",
    repeater: "RP", tall_nut: "TN", cabbage_pult: "CP", melon_pult: "MP", chomper: "CH",
    jalapeno: "JP", potato_mine: "PM", torchwood: "TW", squash: "SQ", threepeater: "3P",
    gatling_pea: "GP", twin_sunflower: "TS", garlic: "GA", umbrella_leaf: "UL", spikeweed: "SW",
  };

  /** `sunflower@r0c0` → {type,row,col}；其它形状返回 null。 */
  function parseCellOption(optionId) {
    const match = CELL_OPTION.exec(String(optionId || ""));
    if (!match) return null;
    return { type: match[1], row: Number(match[2]), col: Number(match[3]) };
  }

  function optionLabel(optionId) {
    const id = String(optionId || "");
    const cell = parseCellOption(id);
    if (cell) {
      return `${localizedType("plant", null, cell.type)} R${cell.row + 1} C${cell.col + 1}`;
    }
    const lane = LANE_OPTION.exec(id);
    if (lane) return `R${Number(lane[1]) + 1}`;
    if (CHOICE_ZH[id]) return CHOICE_ZH[id];
    return localizedType("plant", null, id);
  }

  /** 缩写：常用植物用约定写法，否则取英文名首字母，最后回退中文名前两字。 */
  function plantAbbr(code, name) {
    const key = typeof name === "string" ? name : (catalogEntry("plant", code, name) || {}).name;
    if (key && ABBR[key]) return ABBR[key];
    if (key) {
      const words = String(key).split(/[^A-Za-z0-9]+/).filter(Boolean);
      if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
      if (words.length === 1 && words[0].length >= 2) return words[0].slice(0, 2).toUpperCase();
    }
    return localizedType("plant", code, name).slice(0, 2);
  }

  function safeNumber(value) {
    return Number.isFinite(value) ? value : null;
  }

  function pct(value) {
    return Number.isFinite(value) ? Math.round(value * 100) : null;
  }

  function cardDisplay(card) {
    const cost = Number.isInteger(card && card.cost) && card.cost >= 0 ? card.cost : null;
    const ready = typeof (card && card.cooldown_ready) === "boolean" ? card.cooldown_ready : null;
    const progress = Number.isInteger(card && card.cooldown_progress_raw) ? card.cooldown_progress_raw : null;
    const total = Number.isInteger(card && card.cooldown_total_raw) ? card.cooldown_total_raw : null;
    let fraction = null;
    if (progress !== null && total !== null && total > 0 && progress >= 0 && progress <= total) {
      fraction = progress / total;
    }
    if (ready === true) fraction = 1;
    return { cost, ready, fraction };
  }

  /* --------------------------------------------------------------- lawn --- */

  function buildLawn(state) {
    const availability = state.availability || {};
    const plantStatus = availability.plants || availability["board.occupancy"] || "unavailable";
    const readable = Array.isArray(state.plants)
      && (plantStatus === "available" || plantStatus === "provisional");
    const boardCells = state.board && Array.isArray(state.board.cells) ? state.board.cells : [];
    const cells = [];
    for (let row = 0; row < 5; row += 1) {
      for (let col = 0; col < 9; col += 1) {
        const raw = boardCells[row] && boardCells[row][col];
        let plant = null;
        if (readable && raw) {
          const occupants = Array.isArray(raw.plants) && raw.plants.length ? raw.plants : [raw];
          plant = occupants.map((occupant) => ({
            typeCode: occupant.type_code,
            typeName: occupant.type_name,
            label: localizedType("plant", occupant.type_code, occupant.type_name),
            abbr: plantAbbr(occupant.type_code, occupant.type_name),
          }));
        }
        cells.push({ row, col, plant });
      }
    }
    return {
      readable,
      reason: readable ? null : (plantStatus === "error" ? "植物读取失败" : "植物未获取"),
      cells,
    };
  }

  /* ------------------------------------------------------------ threats --- */

  function buildThreats(state) {
    const availability = state.availability || {};
    const read = Array.isArray(state.zombies);
    const geometryReadable = availability["zombies.distance_to_house_cells"] === "available";
    const list = [];
    if (read) {
      for (const [index, zombie] of state.zombies.entries()) {
        const row = Number.isInteger(zombie.row) && zombie.row >= 0 && zombie.row <= 4 ? zombie.row : null;
        const col = geometryReadable
          && Number.isInteger(zombie.distance_to_house_cells)
          && zombie.distance_to_house_cells >= 0
          && zombie.distance_to_house_cells <= 8
          ? zombie.distance_to_house_cells : null;
        list.push({
          id: `Z${String(index + 1).padStart(2, "0")}`,
          typeCode: zombie.type_code,
          typeName: zombie.type_name,
          label: localizedType("zombie", zombie.type_code, zombie.type_name),
          row,
          col,
          hp: Number.isInteger(zombie.hp) ? zombie.hp : null,
          totalHp: Number.isInteger(zombie.total_hp) ? zombie.total_hp : null,
          distancePx: safeNumber(zombie.distance_to_house_px),
          x: safeNumber(zombie.x),
          y: safeNumber(zombie.y),
        });
      }
    }
    return { readable: read, geometryReadable, list };
  }

  /**
   * 聚焦僵尸 = 距房屋最近者（distance_to_house_px 最小）。
   * 这是本文件唯一的“选择”而非“读取”：展示的每个数值仍是真实字段。
   */
  function pickFocus(threats) {
    const candidates = threats.list.filter((zombie) => zombie.distancePx !== null);
    if (!candidates.length) return threats.list[0] || null;
    return candidates.reduce((best, z) => (z.distancePx < best.distancePx ? z : best));
  }

  /* ---------------------------------------------------------- inventory --- */

  function buildInventory(state) {
    const read = Array.isArray(state.cards);
    const items = [];
    if (read) {
      for (const card of state.cards) {
        const display = cardDisplay(card);
        const entry = catalogEntry("plant", card.type_code, card.type_name);
        items.push({
          typeCode: card.type_code,
          label: localizedType("plant", card.type_code, card.type_name),
          abbr: plantAbbr(card.type_code, card.type_name),
          role: entry ? entry.role : null,
          cost: display.cost,
          ready: display.ready,
          fraction: display.fraction,
        });
      }
    }
    return {
      read,
      items,
      availableCount: items.filter((item) => item.ready === true).length,
      readyKnown: items.some((item) => item.ready !== null),
    };
  }

  /* --------------------------------------------------------------- game --- */

  function buildGame(state) {
    const game = state.game || {};
    const spawned = Number.isInteger(game.spawned_waves) ? game.spawned_waves : null;
    const total = Number.isInteger(game.total_waves) ? game.total_waves : null;
    return {
      sun: Number.isInteger(state.sun_balance) ? state.sun_balance : null,
      level: game.level ?? null,
      modeLabel: localizedGame("mode", game.mode) || null,
      sceneLabel: localizedGame("scene", game.scene ?? game.phase) || null,
      sceneKey: game.scene ?? game.phase ?? null,
      paused: typeof game.paused === "boolean" ? game.paused : null,
      decisionReady: typeof state.decision_ready === "boolean" ? state.decision_ready : null,
      spawnedWaves: spawned,
      totalWaves: total,
      waveText: spawned === null ? null
        : `${String(spawned).padStart(2, "0")} / ${total === null ? "—" : String(total).padStart(2, "0")}`,
      sampleSequence: Number.isInteger(state.sample_sequence) ? state.sample_sequence : null,
      observedAt: typeof state.observed_at_utc === "string" ? state.observed_at_utc : null,
    };
  }

  /* ----------------------------------------------------------- decision --- */

  /** job id 形如 job-000893，零填充，可直接按数值排序取最新。 */
  function jobRank(jobId) {
    const match = /(\d+)/.exec(String(jobId || ""));
    return match ? Number(match[1]) : -1;
  }

  function normalizeGroups(payload) {
    const questions = payload && Array.isArray(payload.questions) ? payload.questions : [];
    return questions.map((group) => ({
      questionId: String(group.question_id),
      branchId: group.branch_id || null,
      jobId: group.job_id || null,
      choice: typeof group.choice === "string" ? group.choice : null,
      options: (Array.isArray(group.options) ? group.options : []).map((option) => ({
        optionId: String(option.option_id),
        label: optionLabel(option.option_id),
        probability: safeNumber(option.probability),
        executed: option.executed === true,
      })),
    }));
  }

  /**
   * 一条候选轨只放“一次决策”的问题。轨内选项按真实概率降序，过滤近零噪声，
   * 但被选中的选项永远保留，否则会出现“选中项看不见”的假象。
   */
  /** 候选轨最多 3 条、每条最多 3 项：300px 高的决策空间内不出现滚动，
   * 被截断的项数如实计数（`hiddenCount`），不假装候选就这么几个。 */
  const MAX_RAILS = 3;
  const MAX_RAIL_OPTIONS = 3;

  function buildRails(groups) {
    const ordered = [
      ...RAIL_PRIORITY.map((id) => groups.find((group) => group.questionId === id)).filter(Boolean),
      ...groups.filter((group) => !RAIL_PRIORITY.includes(group.questionId)),
    ];
    const rails = [];
    for (const group of ordered) {
      if (rails.length >= MAX_RAILS) break;
      if (SPATIAL_QUESTION.test(group.questionId)) continue;
      const all = group.options.map((option) => ({
        ...option,
        selected: group.choice !== null && group.choice === option.optionId,
      }));
      if (!all.length) continue;
      const significant = all.filter((option) => option.selected || (option.probability ?? 0) >= 0.005);
      const ranked = (significant.length ? significant : all)
        .sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1));
      rails.push({
        questionId: group.questionId,
        label: QUESTION_LABELS[group.questionId] || group.questionId,
        options: ranked.slice(0, MAX_RAIL_OPTIONS),
        optionCount: all.length,
        hiddenCount: Math.max(0, ranked.length - MAX_RAIL_OPTIONS),
      });
    }
    return rails;
  }

  /**
   * 哪一条空间问题才是真正拍板的那条：
   *   1. 这次决策真的下发了铲除时，铲除层拍板（铲除优先于同一次请求里的放置）；
   *   2. 否则直接问全局格点的 plant_target 一定权威；
   *   3. 再否则若 plant_target_lane 选了 lane_N，则只有 plant_target_lane_N 权威；
   *   4. 只有铲除层而没有放置层时（放置层为空），铲除层就是唯一的拍板问题。
   * 其余空间问题只提供概率点，不得点亮“已选中”，否则一次决策会同时出现多个选中格。
   */
  function pickAuthoritativeQuestion(groups, decision) {
    const hasShovel = groups.some((group) => group.questionId === SHOVEL_TARGET_QUESTION);
    const decidedShovel = Boolean(decision && decision.target && decision.target.action === "shovel_cell");
    if (hasShovel && decidedShovel) return SHOVEL_TARGET_QUESTION;
    if (groups.some((group) => group.questionId === "plant_target")) return "plant_target";
    const lane = groups.find((group) => group.questionId === "plant_target_lane"
      && LANE_OPTION.test(String(group.choice || "")));
    if (lane) return `plant_target_lane_${Number(LANE_OPTION.exec(lane.choice)[1])}`;
    return hasShovel ? SHOVEL_TARGET_QUESTION : null;
  }

  /**
   * 同一次成功铲除的执行事实：只有同一 action_result 的边界状态为 success、动作为
   * shovel_cell，且行列精确一致时才算证明。失败、未证实、旧 job 的铲除都不点亮。
   */
  function shovelExecution(execution) {
    if (!execution || execution.boundary_status !== "success") return null;
    const target = execution.target;
    if (!target || target.action !== "shovel_cell") return null;
    if (!Number.isInteger(target.row) || !Number.isInteger(target.col)) return null;
    return { row: target.row, col: target.col };
  }

  /** Decision Field = 与草坪同构的 5×9 格点，每格一票“种在这里”或“铲这里”。 */
  function buildField(groups, authoritative, execution) {
    const byCell = new Map();
    const sources = [];
    const shovelProof = shovelExecution(execution);
    for (const group of groups) {
      if (!SPATIAL_QUESTION.test(group.questionId)) continue;
      if (!group.options.length) continue;
      sources.push(group.questionId);
      const authoritativeGroup = group.questionId === authoritative;
      for (const option of group.options) {
        const cell = parseCellOption(option.optionId);
        if (!cell) continue;
        const shovel = SHOVEL_OPTION.test(option.optionId);
        const key = `${cell.row}:${cell.col}`;
        const existing = byCell.get(key);
        const selected = authoritativeGroup && group.choice === option.optionId;
        const better = !existing
          || (selected && !existing.selected)
          || (selected === existing.selected && (option.probability ?? -1) > (existing.probability ?? -1));
        if (!better) continue;
        // 铲除的已执行标记与服务器对放置层同规：同一 job、边界 success、目标精确映射；
        // 铲除格读作铲除，不冒充植物。
        const shovelExecuted = shovel && shovelProof !== null
          && execution.job_id === group.jobId
          && shovelProof.row === cell.row && shovelProof.col === cell.col;
        byCell.set(key, {
          row: cell.row,
          col: cell.col,
          optionId: option.optionId,
          typeLabel: shovel ? ACTION_ZH.shovel_cell : localizedType("plant", null, cell.type),
          probability: option.probability,
          selected,
          executed: option.executed === true || shovelExecuted,
        });
      }
    }
    return { readable: byCell.size > 0, sources, authoritative, cells: [...byCell.values()] };
  }

  /** 执行目标可能是植物（种植）也可能是掉落物（收集），标签查对应目录。 */
  function localizedActionTarget(action, typeName) {
    if (!typeName) return null;
    return action === "place_plant"
      ? localizedType("plant", null, typeName)
      : localizedType("item", null, typeName);
  }

  function buildSelected(decision, execution) {
    if (!decision) return { known: false, executed: null };
    const target = decision.target && typeof decision.target === "object" ? decision.target : null;
    const row = target && Number.isInteger(target.row) ? target.row : null;
    const col = target && Number.isInteger(target.col) ? target.col : null;
    const executed = execution && execution.boundary_status ? {
      boundaryStatus: execution.boundary_status,
      outcome: execution.outcome,
      actionLabel: execution.target && execution.target.action
        ? (ACTION_ZH[execution.target.action] || execution.target.action) : null,
      typeLabel: execution.target
        ? localizedActionTarget(execution.target.action, execution.target.type_name) : null,
      elapsedMs: execution.execution_elapsed_ms,
    } : null;
    return {
      known: true,
      jobId: decision.job_id || null,
      stageLabel: decision.stage_id ? (STAGE_ZH[decision.stage_id] || decision.stage_id) : null,
      statusLabel: decision.status ? (STATUS_ZH[decision.status] || decision.status) : null,
      intentLabel: decision.intent ? (CHOICE_ZH[decision.intent] || decision.intent) : null,
      actionLabel: target && target.action ? (ACTION_ZH[target.action] || target.action) : null,
      typeLabel: target && target.type_name ? localizedType("plant", null, target.type_name) : null,
      row,
      col,
      cellText: row === null || col === null ? null : `R${row + 1} C${col + 1}`,
      rule: decision.target_choice_rule || null,
      fallbackReason: decision.fallback_reason
        ? (FALLBACK_ZH[decision.fallback_reason] || decision.fallback_reason) : null,
      fallbackCode: decision.fallback_reason || null,
      latencyMs: decision.latency_ms,
      executed,
    };
  }

  function buildDecision(payload) {
    const groups = normalizeGroups(payload);
    if (!groups.length) {
      return {
        readable: false, jobId: null, branchLabel: null, railJobLabel: null,
        rails: [], field: { readable: false, sources: [], cells: [] },
        selected: buildSelected(payload && payload.decision, payload && payload.execution),
      };
    }
    const newestRank = groups.reduce((best, group) => Math.max(best, jobRank(group.jobId)), -1);
    const current = groups.filter((group) => jobRank(group.jobId) === newestRank);
    // 最新的决策常常是收集分支（没有空间问题）。决策场取“最近一次带格点的决策”，
    // 并把它的 job/分支如实标出来，避免把多次决策说成一次。
    let fieldGroups = current.filter((group) => SPATIAL_QUESTION.test(group.questionId));
    if (!fieldGroups.length) {
      const ranks = [...new Set(groups.map((group) => jobRank(group.jobId)))].sort((a, b) => b - a);
      for (const rank of ranks) {
        const candidate = groups.filter((group) => jobRank(group.jobId) === rank
          && SPATIAL_QUESTION.test(group.questionId));
        if (candidate.length) {
          fieldGroups = candidate;
          break;
        }
      }
    }
    const fieldJobId = fieldGroups.length ? fieldGroups[0].jobId : null;
    const fieldBranch = fieldGroups.length ? fieldGroups[0].branchId : null;
    // 权威问题可能本身不是空间问题（plant_target_lane 只选行），所以必须在
    // 同一个 job 的**全部**问题里判定，而不是只在空间子集里找。
    // 权威问题可能本身不是空间问题（plant_target_lane 只选行），所以必须在
    // 同一个 job 的**全部**问题里判定，而不是只在空间子集里找。
    const fieldJobRank = fieldJobId === null ? null : jobRank(fieldJobId);
    const fieldJobGroups = fieldJobRank === null ? [] : groups.filter((group) => jobRank(group.jobId) === fieldJobRank);
    // 决策与执行摘要只对同一 job 的格点场有效：旧 job 的铲除不得点亮当前格点。
    const latestDecision = (payload && payload.decision) || null;
    const latestExecution = (payload && payload.execution) || null;
    const fieldDecision = latestDecision && fieldJobId !== null && latestDecision.job_id === fieldJobId
      ? latestDecision : null;
    const fieldExecution = latestExecution && fieldJobId !== null && latestExecution.job_id === fieldJobId
      ? latestExecution : null;
    const authoritative = pickAuthoritativeQuestion(fieldJobGroups, fieldDecision);
    const field = buildField(fieldJobGroups, authoritative, fieldExecution);
    const rails = buildRails(current);
    const selected = buildSelected(payload && payload.decision, payload && payload.execution);
    /*
     * SCORE = JEV 实际选中那一项的真实概率。
     * 种植决策用候选场里被选中格的概率；收集/等待类没有格点，回退到意图层里
     * 真正被选中的那个选项的概率。两者都是 Trace 真值，不为凑字段而造数。
     */
    const chosenCell = field.cells.find((cell) => cell.selected);
    if (chosenCell && chosenCell.probability !== null) {
      selected.score = chosenCell.probability;
    } else {
      const firstRail = rails[0];
      const chosen = firstRail ? firstRail.options.find((option) => option.selected) : null;
      selected.score = chosen ? chosen.probability : null;
    }
    const currentBranch = current[0] ? current[0].branchId : null;
    return {
      readable: true,
      jobId: current[0] ? current[0].jobId : null,
      branchLabel: currentBranch ? (BRANCH_ZH[currentBranch] || currentBranch) : null,
      railJobLabel: current[0] ? current[0].jobId : null,
      rails,
      field: {
        ...field,
        jobId: fieldJobId,
        branchLabel: fieldBranch ? (BRANCH_ZH[fieldBranch] || fieldBranch) : null,
      },
      selected,
    };
  }

  /* ------------------------------------------------------------- public --- */

  function buildRuntimeViewModel(raw) {
    const input = raw || {};
    const state = input.state || {};
    const threats = buildThreats(state);
    return {
      game: buildGame(state),
      lawn: buildLawn(state),
      inventory: buildInventory(state),
      threats,
      currentTarget: pickFocus(threats),
      decision: buildDecision(input.options),
      runtime: input.runtime || { state: "unknown" },
      raw: state,
    };
  }

  root.JEVViewModel = {
    buildRuntimeViewModel,
    installCatalog,
    localizedType,
    localizedGame,
    optionLabel,
    parseCellOption,
    plantAbbr,
    pct,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
