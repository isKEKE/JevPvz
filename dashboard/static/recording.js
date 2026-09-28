/* ============================================================================
 * 录制页控制器。
 *
 * 数据流：/api/{catalog,state,jev-options,jev-runtime}
 *           → JEVViewModel.buildRuntimeViewModel
 *           → RuntimeViewModel
 *           → 下面的 render* 函数
 *
 * 本文件不出现任何原始 schema 路径（`state.availability[...]`、`group.options`
 * 之类）：那是 viewmodel.js 的职责。渲染函数只接受 RuntimeViewModel。
 *
 * 视觉规则：
 *   - 只有“被选中 / 当前观察”允许使用强调色；其余一律灰阶。
 *   - 整页最亮最大的是 ACTION 阶段，因为那是观众要记住的那一件事。
 *   - 调试字段（采样号、就绪、场景、模型延迟…）默认收进 <details>，能力保留、视线让出。
 * ========================================================================= */

(function () {
  "use strict";

  const STATE_REFRESH_MS = 500;
  const DECISION_REFRESH_MS = 1000;
  const RUNTIME_LABELS = {
    running: ["运行中", "is-running"],
    starting: ["启动中", "is-running"],
    stopped: ["已停止", "is-stopped"],
    idle: ["空闲", "is-stopped"],
    failed: ["异常", "is-error"],
    disabled: ["未启用", "is-stopped"],
  };
  /** 候选点不透明度：未评估 ~0.15，候选随真实概率 0.34→0.92，选中恒为 1。 */
  const SVG_NS = "http://www.w3.org/2000/svg";
  const CANDIDATE_FLOOR = 0.34;
  const CANDIDATE_FULL = 0.5;
  const CANDIDATE_CEILING = 0.92;
  /** 节点半径随 score 变化：低分小圈，高分接近满尺寸。 */
  const NODE_SCALE_MIN = 0.72;
  const NODE_SCALE_MAX = 1.22;
  let previousSelectedOptionId = null;
  let lastThreatFocusId = null;
  /** 执行状态词：直接来自 action_result.boundary.status。 */
  const BOUNDARY_LABELS = {
    success: ["SUCCESS", "is-success"],
    unverified: ["UNVERIFIED", "is-unverified"],
    rejected: ["REJECTED", "is-failed"],
    failed: ["FAILED", "is-failed"],
  };

  const store = { state: null, options: null, runtime: null, catalog: false };
  let runtimeBusy = false;
  let lastDecisionKey = null;

  const byId = (id) => document.getElementById(id);

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  const dash = (value) => (value === null || value === undefined || value === "" ? "—" : String(value));

  function observeRow(label, value) {
    const wrap = el("div", "observe-row");
    wrap.append(el("span", "", label));
    wrap.append(el("b", "", value));
    return wrap;
  }

  /* ------------------------------------------------------------ header --- */

  function renderHeader(vm) {
    byId("m-sun").textContent = vm.game.sun === null ? "—" : String(vm.game.sun);
    byId("m-wave").textContent = vm.game.waveText || "—";
    byId("m-level").textContent = dash(vm.game.level);
    byId("m-mode").textContent = dash(vm.game.modeLabel);
  }

  function renderClock() {
    const now = new Date();
    byId("m-clock").textContent = [now.getHours(), now.getMinutes(), now.getSeconds()]
      .map((part) => String(part).padStart(2, "0")).join(":");
  }

  /* --------------------------------------------------------- inventory --- */

  function renderInventory(vm) {
    const list = byId("inv-list");
    const available = byId("inv-available");
    const inventory = vm.inventory;
    list.replaceChildren();
    if (!inventory.read) {
      available.textContent = "—";
      list.append(el("span", "empty-message", "卡槽尚未读取"));
      return;
    }
    available.textContent = inventory.readyKnown ? String(inventory.availableCount) : "—";
    if (!inventory.items.length) {
      list.append(el("span", "empty-message", "当前没有卡牌槽"));
      return;
    }
    for (const item of inventory.items) {
      const wrap = el("span", `inv-item ${item.ready === true ? "is-ready" : item.ready === false ? "is-cooling" : ""}`);
      wrap.append(el("span", "inv-state", ""));
      wrap.append(el("span", "inv-abbr", item.abbr));
      wrap.append(el("span", "inv-cost", item.cost === null ? "—" : String(item.cost)));
      const cooling = item.fraction === null ? "冷却未知"
        : item.ready === true ? "冷却完成" : `冷却 ${Math.round(item.fraction * 100)}%`;
      wrap.title = `${item.label} · 阳光 ${item.cost === null ? "未知" : item.cost} · ${cooling}`;
      wrap.setAttribute("aria-label", wrap.title);
      list.append(wrap);
    }
  }

  /* -------------------------------------------------------------- lawn --- */

  /**
   * 草坪是机器视图，必须同时表达两件事：哪里种了什么、僵尸走到了哪。
   * 后者曾经被整个漏掉：只有“聚焦格”的角标，没有任何僵尸标记。
   */
  function renderLawn(vm) {
    const lawn = byId("lawn");
    const focus = vm.currentTarget;
    const zombiesByCell = new Map();
    for (const zombie of vm.threats.list) {
      if (zombie.row === null || zombie.col === null) continue;
      const key = `${zombie.row}:${zombie.col}`;
      if (!zombiesByCell.has(key)) zombiesByCell.set(key, []);
      zombiesByCell.get(key).push(zombie);
    }
    lawn.replaceChildren();
    lawn.append(el("div", "lawn-head", ""));
    for (let col = 0; col < 9; col += 1) lawn.append(el("div", "lawn-head", String(col + 1).padStart(2, "0")));
    for (let r = 0; r < 5; r += 1) {
      lawn.append(el("div", "lawn-row", `R${r + 1}`));
      for (let c = 0; c < 9; c += 1) {
        const cell = vm.lawn.cells[r * 9 + c];
        const node = el("div", "lawn-cell");
        if (!vm.lawn.readable) {
          node.classList.add("is-empty");
          node.append(el("span", "cell-unknown", "—"));
          node.title = `${vm.lawn.reason}；无法判断当前格是否为空`;
        } else if (cell && cell.plant && cell.plant.length) {
          node.classList.add("is-plant");
          node.append(el("span", "cell-marker", ""));
          node.append(el("span", "cell-abbr", cell.plant.map((item) => item.abbr).join("+")));
          node.title = cell.plant.map((item) => item.label).join("；");
        } else {
          node.classList.add("is-empty");
          node.append(el("span", "cell-dot", "·"));
          node.title = "空位";
        }

        const here = zombiesByCell.get(`${r}:${c}`);
        if (here) {
          node.classList.add("has-zombie");
          const stack = el("div", "cell-zombies");
          for (const zombie of here.slice(0, 2)) {
            const item = el("div", "cell-zombie");
            item.append(el("span", "cell-zombie-mark", ""));
            item.append(el("span", "cell-zombie-label", zombie.id));
            item.title = `${zombie.id} ${zombie.label}${zombie.hp === null ? "" : ` · 血量 ${zombie.hp}`}`;
            stack.append(item);
          }
          if (here.length > 2) stack.append(el("span", "cell-zombie-more", `+${here.length - 2}`));
          node.append(stack);
          const names = here.map((zombie) => `${zombie.id} ${zombie.label}`).join("；");
          node.title = node.title ? `${names} · ${node.title}` : names;
        }

        if (focus && focus.row === r && focus.col === c) {
          node.classList.add("is-focused");
          const reticle = el("span", "cell-reticle", "");
          reticle.append(el("span", "cell-reticle-inner", ""));
          node.append(reticle);
          if (!node.title.includes("聚焦")) node.title = `${node.title} · 当前聚焦`;
        }
        lawn.append(node);
      }
    }
  }

  /* ------------------------------------------------------------ target --- */

  function renderTarget(vm) {
    const box = byId("target");
    const target = vm.currentTarget;
    box.replaceChildren();

    // 眉标与决策链的 OBSERVE 同源：这块是“观察的结果”，不是一张独立的卡。
    const head = el("div", "rt-target-head");
    head.append(el("h3", "", "目标"));
    head.append(el("span", "rt-pane-meta", "TARGET"));
    box.append(head);

    if (!target) {
      box.append(el("p", "stage-empty", vm.threats.readable ? "当前没有僵尸" : "僵尸域尚未读取"));
      return;
    }

    const main = el("div", "target-head");
    main.append(el("span", "target-id", target.id));
    main.append(el("span", "target-name", target.label));
    box.append(main);

    const rows = el("div", "target-rows");
    for (const [label, value] of [
      ["行 · 列", `${target.row === null ? "—" : `R${target.row + 1}`} · ${target.col === null ? "—" : `C${target.col + 1}`}`],
      ["距房", target.distancePx === null ? "—" : `${Math.round(target.distancePx)} px`],
      ["血量", dash(target.hp)],
    ]) {
      const line = el("div", "target-row");
      line.append(el("span", "", label));
      line.append(el("b", "", value));
      rows.append(line);
    }
    box.append(rows);

    // 局面压成一行淡色：它是背景噪声，不该和靶子抢注意力。
    const state = el("p", "target-state");
    const pairs = [
      ["阳光", dash(vm.game.sun)],
      ["植物", String(vm.lawn.cells.filter((cell) => cell.plant).length)],
      ["僵尸", String(vm.threats.list.length)],
      ["波次", dash(vm.game.waveText)],
    ];
    pairs.forEach(([label, value], index) => {
      if (index) state.append(document.createTextNode(" · "));
      state.append(document.createTextNode(`${label} `));
      state.append(el("b", "", value));
    });
    state.title = "聚焦 = 距房屋最近者";
    box.append(state);

    // 调试字段默认收起：保留能力，但不占展示视线。
    const details = el("details", "rt-details");
    details.append(el("summary", "", "细节"));
    const body = el("div", "rt-details-body");
    for (const [label, value] of [
      ["场景", dash(vm.game.sceneLabel)],
      ["决策就绪", vm.game.decisionReady === null ? "—" : vm.game.decisionReady ? "是" : "否"],
      ["采样", dash(vm.game.sampleSequence)],
      ["聚焦规则", "距房屋最近"],
    ]) {
      const item = el("span", "", `${label} `);
      item.append(el("b", "", value));
      body.append(item);
    }
    details.append(body);
    box.append(details);

    // 世界模型不只有靶子：机器识别出的完整威胁集也要能看到，
    // 否则中间那一列在 2K 下会空掉一大截。
    if (vm.threats.list.length) {
      const threats = el("div", "rt-threats");
      const threatsHead = el("div", "rt-target-head");
      threatsHead.append(el("h3", "", "威胁"));
      threatsHead.append(el("span", "rt-pane-meta", `THREATS · ${vm.threats.list.length}`));
      threats.append(threatsHead);
      const rows = el("div", "threat-rows");
      let focusedRow = null;
      for (const zombie of vm.threats.list) {
        const isTarget = zombie === target;
        const line = el("div", `threat-row${isTarget ? " is-target" : ""}`);
        line.append(el("span", "threat-id", zombie.id));
        line.append(el("span", "threat-name", zombie.label));
        line.append(el("span", "", zombie.row === null || zombie.col === null ? "—" : `R${zombie.row + 1} C${zombie.col + 1}`));
        line.append(el("span", "threat-dist", zombie.distancePx === null ? "—" : `${Math.round(zombie.distancePx)} px`));
        line.append(el("span", "threat-hp", zombie.hp === null ? "—" : String(zombie.hp)));
        line.title = `${zombie.id} ${zombie.label}${zombie.hp === null ? "" : ` · 血量 ${zombie.hp}`}`;
        if (isTarget) focusedRow = line;
        rows.append(line);
      }
      threats.append(rows);
      box.append(threats);
      // 列表内部滚动时焦点那只必须看得见；只在焦点真的换了的那一次动滚动位置，
      // 否则每轮采样都会把人工滚动抢回去。
      if (focusedRow && target && target.id !== lastThreatFocusId) {
        const listRect = rows.getBoundingClientRect();
        const rowRect = focusedRow.getBoundingClientRect();
        if (rowRect.top < listRect.top) rows.scrollTop -= listRect.top - rowRect.top;
        else if (rowRect.bottom > listRect.bottom) rows.scrollTop += rowRect.bottom - listRect.bottom;
      }
    }
    lastThreatFocusId = target ? target.id : null;
  }

  /* ------------------------------------------------------------ stages --- */

  function renderObserve(vm) {
    const box = byId("stage-observe");
    const target = vm.currentTarget;
    box.replaceChildren();
    if (!target) {
      box.append(el("p", "stage-empty", vm.threats.readable ? "没有观察对象" : "僵尸域尚未读取"));
      return;
    }
    box.append(el("span", "observe-id", target.id));
    box.append(el("span", "observe-name", target.label));
    const rows = el("div", "observe-rows");
    // 只留两行：距房同时出现在目标块与右侧交叉引用里，这里不重复占高度。
    rows.append(observeRow("行 · 列", `${target.row === null ? "—" : `R${target.row + 1}`} · ${target.col === null ? "—" : `C${target.col + 1}`}`));
    rows.append(observeRow("血量", dash(target.hp)));
    box.append(rows);
  }

  function renderRail(containerId, vm, index, emptyText) {
    const box = byId(containerId);
    const rail = vm.decision.rails[index];
    box.replaceChildren();
    if (!rail) {
      box.append(el("p", "stage-empty", emptyText));
      return;
    }
    box.append(el("span", "rail-title", rail.label));
    const options = el("div", "rail-options");
    for (const option of rail.options) {
      const line = el("div", `rail-opt${option.selected ? " is-selected" : ""}`);
      line.append(el("span", "rail-opt-mark", "●"));
      line.append(el("span", "rail-opt-name", option.label));
      line.append(el("span", "rail-opt-value", option.probability === null ? "—" : option.probability.toFixed(2)));
      line.title = `${option.label} · ${option.probability === null ? "无概率" : option.probability}`
        + `${option.selected ? " · 已选中" : ""}${option.executed ? " · 已执行" : ""}`;
      options.append(line);
    }
    box.append(options);
    if (rail.hiddenCount > 0) {
      box.append(el("span", "rail-more", `另有 ${rail.hiddenCount} 项未列出`));
    }
  }

  function svgEl(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, String(value));
    return node;
  }

  function scoreOpacity(probability) {
    if (probability === null) return CANDIDATE_FLOOR;
    return Math.round((CANDIDATE_FLOOR
      + (CANDIDATE_CEILING - CANDIDATE_FLOOR) * Math.min(1, probability / CANDIDATE_FULL)) * 100) / 100;
  }

  function scoreScale(probability) {
    if (probability === null) return NODE_SCALE_MIN;
    return Math.round((NODE_SCALE_MIN
      + (NODE_SCALE_MAX - NODE_SCALE_MIN) * Math.min(1, probability / CANDIDATE_FULL)) * 100) / 100;
  }

  /**
   * JEV Decision Field。
   * 节点半径与亮度都由真实 score 驱动；轨道 / 竖轴 / 信号写在底层 SVG 上。
   * 动画只在“新决策到来”时跑一次，且全部有限时长。
   */
  function renderField(vm, isNewDecision) {
    const grid = byId("field-grid");
    const provenance = byId("field-provenance");
    const field = vm.decision.field;
    const byCell = new Map(field.cells.map((cell) => [`${cell.row}:${cell.col}`, cell]));
    const selected = field.cells.find((cell) => cell.selected) || null;
    grid.replaceChildren();
    grid.append(el("div", "field-row", ""));
    for (let col = 0; col < 9; col += 1) grid.append(el("div", "field-col", String(col + 1).padStart(2, "0")));
    for (let r = 0; r < 5; r += 1) {
      grid.append(el("div", "field-row", `R${r + 1}`));
      for (let c = 0; c < 9; c += 1) {
        const holder = el("div", "field-cell");
        const cell = byCell.get(`${r}:${c}`);
        if (!cell) {
          holder.append(el("span", "field-none", "·"));
        } else {
          const node = el("span", "fd-node");
          node.style.opacity = String(scoreOpacity(cell.probability));
          node.style.setProperty("--node-scale", String(scoreScale(cell.probability)));
          if (cell.selected) {
            node.classList.add("is-selected");
            node.style.opacity = "1";
            node.style.setProperty("--node-scale", "1.22");
            if (isNewDecision) node.classList.add("is-blooming");
            const frame = el("span", "fd-frame");
            frame.append(el("span", "fd-frame-inner", ""));
            node.append(frame, el("span", "fd-halo", ""));
          } else {
            node.classList.add("is-candidate");
            if (isNewDecision) {
              node.classList.add("is-activating");
              // 高分先出现、低分后出现：候选是“依次被评估出来”的。
              node.style.animationDelay = `${Math.round((1 - Math.min(1, (cell.probability ?? 0) / CANDIDATE_FULL)) * 170)}ms`;
            }
            // 上一个被选中的节点不瞬时消失，在 700ms 里退回候选。
            if (previousSelectedOptionId !== null && cell.optionId === previousSelectedOptionId) {
              node.classList.add("is-decaying");
            }
          }
          if (cell.executed) node.classList.add("is-executed");
          node.append(el("span", "fd-core", ""));
          node.title = `${cell.typeLabel} · ${cell.probability === null ? "无概率" : cell.probability}`
            + `${cell.selected ? " · 已选中" : ""}${cell.executed ? " · 已执行" : ""}`;
          node.setAttribute("role", "img");
          node.setAttribute("aria-label", node.title);
          holder.append(node);
        }
        grid.append(holder);
      }
    }
    previousSelectedOptionId = selected ? selected.optionId : null;

    // 候选场来自哪一次决策必须写出来：最新的决策常常是收集分支，那时格点场来自
    // 更早的一次种植决策。但不写成一句话——只是一串 job 号，贴在 POSITION 标题行上。
    if (!field.readable) {
      provenance.textContent = "";
    } else if (field.jobId) {
      provenance.textContent = `${field.jobId}${field.branchLabel ? ` · ${field.branchLabel}` : ""}`;
    } else {
      provenance.textContent = "";
    }
    window.requestAnimationFrame(() => drawFieldScaffold(selected, isNewDecision));
  }

  /** 轨道 / 竖轴 / 信号：几何要等布局完成，所以放在 rAF 里量。 */
  function drawFieldScaffold(selected, animate) {
    const svg = byId("field-svg");
    const grid = byId("field-grid");
    const coord = byId("field-coord");
    const host = grid && grid.parentElement;
    svg.replaceChildren();
    if (!host) return;
    const hostRect = host.getBoundingClientRect();
    if (!hostRect.width || !hostRect.height) return;
    svg.setAttribute("viewBox", `0 0 ${Math.round(hostRect.width)} ${Math.round(hostRect.height)}`);
    const children = [...grid.children];
    const rectOf = (index) => children[index].getBoundingClientRect();
    const mid = (rect) => ({
      x: rect.left - hostRect.left + rect.width / 2,
      y: rect.top - hostRect.top + rect.height / 2,
    });

    // 5 条横向轨道，把每行的节点串起来。
    for (let r = 0; r < 5; r += 1) {
      const first = mid(rectOf(11 + r * 10));
      const last = mid(rectOf(19 + r * 10));
      svg.append(svgEl("line", { class: "rail", x1: first.x.toFixed(1), y1: first.y.toFixed(1),
        x2: last.x.toFixed(1), y2: last.y.toFixed(1) }));
    }

    if (!selected || selected.row === null || selected.col === null) {
      coord.hidden = true;
      return;
    }
    if (selected.row > 4 || selected.col > 8) { coord.hidden = true; return; }
    const target = children[11 + selected.row * 10 + selected.col];
    if (!target) { coord.hidden = true; return; }
    const dot = mid(target.getBoundingClientRect());
    const rowStart = mid(rectOf(11 + selected.row * 10));
    const gridBottom = hostRect.height;

    // 竖轴：从列标签下方穿过选中节点，一直落到坐标框。
    svg.append(svgEl("line", { class: "axis", x1: dot.x.toFixed(1), y1: "2",
      x2: dot.x.toFixed(1), y2: (gridBottom - 4).toFixed(1) }));
    coord.hidden = false;
    coord.textContent = `R${selected.row + 1} C${selected.col + 1}`;
    coord.style.left = `${dot.x.toFixed(1)}px`;
    coord.style.top = `${(gridBottom - 4).toFixed(1)}px`;

    if (!animate) return;
    // 信号沿选中那一行的轨道跑到节点上，再拆掉，不留常亮图形。
    const from = rowStart.x - 40;
    const sweep = svgEl("line", { class: "sweep", x1: from.toFixed(1), y1: dot.y.toFixed(1),
      x2: dot.x.toFixed(1), y2: dot.y.toFixed(1), "stroke-dasharray": "20 24" });
    const pulse = svgEl("circle", { class: "signal", r: "3.5", cx: from.toFixed(1), cy: dot.y.toFixed(1) });
    svg.append(sweep, pulse);
    const travel = Math.max(60, dot.x - from);
    sweep.animate([
      { opacity: 0, strokeDashoffset: 44 },
      { opacity: 0.85, offset: 0.35 },
      { opacity: 0, strokeDashoffset: 0 },
    ], { duration: 620, easing: "cubic-bezier(0.4, 0, 0.2, 1)", fill: "forwards" });
    pulse.animate([
      { opacity: 0, transform: "translateX(0px)" },
      { opacity: 1, offset: 0.25 },
      { opacity: 0, transform: `translateX(${travel.toFixed(1)}px)` },
    ], { duration: 560, easing: "cubic-bezier(0.4, 0, 0.2, 1)", fill: "forwards" });
    window.setTimeout(() => { sweep.remove(); pulse.remove(); }, 760);
  }

  function renderAction(vm) {
    const box = byId("stage-action");
    const selected = vm.decision.selected;
    box.replaceChildren();
    if (!selected || !selected.known) {
      box.append(el("span", "action-name is-idle", "—"));
      box.append(actionRows([["STATUS", "PENDING", "is-pending"]]));
      return;
    }
    // 种植、收集、等待三种动作的“名字”与“目标”含义不同，分开拼。
    const isPlant = Boolean(selected.cellText && selected.typeLabel);
    const isIdle = !selected.actionLabel || selected.actionLabel === "等待";
    const name = isIdle ? dash(selected.actionLabel || "等待")
      : isPlant ? `${selected.actionLabel}${selected.typeLabel}` : dash(selected.actionLabel || selected.intentLabel);
    const nameClass = isIdle ? "is-idle"
      : isPlant ? "is-plant"
        : (selected.actionLabel === "铲除" ? "is-shovel" : "is-collect");
    box.append(el("span", `action-name ${nameClass}`, name));

    const executed = selected.executed;
    const status = executed && executed.boundaryStatus
      ? (BOUNDARY_LABELS[executed.boundaryStatus] || [String(executed.boundaryStatus).toUpperCase(), "is-pending"])
      : ["PENDING", "is-pending"];
    const targetText = isPlant ? selected.cellText
      : (executed && executed.typeLabel ? executed.typeLabel : "—");
    const rows = [
      ["TARGET", targetText],
      ["STATUS", status[0], status[1]],
      ["LATENCY", executed && executed.elapsedMs !== null ? `${executed.elapsedMs} ms` : "—"],
      ["SCORE", typeof selected.score === "number" ? selected.score.toFixed(2) : "—"],
    ];
    // JEV 弃权时闸门原因是唯一的解释，放进同一个对齐列表，不加额外注释行。
    if (selected.fallbackCode) rows.push(["GATE", selected.fallbackCode, "is-reason"]);
    box.append(actionRows(rows));
  }

  /** 对齐的 label/value 列表：动作名之下的一切都走这个形状。 */
  function actionRows(spec) {
    const list = el("div", "action-rows");
    for (const [label, value, valueClass] of spec) {
      const line = el("div", "action-row");
      line.append(el("span", "", label));
      line.append(el("b", valueClass || "", value));
      list.append(line);
    }
    return list;
  }

  /* ---------------------------------------------------------- crossref --- */

  /** 把机器正在看的目标指回真实画面，建立 World Model 与 Game Window 的关联。 */
  function renderCrossref(vm) {
    const node = byId("crossref");
    const target = vm.currentTarget;
    node.replaceChildren();
    if (!target) {
      node.append(document.createTextNode(vm.threats.readable ? "本轮没有观察对象。" : "僵尸域尚未读取，无法定位观察对象。"));
      return;
    }
    node.append(document.createTextNode("机器聚焦 "));
    node.append(el("b", "", target.id));
    node.append(document.createTextNode(" · "));
    const cell = `${target.row === null ? "—" : `R${target.row + 1}`} ${target.col === null ? "—" : `C${target.col + 1}`}`;
    node.append(el("i", "", cell));
    if (target.distancePx !== null) {
      node.append(document.createTextNode(" · 距房 "));
      node.append(el("i", "", `${Math.round(target.distancePx)} px`));
    }
    node.append(document.createTextNode("（＝距房屋最近者）"));
  }

  /* ------------------------------------------------------------- trace --- */

  /**
   * 信号沿决策链的 1px 主干从左扫到右，只在“新决策到来”时跑一次。
   * 之前这里画的是从格点斜拉到 ACTION 的一条长虚线：它既不像信号，
   * 又会随每秒轮询反复重画，看起来就像面板上的一道划痕。
   */
  function drawTrace() {
    const svg = byId("trace");
    const host = svg.parentElement;
    svg.replaceChildren();
    if (!host) return;
    const chain = host.querySelector(".rt-chain");
    if (!chain) return;
    const hostRect = host.getBoundingClientRect();
    const chainRect = chain.getBoundingClientRect();
    if (!hostRect.width || !chainRect.width) return;
    svg.setAttribute("viewBox", `0 0 ${Math.round(hostRect.width)} ${Math.round(hostRect.height)}`);
    // .rt-chain::before 的主干固定在 top: 11px。
    const y = chainRect.top - hostRect.top + 11.5;
    const x1 = chainRect.left - hostRect.left;
    const sweep = svgEl("line", { class: "chain-sweep", x1: x1.toFixed(1), y1: y.toFixed(1),
      x2: (x1 + chainRect.width).toFixed(1), y2: y.toFixed(1), "stroke-dasharray": "64 2400" });
    svg.append(sweep);
    sweep.animate([
      { opacity: 0, strokeDashoffset: 2464 },
      { opacity: 0.9, offset: 0.3 },
      { opacity: 0, strokeDashoffset: 0 },
    ], { duration: 980, easing: "cubic-bezier(0.4, 0, 0.2, 1)", fill: "forwards" });
    window.setTimeout(() => sweep.remove(), 1080);
  }

  /* ----------------------------------------------------------- runtime --- */

  function renderRuntime(status) {
    const state = (status && status.state) || "unknown";
    const [label, dotClass] = RUNTIME_LABELS[state] || [state, "is-stopped"];
    // 运行中用 ● LIVE 表达，不再并排两个同等强度的按钮。
    const running = Boolean(status && status.can_stop);
    byId("m-run-label").textContent = running && label !== "异常" ? "运行中" : label;
    byId("m-run-dot").className = `rt-dot ${dotClass}`;
    const start = byId("runtime-start");
    const stop = byId("runtime-stop");
    start.hidden = running;
    stop.hidden = !running;
    start.disabled = runtimeBusy || !status || !status.can_start;
    stop.disabled = runtimeBusy || !status || !status.can_stop;
    const meta = `进程 ${dash(status && status.pid)} · 退出码 ${dash(status && status.exit_code)}`
      + ` · 游戏${status && status.game_ready ? "进行中" : "未就绪"}`;
    start.title = `启动 · ${(status && status.message) || "—"} · ${meta}`;
    stop.title = `停止 · ${(status && status.message) || "—"} · ${meta}`;
  }

  async function controlRuntime(command) {
    if (runtimeBusy) return;
    runtimeBusy = true;
    byId("runtime-start").disabled = true;
    byId("runtime-stop").disabled = true;
    try {
      const response = await fetch(`/api/jev-runtime/${command}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-JEV-Control": "1" },
        body: "{}",
        cache: "no-store",
      });
      renderRuntime(await response.json());
    } catch (error) {
      renderRuntime({ state: "failed", message: `控制请求失败：${error}` });
    } finally {
      runtimeBusy = false;
      await fetchRuntime();
      await fetchOptions();
    }
  }

  /* ------------------------------------------------------------- fetch --- */

  async function fetchCatalog() {
    try {
      const response = await fetch("/api/catalog", { cache: "no-store" });
      if (!response.ok) return;
      JEVViewModel.installCatalog(await response.json());
      store.catalog = true;
      render();
    } catch (error) { /* 目录缺失时 viewmodel 回退到英文名，不阻塞页面 */ }
  }

  async function fetchState() {
    try {
      const response = await fetch("/api/state", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      store.state = await response.json();
    } catch (error) {
      store.state = null;
    }
    render();
  }

  async function fetchOptions() {
    try {
      const response = await fetch("/api/jev-options", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      store.options = await response.json();
    } catch (error) {
      store.options = null;
    }
    render();
  }

  async function fetchRuntime() {
    try {
      const response = await fetch("/api/jev-runtime", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      store.runtime = await response.json();
    } catch (error) {
      store.runtime = { state: "failed", message: "进程状态不可读" };
    }
    renderRuntime(store.runtime);
  }

  /* ------------------------------------------------------------ render --- */

  function render() {
    if (!store.state) return;
    const vm = JEVViewModel.buildRuntimeViewModel({
      state: store.state,
      options: store.options,
      runtime: store.runtime,
    });
    // 决策是否真的换了：只有换了才跑一次性动画。
    const decisionKey = [
      vm.decision.jobId,
      vm.decision.field.jobId,
      vm.decision.field.cells.length,
      vm.decision.field.cells.find((cell) => cell.selected)?.optionId || "",
      vm.decision.rails.map((rail) => `${rail.questionId}:${rail.options.map((option) => option.optionId).join(",")}`).join("|"),
    ].join("#");
    const first = lastDecisionKey === null;
    const isNewDecision = !first && decisionKey !== lastDecisionKey;
    lastDecisionKey = decisionKey;

    renderHeader(vm);
    renderInventory(vm);
    renderLawn(vm);
    renderTarget(vm);
    renderCrossref(vm);
    renderObserve(vm);
    renderRail("stage-intent", vm, 0, "本步没有意图问题");
    renderRail("stage-option", vm, 1, "本步没有第二级问题");
    renderField(vm, isNewDecision);
    renderAction(vm);

    // 世界状态就地更新（数字变化本身已经是反馈），不做入场动画：
    // 采样每秒推进一次，任何入场动画都会变成持续闪烁。
    if (isNewDecision) {
      for (const node of [byId("stage-intent"), byId("stage-option"), byId("stage-action")]) {
        node.classList.remove("is-fresh");
        void node.offsetWidth;
        node.classList.add("is-fresh");
      }
      // 首次渲染不跑信号：静止页面不应该有常亮的东西。
      window.requestAnimationFrame(() => drawTrace());
    }
    byId("decision-meta").textContent = vm.decision.readable
      ? `${dash(vm.decision.branchLabel)} · ${dash(vm.decision.jobId)}${vm.decision.selected.known && vm.decision.selected.stageLabel ? ` · ${vm.decision.selected.stageLabel}` : ""}`
      : "";
  }

  /* -------------------------------------------------------------- wire --- */

  document.addEventListener("DOMContentLoaded", () => {
    byId("runtime-start").addEventListener("click", () => controlRuntime("start"));
    byId("runtime-stop").addEventListener("click", () => controlRuntime("stop"));
    renderClock();
    window.setInterval(renderClock, 1000);
    fetchCatalog();
    fetchState();
    fetchOptions();
    fetchRuntime();
    window.setInterval(fetchState, STATE_REFRESH_MS);
    window.setInterval(fetchOptions, DECISION_REFRESH_MS);
    window.setInterval(fetchRuntime, DECISION_REFRESH_MS);
    window.addEventListener("resize", () => drawTrace());
  });

  /* 测试/预览接缝：用固定样本喂渲染层，不经过网络。 */
  window.JEVRecording = {
    apply(input) {
      const payload = input || {};
      if (payload.catalog) store.catalog = payload.catalog;
      if (payload.state) store.state = payload.state;
      if (payload.options) store.options = payload.options;
      if (payload.runtime) {
        store.runtime = payload.runtime;
        renderRuntime(store.runtime);
      }
      render();
    },
    drawTrace,
    store,
  };
})();
