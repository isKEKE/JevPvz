# 种植短视与高级植物不进入候选：只读根因分析 + 修复记录

时间：2026-09-29（本地直改任务，非 SDD 阶段；未 commit/push）
证据：`.log/jev-dashboard.jsonl`（run `3e6e1b07…`，305 事件，17:06:17–17:10:41 UTC）、
`.log/jev-dashboard-process.log`（累积 11 次运行、4505 条 cycle 记录、491 次 plant 决策）、
`jev/*` 与 `tests/*` 当前工作树。
复现脚本：`uv run python tools/evidence-plan-economy.py --trace-file .log/jev-dashboard.jsonl`（离线、不调模型、不访问游戏）。

---

## 1. 现行实现链路（修复前）

```text
All State (state/builder.py: 卡槽 cost/usable/cooldown_ready, 5x9 board, plants, zombies, items)
   │  state/projection.py  JEV allowlist
   ▼
SnapshotStore.publish/latest  (jev/loop.py)
   │
   ├─ CollectBranch（共享入口 decide_shared）
   │     collect Noul + management 问题(construction_intent: keep/replace/cancel
   │                                    next_construction_type: 全部手牌)
   │     答案 replace → loop._intent = {type_name}; _intent_version += 1
   │
   └─ PlantBranch
         _local_wait_reason / decide_plant
             if intent: cards := [card for card in cards if type_name == intent]   ← 候选空间在此被截断
             candidates = affordable(cards) × empty_plantable_cells
             >254 → lane Choice + 每行 Choice（官方链式拆分）
             state = management_facts + threat_label_facts + catalog + current_intent + last_actual_result
             → 模型 argmax（弃选项=wait）
   ▼
_propose → scheduler（source_intent_version 守卫 + type==intent 守卫） → ActionBoundary → Executor
```

关键事实：`jev/strategy.py` 的 `StrategySignals`（`phase`、`economy_signal`、逐行 urgency）
**只写进 Trace，没有任何决策消费者**；`build_typesafe_state` 也不发送这些字段
（`phase`/`economy_signal` 是 `tests/test_jev_client.py` 里明确禁止下发的字段）。
`PLANT_STATE_FIELDS` 里与资源相关的只有裸 `sun` 和每张卡的 `payable`/`shortfall`。

## 2. 两个问题的定位

### Case B —— 高级植物不进入候选（Candidate Generation 层）

链路定位：**CollectBranch 的意图写入 → PlantBranch 候选截断**，不是 JEV 评分、不是阈值。

`jev/decision Trace` 逐事件证据（同一局，同一 10 张手牌）：

| 事件 | 时刻 | sun | 模型看到的手牌 | 候选 | 结果 |
|---|---|---|---|---|---|
| job-000002 | 17:06:17.391 | 7375 | 10 种 | 10×37=370 → 链式 | `peashooter@r0c0` 执行 |
| job-000005 | 17:06:21.320 | 7400 | 10 种(9 可用) | 9×37 | `cabbage_pult@r0c0` → superseded |
| job-000009 | 17:06:21.882 | 7300 | 10 种(9 可用) | 9×36 | `cabbage_pult@r2c3` → superseded |
| job-000006(collect) | 17:06:22.003 | 7300 | — | — | `construction_intent=replace`(0.46 vs keep 0.44)，`next_construction_type=sunflower`（confidence 0.33） |
| job-000010 | 17:06:22.828 | 7300 | **仅 sunflower** | **1×36** | 弃选项 0.42 > sunflower 0.22 → wait |
| job-000016 | 17:06:28.936 | 7375 | **仅 sunflower** | **1×36** | 弃选项 0.42 > sunflower 0.23 → wait |

- `strategy.summary.affordable` 在 job-000010/16 仍是全部 10 种（说明原始样本里手牌完整），
  而 `job_start.state.cards` 只有 1 张 —— 差异只能来自 `decide_plant` 里的意图过滤。
- 由此，sun 从 7375 到 8175 级的手牌里，`melon_pult(300)/repeater(200)/snow_pea(175)` 等
  **在候选层面就不存在**；JEV 永远不可能选到它们。`sun` 的唯一作用是把 `usable` 从 false 变 true。
- 触发条件极脆弱：一次 `replace` 的 argmax 只要以 0.02 优势胜过 `keep`（job-000006 实测
  0.46 vs 0.44，confidence 0.33），就会锁死随后所有 plant 决策的候选空间；
  `keep`（0.49–0.59）会无限期维持它。没有 TTL、没有重新论证、没有失效条件。
- 附带损失：意图版本变化同时让两个已完成推理的 plant 决策（job-000005/000009）
  在 `_resolve_outcome` 里变成 `superseded`。累计统计（process log，11 次运行、491 次 plant 决策）：
  `none_of_the_above` 241 次、peashooter 76、sunflower 52、cabbage_pult 38、tall_nut 21、
  potato_mine 18、wall_nut 15、jalapeno 11、snow_pea 4、repeater 4、chomper 3、magnet_shroom 3、
  cherry_bomb 2、**melon_pult 2**、starfruit 1；`replace` 答案里 143/189 是 50 阳光的 sunflower。

### Case A —— 不会为未来而等待（Economy/Candidate 层）

链路定位：**State→Strategy→Candidate 之间缺少资源层**。

1. `build_plant_candidates` 的语义就是「当前可负担 × 空格」——按构造即
   「有资源 + 有合法位置 → 立即消费」，没有任何跨 tick 表达。
2. 决策路径里没有 economy state：没有 reserve/plan 价格/surplus，只有裸 `sun`。
   `StrategySignals.phase/economy_signal` 存在但不消费、不下发。
3. 唯一 wait 机制是「目标类型不可支付 → 本地 `await_resource`」或「模型自己选弃选项」。
   攒钱的语义只能间接产生于「模型声明了一个买不起的目标」，而问题文本与状态里
   没有任何东西提示这条路径存在（`next_construction_type` 选项只写 cost + payable）。
4. 结果：模型把目标声明成 sunflower（76% 的 replace 答案）→ 目标始终可支付 →
   系统永远处在「有合法选项」的状态，没有需要攒钱的对象。

结论：**Case A 是「缺失的经济层」而不是「阈值不对」**；Case B 是「实现把意图从上下文
退化成了候选过滤器」，与已批准的 R29/OD-43「construction_intent 从授权前提降级为上下文」相矛盾。

## 3. 修复（最小但通用）

分层落点：

```text
World State
   │  management_facts(..., plan) → economy{band, plan{cost,payable,shortfall}, sun_above_plan, ...}
   ├─ Threat 事实：逐行 urgency（OD-30 表）+ 有僵尸且无攻击植物
   └─ Economy 事实：手牌自身价格阶梯（不分档次外挂阈值）+ 模型自己声明的目标
          ▼
   plant_spend_decision(signals, cards, plan) → PlantSpendDecision{type_names, hold_reason}
          ▼
   build_plant_candidates(...) / build_plant_questions(...)
          ▼
   JEV 在合理候选空间内 argmax（弃选项=wait）
          ▼
   Gate：epoch → sample 新鲜度 → 意图版本（**不再**校验 target 类型 == 意图类型）
          ▼
   Action
```

规则（全部由代码显式表达、零新增可调参数、零硬编码 sun 数字；`jev/strategy.py`）：

| 条件 | 候选空间 | 结果 |
|---|---|---|
| 无目标（intent=None） | 全部 affordable × 空格 | 与修复前一致（OD-15 全枚举） |
| 目标仍差阳光 + 无行处于 `high/critical`，也没有「有僵尸但无攻击植物」的行 | 空 | 本地 `await_plan`（不花目标的钱） |

> 注（2026-09-29，009/T2 落地后回填）：中断档位已按 CD-02 从 `{medium,high,critical}` 收窄为 `{high,critical}`（“有僵尸但无攻击植物”的独立条件不变）；上表与 §3 其余描述同步更新，V10 的文档一致性问题已消除。
| 目标仍差阳光 + 有行处于上述状态 | 全部 affordable | 先应对近处威胁 |
| 目标可支付 | 目标自身 + **surplus(sun−目标价)** 能支付的卡 | 小 surplus → 只出目标；大 surplus → 手牌重新全开 |
| 目标类型不在手/价格未知（过期目标） | 全部 affordable、不 hold | 失效目标不构成前提，fail-safe |

新增事实字段（随 plant/collect 请求下发，进 Trace 白名单）：

```json
"economy": {"sun": 7300, "band": "abundant", "cheapest_cost": 50, "highest_cost": 300,
            "sun_above_plan": 7250,
            "plan": {"type_name": "sunflower", "cost": 50, "payable": true, "shortfall": 0}}
```

`band` 由**这张手牌自己的价格阶梯**推出（scarce < 最低价 ≤ normal < 中位价 ≤ comfortable <
最高价 ≤ abundant），没有任何配置的 sun 阈值；每张卡在 `next_construction_type` 选项里附带
`low/mid/high price in hand` 的相对价格位置。plant 三处 instructions 追加固定
`ECONOMY_ANCHOR`（语义说明，不含阳光数字、不点名植物、不排序）。

## 4. 改动文件

| 文件 | 改动 |
|---|---|
| `jev/strategy.py` | 新增 `card_costs`/`card_price_band`/`economy_band`/`plan_facts`/`economy_facts`/`lane_needs_response`/`PlantSpendDecision`/`plant_spend_decision`；`build_plant_candidates(..., plan=)`；`management_facts(..., plan=)` 增 `economy` |
| `jev/client.py` | `decide_plant` **删除**意图手牌过滤，改传 `plan`；无候选时按 hold 原因返回；`build_plant_questions(..., plan=)`；`build_typesafe_state(..., plan=)`；`decide_shared` 下发 `economy` 并把 economy 传给 management 问题 |
| `jev/questions.py` | `ECONOMY_ANCHOR` + `_plant_economy_guidance()`（三处 plant 问题）；`PLANT_STATE_FIELDS` 增 `economy`；`management_questions(cards, economy=)` 增加相对价格位置与目标语义说明 |
| `jev/loop.py` | `_local_wait_reason` 用同一 `plant_spend_decision`，新增 `await_plan`；`_proposal_source_guard` 去掉 `intent_type_conflict`（保留 `intent_changed`） |
| `jev/trace.py` | `RELIABLE_OUTCOMES` 增 `await_plan`；`_actual_request_state` 增加 `economy` 有界投影 |
| `docs/architecture.md` | Decision/Scheduling 两段同步（economy、offer 规则、await_plan、reservation 语义） |
| `tests/test_jev_strategy.py` | 新增 `EconomyPlanAcceptanceTests`（14 项：band/价格档/hold/surplus/紧急覆盖/失效目标/economy facts） |
| `tests/test_jev_client.py` | 新增 `PlantPlanEconomyAcceptanceTests`（5 项：Case B 请求态、Case A 不发请求、surplus、shortfall、management 价格档）+ 三处 anchor 断言 |
| `tests/test_jev_loop.py` | 新增 4 项（`await_plan`、目标可支付后重开、紧急覆盖、Case B 全开、非目标类型可派发），修正 1 项旧断言 |
| `tests/test_jev_trace.py` | 新增 `await_plan` 可靠结论 + 带目标的 economy 白名单往返 + economy 出现断言 |

## 5. before / after（同一冻结样本，`uv run python tools/evidence-plan-economy.py --trace-file .log/jev-dashboard.jsonl`）

```
--- job-000010  sample 696  sun 7300
    declared goal        : sunflower (cost 50, payable True)
    balance band         : abundant   sun_above_plan: 7250
    BEFORE (goal filter) :   36 placements, types=['sunflower']
    AFTER  (goal context):  360 placements, types=[cabbage_pult, cherry_bomb, chomper, jalapeno,
                             melon_pult, peashooter, repeater, snow_pea, sunflower, tall_nut]
--- job-000016  sample 1413  sun 7375
    BEFORE 36 / 1 种 → AFTER 360 / 10 种
--- Case A sun 150  goal melon_pult(300): BEFORE 0 / []            AFTER 0 / []  hold=await_plan
--- Case A sun 320  goal melon_pult(300): BEFORE 37 ['melon_pult']  AFTER 37 ['melon_pult']
--- Case A sun 400  goal melon_pult(300): BEFORE 37 ['melon_pult']  AFTER 148 ['cabbage_pult',
                             'melon_pult', 'peashooter', 'sunflower']
```

测试：`uv run python -m unittest discover -s tests -p "test_*.py"` → **470 tests OK**
（本次新增 24 个用例：`test_jev_strategy` 12 / `test_jev_client` 6 / `test_jev_loop` 4 / `test_jev_trace` 2；
本次运行单实例锁空闲，9 个锁相关用例也通过）。

**尚未验证**：真实模型在两 Case 下的现场行为（需要 Human 授权的一局实机 + 真实 API）。

## 6. 新发现 / 未解决

1. **已批准计划与本次修复冲突，需 `$sdd-plan` 修订**：
   - OD-29「资源层……不做阳光预留」↔ 现在的 surplus 规则（`sun_above_plan` 限定候选）。
   - OD-38/plan §「为指定建设攒钱改由模型选 `none_of_the_above` 表达（目标候选只含当前可负担类型）」
     ↔ 现在的本地 `await_plan` 与「目标+surplus」候选。
   - R28「意图类别只表示动作能力 / 意图与费用不兼容可拒绝」与 plan 第 268 行「意图与目标语义冲突→拒绝」
     ↔ R29/OD-43「construction_intent 从授权前提降级为上下文」。两段文本本身就互相矛盾：
     修复选择按「上下文」实现（删掉类型守卫），若 Human 要保留「冲突即拒绝」语义必须回改。
2. **意图仍然由另一个分支在近零点差上改写**：`construction_intent` 是 argmax、无门槛、无 TTL，
   `keep`(0.49–0.59) 会长久维持 50 阳光目标。本次修复让「错的目标」不再截断候选空间，
   但「谁来决定目标、何时重新论证」仍是未解策略问题。
3. **约 40% 的 plant 决策仍在推理途中被 superseded**（process log：179/491）。已确认的诱因是
   意图版本与卡槽冷却/占用变化进入 key；本次未改 dedup 粒度。
4. **`StrategySignals.phase/economy_signal` 仍是 Trace-only**：真实的 economy 事实现在由
   `economy_facts` 承载并进入决策，但旧的 phase 分类仍无消费者（历史遗留，未清理）。
5. 本次会话中发现 `jev/loop.py::_branch_key` 的 collect key 一度缺少 `repr(self._last_result)`
   （与本次任务无关），已按 HEAD 恢复；如有并行会话在改同一文件需注意。

---

## 7. Human 决议与交付状态（2026-09-29 01:38，事后回填）

- **Human 决议：保持"代码代攒钱"方案（本文件 §3 的修复）**。即保留
  `plant_spend_decision` 的 surplus 规则与本地 `await_plan`；不改回"只给事实、攒钱由模型选弃选项决定"。
- 由此需要在下一次 `$sdd-plan` 中正式改写：OD-29（原"不做阳光预留"）、OD-38/§冷启动第 6 条
  （原"攒钱由模型选 `none_of_the_above` 表达、目标候选只含当前可负担类型"）、R28 与其相邻的
  "意图与目标语义冲突即拒绝"表述（与 R29/OD-43"意图仅提供上下文"二选一，本次实现选择了后者）。
- **交付事实**：`.sdd/007-dashboard-jev-runtime` 的交付提交 `7da972d`
  （`sdd(007): feat dashboard JEV runtime with option decision field`，已推送 `origin/main`）
  在暂存时一并带入了本文件 §4 对 `docs/architecture.md` 的经济段落。也就是说
  `7da972d` 的文档描述了该提交中尚不存在的 plan/economy 行为。因该提交已推送，不改写历史；
  本次经济改动落地的那次提交会让文档与代码一致，**建议在其 delivery 记录里注明
  "docs/architecture.md 的经济段落早于代码一个提交"**。
- 本次代码改动（`jev/strategy.py`、`jev/client.py`、`jev/questions.py`、`jev/loop.py`、
  `jev/trace.py` 与四个测试文件）在 007 交付时未被暂存，因此不在 `7da972d` 内。
