/* 录制页视觉预览 + 排版量测：用固定样本喂渲染层，不依赖实机。
 *
 * 样本情景是“一次成功的种植决策”，也就是录制要讲的那个故事。
 * 用法：
 *   VIEW_WIDTH=1920 VIEW_HEIGHT=1080 node tools/dev-view.mjs \
 *     "http://127.0.0.1:8899/" out.png "$(cat tools/fixtures/recording-probe.js)"
 */

(function () {
  // 冻结轮询，避免真实 fetch 覆盖样本。
  window.fetch = () => new Promise(() => {});

  const CATALOG = {
    plants: { entries: [], byCode: {}, byName: {} },
    zombies: { entries: [], byCode: {}, byName: {} },
    items: { entries: [], byCode: {}, byName: {} },
  };
  const PLANTS = [[0, "peashooter", "豌豆射手", 100], [1, "sunflower", "向日葵", 50],
    [2, "cherry_bomb", "樱桃炸弹", 150], [3, "wall_nut", "坚果", 50], [4, "potato_mine", "土豆地雷", 25],
    [5, "snow_pea", "寒冰射手", 175], [6, "chomper", "大嘴花", 150], [7, "repeater", "双发射手", 200],
    [31, "threepeater", "三线射手", 325], [32, "cabbage_pult", "卷心菜投手", 100]];
  for (const [code, name, zh, cost] of PLANTS) {
    const entry = { code, name, zh, cost, role: null };
    CATALOG.plants.entries.push(entry);
    CATALOG.plants.byCode[String(code)] = name;
    CATALOG.plants.byName[name] = entry;
  }
  for (const [code, name, zh] of [[0, "normal_zombie", "普通僵尸"], [1, "flag_zombie", "旗帜僵尸"],
    [2, "conehead_zombie", "路障僵尸"]]) {
    const entry = { code, name, zh };
    CATALOG.zombies.entries.push(entry);
    CATALOG.zombies.byCode[String(code)] = name;
    CATALOG.zombies.byName[name] = entry;
  }
  CATALOG.items.byName.reward_money_bag = { code: 18, name: "reward_money_bag", zh: "奖励钱袋" };

  const cells = Array.from({ length: 5 }, () => Array.from({ length: 9 }, () => null));
  const put = (row, col, code, name) => { cells[row][col] = { plants: [{ type_code: code, type_name: name }] }; };
  put(0, 2, 1, "sunflower"); put(1, 2, 1, "sunflower"); put(2, 2, 1, "sunflower");
  put(3, 2, 1, "sunflower"); put(4, 2, 6, "chomper"); put(1, 4, 1, "sunflower");

  const STATE = {
    schema_version: 2, observed_at_utc: "2026-09-28T15:36:11.579+00:00", sample_sequence: 272,
    status: "ok", valid: true, decision_ready: true, sun_balance: 250,
    game: { level: "1-4", mode: "adventure", scene: "playing", spawned_waves: 5, total_waves: 20, paused: false },
    board: { rows: 5, cols: 9, cells },
    plants: [], lanes: [], items: [],
    zombies: [
      { row: 1, type_code: 0, type_name: "normal_zombie", hp: 170, total_hp: 170, distance_to_house_px: 338, distance_to_house_cells: 4, x: 338, y: 150 },
      { row: 0, type_code: 0, type_name: "normal_zombie", hp: 270, total_hp: 270, distance_to_house_px: 476, distance_to_house_cells: 6, x: 476, y: 50 },
      { row: 3, type_code: 2, type_name: "conehead_zombie", hp: 370, total_hp: 370, distance_to_house_px: 612, distance_to_house_cells: 7, x: 612, y: 250 },
      { row: 4, type_code: 0, type_name: "normal_zombie", hp: 270, total_hp: 270, distance_to_house_px: 27, distance_to_house_cells: 0, x: 27, y: 450 },
    ],
    cards: [
      { type_code: 31, cost: 325, cooldown_ready: true, cooldown_progress_raw: 0, cooldown_total_raw: 0 },
      { type_code: 4, cost: 25, cooldown_ready: true, cooldown_progress_raw: 0, cooldown_total_raw: 0 },
      { type_code: 6, cost: 150, cooldown_ready: false, cooldown_progress_raw: 900, cooldown_total_raw: 1500 },
      { type_code: 0, cost: 100, cooldown_ready: true, cooldown_progress_raw: 0, cooldown_total_raw: 0 },
      { type_code: 1, cost: 50, cooldown_ready: true, cooldown_progress_raw: 0, cooldown_total_raw: 0 },
      { type_code: 2, cost: 150, cooldown_ready: true, cooldown_progress_raw: 0, cooldown_total_raw: 0 },
      { type_code: 7, cost: 200, cooldown_ready: false, cooldown_progress_raw: 480, cooldown_total_raw: 1500 },
      { type_code: 3, cost: 50, cooldown_ready: true, cooldown_progress_raw: 0, cooldown_total_raw: 0 },
      { type_code: 32, cost: 100, cooldown_ready: true, cooldown_progress_raw: 0, cooldown_total_raw: 0 },
      { type_code: 5, cost: 175, cooldown_ready: true, cooldown_progress_raw: 0, cooldown_total_raw: 0 },
    ],
    availability: {
      plants: "available", zombies: "available", "zombies.distance_to_house_cells": "available",
      cards: "available", items: "available", "game.scene": "available",
    },
  };

  const lane1 = [[1, 3, "sunflower", 0.72], [1, 3, "repeater", 0.09], [1, 5, "wall_nut", 0.06],
    [0, 3, "sunflower", 0.05], [1, 4, "peashooter", 0.04], [1, 6, "sunflower", 0.02],
    [2, 3, "sunflower", 0.01], [4, 4, "chomper", 0.01]];
  const lane2 = [[2, 3, "sunflower", 0.31], [2, 4, "wall_nut", 0.18], [2, 5, "peashooter", 0.12],
    [2, 2, "sunflower", 0.09], [3, 6, "repeater", 0.06]];
  const lane0 = [[0, 4, "sunflower", 0.22], [0, 5, "peashooter", 0.11]];
  const toOptions = (list) => list.map(([r, c, type, probability]) => ({
    option_id: `${type}@r${r}c${c}`, probability, executed: false,
  }));
  const OPTIONS = {
    status: "ok", schema_version: 2, run_id: "a1b2c3d4e5f60718293a4b5c6d7e8f90",
    questions: [
      { question_id: "construction_intent", branch_id: "plant", job_id: "job-000900", choice: "replace",
        options: toOptions([[-1, -1, "replace", 0.54]]).length ? [
          { option_id: "replace", probability: 0.54, executed: false },
          { option_id: "keep", probability: 0.36, executed: false },
          { option_id: "cancel", probability: 0.10, executed: false }] : [] },
      { question_id: "next_construction_type", branch_id: "plant", job_id: "job-000900", choice: "sunflower",
        options: [
          { option_id: "sunflower", probability: 0.61, executed: false },
          { option_id: "repeater", probability: 0.22, executed: false },
          { option_id: "wall_nut", probability: 0.10, executed: false },
          { option_id: "peashooter", probability: 0.04, executed: false },
          { option_id: "cabbage_pult", probability: 0.02, executed: false },
          { option_id: "chomper", probability: 0.01, executed: false }] },
      { question_id: "plant_target_lane", branch_id: "plant", job_id: "job-000900", choice: "lane_1",
        options: [
          { option_id: "lane_1", probability: 0.60, executed: false },
          { option_id: "lane_2", probability: 0.19, executed: false },
          { option_id: "lane_0", probability: 0.12, executed: false },
          { option_id: "lane_3", probability: 0.05, executed: false },
          { option_id: "lane_4", probability: 0.03, executed: false },
          { option_id: "none_of_the_above", probability: 0.01, executed: false }] },
      { question_id: "plant_target_lane_1", branch_id: "plant", job_id: "job-000900",
        choice: "sunflower@r1c3", options: toOptions(lane1) },
      { question_id: "plant_target_lane_2", branch_id: "plant", job_id: "job-000900",
        choice: "sunflower@r2c3", options: toOptions(lane2) },
      { question_id: "plant_target_lane_0", branch_id: "plant", job_id: "job-000900",
        choice: "sunflower@r0c4", options: toOptions(lane0) },
    ],
    decision: {
      job_id: "job-000900", branch_id: "plant", stage_id: "plant-decision", status: "selected",
      intent: "plant", effective_action: "plant",
      target: { action: "place_plant", type_name: "sunflower", row: 1, col: 3 },
      target_choice_rule: "argmax", fallback_reason: null, model: "jev-1.13.0",
      latency_ms: 412, sample_sequence: 272, event_sequence: 902,
      timestamp_utc: "2026-09-28T15:36:12.100Z",
      choices: { construction_intent: "replace", next_construction_type: "sunflower", plant_target_lane_1: "sunflower@r1c3" },
    },
    execution: {
      job_id: "job-000900", boundary_status: "success", outcome: "executed", effective_action: "plant",
      target: { action: "place_plant", type_name: "sunflower", row: 1, col: 3 },
      execution_elapsed_ms: 318, sample_sequence: 273, event_sequence: 903,
      timestamp_utc: "2026-09-28T15:36:12.420Z",
    },
  };
  const RUNTIME = { state: "running", message: "JEV 循环运行中", can_start: false, can_stop: true, game_ready: true, pid: 4821, exit_code: null };

  JEVViewModel.installCatalog(CATALOG);
  window.JEVRecording.apply({ catalog: CATALOG, state: STATE, options: OPTIONS, runtime: RUNTIME });

  const svg = document.getElementById("field-svg");
  const trace = document.getElementById("trace");

  const box = (id) => document.getElementById(id).getBoundingClientRect();
  const stageTexts = {};
  for (const stage of document.querySelectorAll(".rt-stage")) {
    const key = stage.dataset.stage;
    const body = stage.querySelector(".stage-body");
    stageTexts[key] = body ? body.textContent.trim().replace(/\s+/g, " ").slice(0, 90) : "(field)";
  }
  const cellRect = document.querySelector("#lawn .lawn-cell").getBoundingClientRect();
  const animationState = () => ({
    fieldSweep: svg.querySelectorAll(".sweep").length,
    fieldSignal: svg.querySelectorAll(".signal").length,
    chainSweep: trace.querySelectorAll(".chain-sweep").length,
    blooming: document.querySelectorAll(".fd-node.is-blooming").length,
    activating: document.querySelectorAll(".fd-node.is-activating").length,
  });
  const settle = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

  return (async () => {
    // ① 同一份决策再喂一次：key 未变，不应该跑任何一次性动画。
    window.JEVRecording.apply({ options: OPTIONS });
    await settle();
    const unchanged = animationState();

    // ② 换一个真实存在的选中格（wall_nut@r1c5 在候选里）：应该触发动画。
    const OPTIONS2 = JSON.parse(JSON.stringify(OPTIONS));
    for (const question of OPTIONS2.questions) {
      if (question.question_id === "plant_target_lane_1") question.choice = "wall_nut@r1c5";
    }
    OPTIONS2.decision.target = { action: "place_plant", type_name: "wall_nut", row: 1, col: 5 };
    window.JEVRecording.apply({ options: OPTIONS2 });
    await settle();
    const changed = animationState();

    // ③ 16 只僵尸：威胁清单必须自己内部滚动，不得溢出世界模型区域。
    const crowdedState = JSON.parse(JSON.stringify(STATE));
    crowdedState.zombies = Array.from({ length: 16 }, (_, index) => ({
      row: index % 5, type_code: 0, type_name: "normal_zombie", hp: 270, total_hp: 270,
      distance_to_house_px: 250 + index, distance_to_house_cells: 4, x: 250, y: 60 + index * 20,
    }));
    window.JEVRecording.apply({ state: crowdedState, options: OPTIONS2 });
    await settle();
    const rowsBox = document.querySelector(".threat-rows");
    const targetRect = document.getElementById("target").getBoundingClientRect();
    const worldRect = document.querySelector(".rt-world").getBoundingClientRect();
    const focusedRect = document.querySelector(".threat-row.is-target").getBoundingClientRect();
    const rowsRect = rowsBox.getBoundingClientRect();
    const crowded = {
      threatRows: document.querySelectorAll(".threat-row").length,
      rowsClientH: Math.round(rowsBox.clientHeight),
      rowsScrollH: Math.round(rowsBox.scrollHeight),
      scrollable: rowsBox.scrollHeight > rowsBox.clientHeight + 1,
      targetOverflowPx: Math.round(targetRect.bottom - worldRect.bottom),
      focusVisible: focusedRect.top >= rowsRect.top - 1 && focusedRect.bottom <= rowsRect.bottom + 1,
      focusHighlighted: document.querySelectorAll(".threat-row.is-target").length,
    };

    return JSON.stringify({
      unchanged,
      changed,
      crowded,
      selectedNodes: document.querySelectorAll(".fd-node.is-selected").length,
      frames: document.querySelectorAll(".fd-frame").length,
      halos: document.querySelectorAll(".fd-node.is-selected .fd-halo").length,
      axis: svg.querySelectorAll(".axis").length,
      coord: document.getElementById("field-coord").textContent,
      coordVisible: !document.getElementById("field-coord").hidden,
      coordChipBottom: Math.round(document.getElementById("field-coord").getBoundingClientRect().bottom),
      rails: svg.querySelectorAll(".rail").length,
      diagonalPaths: document.querySelectorAll(".rt-trace path").length,
      nodes: document.querySelectorAll(".fd-node").length,
      candidates: document.querySelectorAll(".fd-node.is-candidate").length,
      noneCells: document.querySelectorAll(".field-none").length,
      lawnZombies: [...document.querySelectorAll("#lawn .cell-zombie-label")].map((n) => n.textContent),
      docH: document.documentElement.scrollHeight,
      docW: document.documentElement.scrollWidth,
      workspaceH: Math.round(document.querySelector(".rt-workspace").getBoundingClientRect().height),
      gameViewport: [Math.round(box("game-viewport").width), Math.round(box("game-viewport").height)],
      lawnH: Math.round(box("lawn").height),
      decisionH: Math.round(document.querySelector(".rt-decision").getBoundingClientRect().height),
      lawnCell: [Math.round(cellRect.width), Math.round(cellRect.height)],
      stageOverflow: [...document.querySelectorAll(".rt-stage")].some((s) => s.scrollHeight > s.clientHeight + 1),
      stageTexts,
      actionName: document.querySelector(".action-name")?.textContent,
      visibleControls: ["runtime-start", "runtime-stop"].filter((id) => !document.getElementById(id).hidden),
    });
  })();
})();
