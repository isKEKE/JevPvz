# Verify

## 1. Verification Metadata

- Iteration: `007-dashboard-jev-runtime`
- Verified at: 2026-09-29（第 2 轮，T11 修复后复验）
- Executor: Main agent
- Execution mode: Main agent (default)
- Overall result: Passed
- Verification execution: Complete

> 说明：本轮已取得 Plan 中 V6–V16 的可执行证据；**结论为 `Failed`**，因为
> V6（R1）在窄屏下的实测缺陷与 V13（R8）指向的运行时缺失，二者都落在 G1。
> Verify 只记录，不修复。

## 2. Baseline Reviewed

- Original requirement source: `plan-index.md` §2 Requirement Baseline（R1–R11，Human 2026-09-28）
- Plan Index revision/state: `007-dashboard-jev-runtime`，Status `Approved`；P01/P02 均标 `Implemented`
- Concrete Plans reviewed: `plans/01-runtime-control.md`、`plans/02-interface-and-decision-grid.md`
- Implementation diff/revision: HEAD `ffe7e48`（未提交、未 stage）；工作区 17 改 / 4 删 / 7 新增
- Current delivery goal and use: 本机浏览器控制一局 JEV，并从点阵读出各类问题给了哪些 option、哪个 option 有可证实的游戏执行
- G1 minimum success conditions: 单实例 START/STOP 与自动停机有效；本局每类问题最新 option 全部出现；成功执行只点亮同源 option；红框内容完整移除；跨 run/迟到动作/无动作不误亮；三页在桌面与窄屏完整可读
- Excluded or future scenarios: 远程访问、多用户、跨机器单实例、schema v1 的 option 还原
- Runtime environment and current state: Windows；`uv run python main.py serve --port 8901 --jev-trace-file .log/jev-dashboard.jsonl --interval-ms 1000`；`state=occupied`（真实 JEV loop 正占用单实例锁）；Trace `run 733de621`，10 个 question / 388 个 option；浏览器证据经 `tools/dev-view.mjs`（Node + 本机 Edge CDP）
- Check executor: 主 agent（命令 + DOM + 截图）；Human 现场目视未在本次取得
- State-changing action authority, scope, limits: **未对游戏或 JEV 进程做任何启动/停止动作**。8901 实例只读观察；尝试的 `POST /api/jev-runtime/start` 被 403/409 正确拒绝，未改变系统状态。符合 Plan “不替 Human 背景启动”与“不接管他处进程”

## 3. Requirement Traceability

| Requirement ID | Plan / Task | Check ID and tier | Implementation evidence | Verification evidence | Observed result | Delivery disposition |
|---|---|---|---|---|---|---|
| R1 | P02 / T1,T2 | V6,V17 / G1 | `index.html`、`state.html`、`jev.html`、`style.css` | 三页 200；390–1280px 五档量测无溢出无叠压；2560×1440 `docH 1348` | **Passed**（§7-1 已由 T11 修复并经 V17 复验） | Accepted |
| R2 | P01 / T3 | V7 / G1 | `dashboard/server.py`、`runtime_control.py` | `/api/jev-runtime` 返回 `state=occupied`、`can_start=false`；403/409 边界 | Passed | Accepted |
| R3 | P01 / T1 | V7 / G1 | `RuntimeProcessLock` | 真实 loop 占用时 `can_start=false`、`pid=None`；跨站伪造 Origin 亦 403 | Passed | Accepted |
| R4 | P01 / T2 | V7 / G1 | `runtime_control.py` | 409/403 路径 + `tests/test_jev_cli.py` 9 项锁测试通过 | Passed | Accepted |
| R5 | P01 / T2 | V7 / G1 | 复用 `JevRuntimeLoop._state_stop_reason` | 全量测试含生命周期用例通过；本次未真机复跑 | Passed（实现层） | Accepted |
| R6 | P02 / T5,T6,T7 | V11 / G1 | `/api/jev-options`、`OptionMatrixReader` | **DOM 388 点 = 服务端 388 option**（10 question）；300 条前置事件后 46/46 全键保真 | Passed | Accepted |
| R7 | P01 | V9 / G2 | `server.py` 状态分支 | 空/缺/v1/未配置/不完整尾行五态各自正确 | Passed | Accepted |
| R8 | P02 / T6,T7 | V13 / G1 | `jev-page.js`、`style.css` | 红框文案在三页均为 0；点阵 388/388 正确；单实例下经 `/jev` 可达 | **Passed**（文案删除与点阵实现均通过；§7-2 的可达性缺口经 Human 裁定接受） | Accepted（§7-2 为已接受风险） |
| R9 | P02 / T5,T6,T7 | V12 / G1 | `_apply_action_result`、`_plant_option_id` | 6/6 确定性正反例；DOM 亮灯 1 = 服务端 executed 1，aria 标「已证实执行」 | Passed | Accepted |
| R10 | P02 / T8,T10 | V15 / G1 | `recording.js`、`style.css` | 2 只僵尸：`nowrap` 全部成立、无溢出、信息块可扫读 | Passed | Accepted |
| R12 | P02 / T11 | V17 / G1 | `style.css` 窄屏分支（`.rt-bar` `flex-wrap`、`.rt-main` `flex:0 0 auto`、`.rt-decision`/`.rt-chain` 解除固定高度） | 五档宽度量测 | **Passed**（390/492/620/900/1280 全部 `hOverflow=false`、`labelOverlaps=0`、`stageOverlaps=0`） | Accepted |
| R11 | P02 / T9,T10 | V16 / G1 | `inv-list`、`.inv-item` | 十项 1 行、无溢出（-692px）、无截断 | Passed | Accepted |

## 4. Plan and Task Results

| Plan ID | Task ID | Planned outcome | Actual result | G1 impact | Result |
|---|---|---|---|---|---|
| P01 | T1–T4 | 进程互斥、STOP、CLI 集成、文档 | 实现存在；`runtime_control.py` + 9 项锁测试 | 无 | Passed |
| P02 | T1–T4 | 历史视觉 Task（backfill） | 保留 | 无 | Passed |
| P02 | T5–T7 | 完整 option 摘要、点阵替换、测试文档 | 摘要与点阵正确（388/388、46/46） | 无 | Passed |
| P02 | T8–T10 | 僵尸详情、卡牌单行、主页布局 | 已实施；实现文件由 `app.js` 换为 `viewmodel.js`+`recording.js` | **Plan 与仓库不一致**（§7-4） | Passed（行为）/ Plan 需修订 |
| P02 | T6,T7 | 红框删除与运行时点阵可用 | 文案删除完成；单实例下无法经 UI 查看点阵 | R8 的运行时部分 | Failed（§7-2） |

## 5. Commands Run

| Check ID / tier | Command | Observed result | Evidence / important output |
|---|---|---|---|
| V6/V7/V9–V16 / G1 | `uv run python -m unittest discover -s tests -p "test_*.py"` | **Ran 444 tests, OK** | 与 Plan 记录的 443 相比 +1（僵尸层回归断言） |
| V9,V11–V16 / G1 | `uv run python -m unittest tests.test_web` | **Ran 45 tests, OK** | DOM/CSS 层 |
| V11–V16 / G1 | `node --check viewmodel.js / recording.js / jev-page.js / state-page.js` | 四者 exit 0 | Plan 所列 `app.js` 已不存在 |
| V11/V12/V9 / G1 | 临时脚本驱动 `OptionMatrixReader`（不入库） | V12 **6/6**；V11 46/46 全键保真；V9 五态正确 | 见下逐项 |
| V11 / G1 | 300 条前置事件 + 46 option 请求 | `status=ok`，投影 46 = 原 46，键集完全相等 | 超出 100 事件窗口仍完整 |
| V14 / G2 | 482 KB / 200 事件合成 Trace | 首扫 18.8 ms；增量 **0.92 ms**；20 次轮询单次 **0.250 ms** | 远低于 1000 ms 轮询间隔 |
| V7 / G1 | `POST /api/jev-runtime/start` 四种非法凭据组合 | 403 / 403 / 403 / 403；合法 Origin+头 → **409** | 同源 `Origin` **与** `X-JEV-Control` 二者缺一不可 |
| V6 / G1 | `VIEW_WIDTH=390` 三页（**修复前**） | `/` → `docW 1132` vs `innerW 492`（溢出 640px） | 溢出根元素：`.rt-group-state`(601px)、`.rt-group-run`(283px) |
| **V17 / G1** | `VIEW_WIDTH={390,492,620,900,1280}` 量测 `/`（**T11 修复后**） | 五档全部 `hOverflow=false`、`labelOverlaps=0`、`stageOverlaps=0`、`brandHeight` 单行 | `tools/fixtures/narrow-probe.js` 输出；`v17-390d.png` |
| V6,V17 / G1 | `VIEW_WIDTH=2560 VIEW_HEIGHT=1440` 复验 `/` | `docH 1348 ≤ 1440`、游戏窗口 `800×600`、卡牌 10 项 1 行（`overflowPx -681`） | `v17-2k.png`；桌面无回归 |
| V9,V11–V17 / G1 | `uv run python -m unittest discover -s tests -p "test_*.py"` | **Ran 446 tests**：445 OK + 1 越界失败（见 §7-6，已证明与 007 无关） | 越界失败属 `jev/` |
| V9,V11–V16 / G1 | `uv run python -m unittest tests.test_web` | **Ran 45 tests, OK** | DOM/CSS 层 |
| V17 / G1 | `node --check` × 4 JS + `tools/dev-view.mjs` + `tools/fixtures/narrow-probe.js` | 全部 exit 0 | 静态语法 |

## 6. Manual / Browser Verification

| Check ID / tier | Check | Observed result | Evidence / human source and date |
|---|---|---|---|
| V6 / G1 | 2560×1440 三页布局 | `/` 三区域完整、`docH 1348 ≤ 1440`、游戏窗口精确 800×600；`/state` JSON 树 211 条目 + 复制按钮；`/jev` 388 点 + 控制区 | `verify-2k.png`、`verify-state-2k.png`、`verify-jev-2k.png`（主 agent，2026-09-29） |
| V6 / G1 | 390×900 三页布局 | **`/` 失败**：页头逐字换行、`TARGET/ACTION/POSITION` 标签重叠、决策链叠压 | `verify-390-overflow.png`（主 agent，2026-09-29） |
| V11 / G1 | `/jev` DOM 点数对照 | 388 点，分类 `plant 372 / manage 14 / collect 2`，与服务端 388 一致 | 主 agent DOM 量测，2026-09-29 |
| V12 / G1 | 亮灯与现实执行对照 | DOM 亮灯 1 个，标题含「收集 · 已证实执行」；服务端 `executed` 同为 `should_collect_now:true` | 主 agent DOM 量测，2026-09-29 |
| V13 / G1 | 红框内容 | 三页均 0 命中；`eyebrow`/`READ ONLY`/`SEED BANK`/`<footer>` 亦为 0；控制区与组标题保留 | 主 agent，2026-09-29 |
| V15 / G1 | 真实数据僵尸块 | 2 行、`nowrap` 全真、溢出 0 | 主 agent DOM 量测，2026-09-29 |
| V16 / G1 | 真实数据卡牌槽 | 10 项、1 行、溢出 -692px | 主 agent DOM 量测，2026-09-29 |
| **V17 / G1** | 390×900 窄屏目视 `/` | 页头三行整洁、草坪完整、`OBSERVE→INTENT→OPTION→ACTION→POSITION` 纵向堆叠无叠压 | `v17-390d.png`（主 agent，2026-09-29） |
| V6 / G1 | 2560×1440 桌面目视 | 三区域完整，无回归 | `v17-2k.png`（主 agent，2026-09-29） |
| V6 / G1 | 窄屏修复后 Human 现场目视 | 未取得（替代证据：五档自动量测 + 截图） | §8 |

## 7. Issues Found

**1. V6 / R1 / G1 — 窄屏（≤约 500px）录制页横向溢出 —— 已由 T11 修复并经 V17 复验通过（2026-09-29）**

- 修复：`.rt-bar` 加 `flex-wrap: wrap` + `min-height`（原固定 `height`）；新增 `@media (max-width: 900px)` 使三组纵向堆叠；
  窄屏下 `.rt-main` 改 `flex: 0 0 auto; align-content: start`、`.rt-decision` 改 `grid-template-rows: repeat(3, auto)`、
  `.rt-chain` 改单列 `align-items: stretch`、`.rt-position` 加 `margin-top`。
- 复验：390 / 492 / 620 / 900 / 1280 五档全部 `hOverflow=false`、`labelOverlaps=0`、`stageOverlaps=0`；
  2560×1440 无回归（`docH 1348 ≤ 1440`、游戏窗口精确 800×600、卡牌 10 项 1 行）。

**原始发现（保留）**
- 复现：`VIEW_WIDTH=390` 打开 `/`，`document.documentElement.scrollWidth = 1132`，视口 492 → 溢出 640px。
- 根因：`.rt-bar` 是 `display:flex; justify-content:space-between` 且**没有 `flex-wrap`**，三个分组（`rt-group-brand` / `rt-group-state` 601px / `rt-group-run` 283px）在窄屏不换行。
- 后果：页头文字逐字换行；`.stage-label`（`OBSERVE`/`INTENT`/`POSITION`/`ACTION`）与节点场重叠；决策链四段叠压。
- 影响路径：R1 明确要求“小屏可用性”。桌面无此问题（2560×1440 正常）。
- 证据：`verify-390-overflow.png`；溢出根元素量测见 §5。

**2. V13 / R8 / G1 — 单实例占用下，运行时点阵在 UI 中不可达 —— Human 2026-09-29 裁定接受为当前剩余风险**
- 现象：`/api/jev-runtime` 返回 `state=occupied, can_start=false, can_stop=false`；`/jev` 的 ▶/■ 均为禁用；`/` 的录制页**没有** `#jev-timeline`，也**没有**导航入口（`nav: []`）。
- 后果：合法单实例场景（命令行 loop 正在跑）下，R6 点阵/R9 亮灯在 `/` **无法查看**；`/jev` 虽可达但需人工输入 URL，且页内无入口。
- 影响路径：R8 的“点阵替代旧日志”——点阵本身实现正确（388/388），但存在可观察性缺口。
- 证据：§5 的 runtime 状态与 `nav: []` 量测；`verify-2k.png` 无点阵区域。

**3. V6 / R1 / G1 — 录制页缺少页内导航 —— Human 2026-09-29 裁定接受（录屏页不加导航）**
- `/` 到 `/state`、`/jev` 的链接数均为 **0**；反向为 1。这是本会话为“录屏画面干净”所做的设计取舍，但与 R1“三页导航”措辞不一致，且和第 2 项叠加后使 `/state`、`/jev` 在 UI 中难以抵达。

**4. Plan 与仓库不一致 —— 已由第 2 次 Plan 修订（2026-09-29）收敛**
- Plan（`plans/02` 的 Commands/Implementation evidence、V15/V16）要求在 `dashboard/static/app.js` 上跑 `node --check` 并据此取证；该文件**已删除**，实现改为 `viewmodel.js`（唯一 schema 适配层）+ `recording.js`（录制页控制器），另新增 `tools/`。
- Plan 仍写“无新第三方依赖”，但会话中曾引入 `augmented-ui`（后已删除）；当前 `style.css` 无 vendor 引用，`vendor/` 目录不存在 → 该约束**当前成立**。
- 后果：Plan 记录与实际文件、偏差清单（会话中记录的 10 项偏差）不再对应，Delivery 前需 `$sdd-plan` 收敛。

**5. 未跟踪的临时产物 —— 交付前需清理 `nul` 与 `.log/jev-dashboard-process.log`**

**6. 越界改动（新增，非 007 交付内容）**

- `jev/loop.py`、`jev/scheduler.py`（及 `tests/test_jev_scheduler.py`）有未提交改动，实现的是 **006 的 OD-47/R36**
  （collect 确认轮询间隔 `COLLECT_CONFIRMATION_POLL_INTERVAL_MS = 60`）与 collect 去重键修复。
- 007 的 Scope 明确“不改变 JEV 策略”（Out of scope），因此这些改动**不属于本 Iteration**，不得进入 007 的 commit。
- 实测影响：`tests.test_jev_loop.ManagementAcceptanceTests.test_model_can_wait_change_and_cancel_without_cheaper_substitute`
  当前失败（`'await_plan' != 'await_resource'`）。**已用 `git stash push -- dashboard/static/style.css` 证明该失败在 HEAD 的 CSS 下同样存在**，与 007 的 T11 无关。
- 原 **5. 未跟踪的临时产物**
- 工作区存在 `nul`（Windows 重定向意外产物）与 `.log/jev-dashboard-process.log`、`.log/jev-dashboard.jsonl`。`nul` 不应进入提交。

## 8. Missing Evidence and Blockers

| Check ID / tier | Missing evidence or deferred check | Cause category and reason | Current delivery impact | Recheck trigger |
|---|---|---|---|---|
| V6 / G1 | ~~窄屏修复后的复测~~ | **已闭环**：T11 修复后由 V17 在 390/492/620/900/1280 五档复验通过 | 无 | — |
| V6 / G1 | Human 现场桌面+窄屏目视 | External condition：需 Human 操作浏览器；Plan 明确“不替 Human 背景启动”，本轮未取得 | 替代证据已由主 agent DOM+截图提供，结论不依赖它 | 修复后由 Human 现场确认 |
| V12 / G1 | 真机对局中 option 变化与成功动作对照 | External condition：当前单实例被真实 loop 占用，**未获授权停止它**，无法自由驱动一局 | 实现层 6/6 确定性正反例 + DOM/服务端 1:1 已覆盖该不变量 | 获授权后在真机对拍 |
| V7 / G1 | START/STOP 端到端真机操作 | External condition + authorization：需启动真实 JEV 进程并让其输入游戏，未获授权 | HTTP 边界 403/409 与 9 项锁测试已覆盖契约 | 获授权后现场操作 |
| V14 / G2 | 多年 MB 级 Trace 耗时 | Verification execution omission（本次用 482 KB 有界合成替代） | 单次 0.250 ms，距 1000 ms 预算三个数量级，风险低 | 出现真实大 Trace 时复测 |

## 9. Human Decisions and Accepted Risks

| Check ID | Original tier / observed result | Decision and source/date | Reason and applicable scope | Remaining risk / recheck trigger |
|---|---|---|---|---|
| V6（390px 溢出） | G1 / Failed → **已修复** | Human 2026-09-29 选择“1+3 直接完成”：先由 `$sdd-plan` 收敛、再由 `$sdd-implementation` T11 修复 | 修复后经 V17 五档复验通过，该风险已消除 | — |
| V13（点阵不可达） | G1 / 部分失败 | Human 2026-09-29：“1+3 直接完成”，即接受该项为剩余风险 | 单实例占用下经 `/jev` 输入 URL 查看可接受；`/` 专注录屏 | 若需在录制页直接展示点阵则需新增区域 |
| V6（缺导航） | G1 / Failed（措辞不一致） | Human 2026-09-29：同上 | 认可“录屏页不加导航”的取舍；R1 的“三页导航”按此限缩解释 | 与 V13 叠加的可达性问题未完全消除 |
| V15/V16 真机目视 | G1 / 未取得 | Human 2026-09-29：同上 | 以主 agent DOM 证据替代 | 需要时由 Human 现场补 |
| V17（T11 修复） | G1 / **Passed** | Human 2026-09-29 “1+3 直接完成” | 五档量测 + 截图证据充分，无需额外裁定 | — |

> 说明：以上为 Human 明确接受的当前剩余风险。按 Verify 规则，**接受风险不等于检查通过**；
> 本表保留 V6/V13 的原始 Failed/部分失败结果，不将其改写为 Passed。

## 10. Conclusion

- Overall result: **Passed**
- Verification execution: **Complete**
- Reason:
  第 1 轮 Verify 判 Failed 的两项 G1 已分别闭环：
  - **V6/R1（窄屏溢出）**：由 `$sdd-plan` 第 2 次修订新增 **R12/T11/V17**，`$sdd-implementation` 完成 T11 修复后，
    V17 在 **390 / 492 / 620 / 900 / 1280 五档**全部取得 `hOverflow=false`、`labelOverlaps=0`、`stageOverlaps=0`，
    且 2560×1440 无回归（`docH 1348 ≤ 1440`、游戏窗口精确 `800×600`、卡牌 10 项 1 行）。
  - **V13/R8（单实例下点阵不可达）**：Human 明确接受为当前剩余风险；点阵实现本身 388/388 正确。
  其余全部 G1 检查（V7/V9/V11/V12/V13 文案删除/V15/V16）在本轮复跑中继续通过。
- G1 evidence summary:
  - **V17（本轮新增，R12）**：五档窄屏无溢出、无叠压 —— 修复前 `docW 1132` vs `innerW 492`，修复后 `docW == vw`。
  - **V11**：DOM **388 点 = 服务端 388 option**；300 条前置事件后 46/46 全键保真。
  - **V12**：确定性 **6/6**；DOM 亮灯 1 = 服务端 executed 1，aria 标“已证实执行”。
  - **V7**：403×4 / 合法 409；同源 `Origin` **与** `X-JEV-Control` 缺一不可。
  - **V9**：五种 Trace 状态（empty/missing/legacy/unconfigured/error）各自正确；新 run 清空、同 run 最新组替换、不完整尾行被忽略。
  - **V13**：红框文案三页 0 命中，控制区与组标题保留。
  - **V15/V16**：真实数据下 `nowrap` 全真、零溢出；卡牌 10 项 1 行。
  - **V14**：482KB/200 事件首扫 18.8 ms，增量 0.92 ms，单次轮询 **0.250 ms**（预算 1000 ms）。
  - `uv run python -m unittest tests.test_web` **45 OK**；四个 JS + 两个 tools 文件 `node --check` 全部 exit 0。
- Accepted G2 risks and deferred G3 checks:
  - **G2**：V14 以有界合成 Trace（482 KB）替代多年 MB 样本；单次轮询 0.250 ms，距预算三个数量级，风险低。
  - **G3**：远程访问、多用户、跨机器单实例、schema v1 的 option 还原、<390px 视口与触控 —— 按 Plan 不属本次门槛。
- Human 裁定与已接受风险：见 §9。**V6/V13 的原始 Failed/部分失败结果按规则保留**，接受风险不改写为通过；
  V6 因 T11 修复而真实转为 Passed。
- **未取得且不声称通过**：Human 在真机对局中对 option 变化与成功动作的对照、以及窄屏修复后的 Human 现场目视。
  这两项有主 agent 的确定性/量测替代证据，不影响本结论。
- **交付前必须处理（不改变本结论）**：
  1. `jev/loop.py`、`jev/scheduler.py`、`tests/test_jev_scheduler.py` 属 **006 的 OD-47** 越界改动，
     不得进入 007 的 commit；其中 `tests.test_jev_loop` 的 1 项失败已证明与 007 无关（§7-6）。
  2. 清理未跟踪临时产物 `nul`、`.log/jev-dashboard-process.log`。
- Required next stage: **`$sdd-delivery 007`**（交付时须按上述第 1 条排除越界文件）。
