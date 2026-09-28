# Plan Index

## 1. Metadata

- Iteration: `007-dashboard-jev-runtime`
- Created at: 2026-09-28
- Status: **Revised, Pending re-approval**（2026-09-29 第 2 次修订：Verify 后发现实现结构与 Plan 脱节、并新增 R12；待 Human 批准）
- Owner: Human / Codex

## 2. Goal

把现有草坪、State、JEV 三页统一为简约、赛博朋克与像素元素结合的本机界面；将第三页改为可启动、观察、停止单个 JEV 进程的 JEV Runtime。Runtime 的主视觉是本局各类问题最新一组 option 的点阵：一个 option 一个点，只有被同任务成功游戏动作证实实际执行的点亮。游戏暂停、结束或退出时，沿用命令行 Loop 的停机语义，页面准确显示终态。

### Revision 2 (2026-09-29) — 实现事实对齐与新增 R12

第 1 次正式 Verify（`verify.md`，Overall **Failed** / Execution Complete）确认 Plan 与仓库已脱节，
且发现一项窄屏 G1 缺陷。本次修订只做三件事：把 Plan 对齐到实际实现、补记已有偏差、新增 R12。

1. **前端结构已变更（对齐事实）**：`dashboard/static/app.js` **已删除**，拆为
   `viewmodel.js`（唯一 schema 适配层，产出 RuntimeViewModel）+ `recording.js`（录制页控制器，
   只消费 VM）。新增 `dashboard/runtime_control.py`。旧 Plan 中所有“在 `app.js` 上 `node --check`”
   的验证路径（P02 Commands、Implementation evidence、V15/V16）一律改指这两个文件。
2. **录制页新增（对齐事实，属 Human 明确的直接任务）**：`/` 由「草坪主页」改为录制页，
   三区域为 **世界模型 / 精确 800×600 游戏窗口 / JEV 决策轨迹**。新增 `GET /api/catalog`
   （`configs/*.py` 是名称唯一真源，前端不再复制中英文对照表）；`/api/jev-options` 增加
   真实 `choice`、`decision`、`execution`。
3. **新增 R12（G1）**：录制页在窄屏下必须可用。Verify 实测 390px 时 `/` 横向溢出 640px
   （`docW 1132` vs `innerW 492`），根因 `.rt-bar` 无 `flex-wrap`，三组不换行 → 页头逐字换行、
   阶段标签重叠。**这是本次修订唯一的新增需求。**

**新增开发期工具（非产品依赖）**：`tools/dev-view.mjs`（Node + 本机 Edge CDP 截图/量测）、
`tools/fixtures/*.js`（固定样本预览与 VerVerify 量测）。它们不进入运行时，也不被 `STATIC_FILES` 服务。

**偏差清单（累计 10 项，其中 (8)(9) 已撤销）**：见 §8 Risks 的偏差条目。

### Requirement Baseline

| Requirement ID | Requirement | Source | Verification tier | Reason for tier |
|---|---|---|---|---|
| R1 | 三个现有页面统一改成简约 + 赛博朋克 + 像素视觉，保留信息可读、原有观察功能和小屏可用性 | Human 2026-09-28，三张现状截图仅作页面基线 | G1 | 用户直接要求的可见结果 |
| R2 | 第三页及三页导航由“JEV 时间线”改为“JEV Runtime”，可快速启动真实 `jev-loop` 子进程并显示运行状态 | Human 2026-09-28 | G1 | 核心控制路径 |
| R3 | 同一台本机同一仓库最多一个 JEV Loop；上一个未完全退出时不能启动下一个，包括网页与命令行竞争 | Human 2026-09-28“只能一个” | G1 | 防止重复决策及游戏输入 |
| R4 | STOP 可强制结束网页启动的 JEV 进程；退出后释放占用、允许下一次启动并明确显示结果 | Human 2026-09-28 | G1 | 生命周期闭环 |
| R5 | 游戏暂停、关卡结束、离开进行中阶段、进程断连时自动停机，与现有命令行 Loop 条件一致 | Human 2026-09-28；现有 `JevRuntimeLoop._state_stop_reason` | G1 | 避免游戏状态变化后继续动作 |
| R6 | Runtime 点阵平铺本局每类问题最新请求的**全部 option**，一 option 一点；不同 question ID 分组且不因 100 事件窗口漏选项，新 run 清空旧 option | Human 2026-09-28 纠正“每决策一点”并选择“每类问题最新一组” | G1 | 核心呈现路径与完整性 |
| R7 | 外部 CLI、配置/启动失败、HTTP 请求竞争与页面刷新时，状态不能谎报为可启动或运行成功 | 仓库调查推导 | G2 | 影响可信度；若能引发双启动则升级 G1 |
| R8 | 删除截图红框内的任务详情卡、决策/执行顺序列表及运行停止事件文字；点阵不再以点击展开底部日志 | Human 2026-09-28 截图与明确删除要求 | G1 | 明确的页面删改结果 |
| R9 | 只有与当前 question option、同源 job_id 对应且 `action_result.boundary.status == success` 的实际游戏动作使点亮灯；仅模型选中、未执行、作废或未确认均不亮 | Human 2026-09-28“那个执行了亮灯”及随后确认的文本模拟 | G1 | 避免把意图误报成执行 |
| R10 | 草坪主页“状态观察→僵尸详情”不再用固定窄列承载行摘要或僵尸字段：行标题（行号/数量/最近距离）独占整行，每只僵尸为独立信息块，名称、坐标、距离、HP 与证据分层且按字段可读换行；`X 836 · Y 430`、`最近：像素距离未获取 · 格距未获取`、`普通僵尸 · #0` 等短字段整体不断行，长 HP 说明在字段间换行而非逐字挤断 | Human 2026-09-28 僵尸详情截图；`style.css::.lane-row` 现为 `grid-template-columns: 56px minmax(0,1fr)`，`app.js::renderLanes` 把标题与详情分别放入该两列 | G1 | 当前截图显示主要信息逐字换行到不可读，直接摧毁观察用途 |
| R12 | 录制页在窄屏（约 390px）下必须可用：页头不得逐字换行、决策链四段不得互相叠压、页面不得出现横向溢出 | Human 2026-09-29 明确选择“1+3 直接完成”；`verify.md` §7-1 实测 `/` 溢出 640px | G1 | 直接决定录制页在非 2K 视口能否使用 |
| R11 | 草坪主页卡牌槽保持**单行横向滚动**（不屈从为多行网格），但每张卡有受控宽度且内部 2–3 层分行：槽位/类型名·编号、费用、冷却/卡牌可选各自成行；十张卡、未知类型（`未知植物 #4294967295`）、长编号及 `未获取`/`已就绪` 状态均完整可读，不再拼成一条横向长文本 | Human 2026-09-28 卡牌槽截图及本次明确选择；`style.css::.seed-card` 现为 `grid-template-columns: auto minmax(66px,auto) auto auto` 加 `min-width: max-content`，`app.js::renderCards` 将四个字段平铺进同一行 | G1 | 卡牌观察是主页主要功能，当前不可读且“部分字段未获取”提示与挤压排版叠加 |

## 3. Scope

### In scope

- 仅改现有本机 Dashboard 的三页、共用 CSS/JS、服务端受控接口和 JEV CLI 生命周期接入。
- 保持现有 State 采样和 Trace JSONL 的数据来源；点阵从 schema v2 Trace 派生，不让视觉状态驱动游戏动作。
- P02 修订须从配置的同一 Trace 文件投影本局每类问题最新 option 和同源动作结果；现有 `/api/jev-trace` 只读最近 100 事件，不足以保证长期运行时“全部最新 option”，需新增或扩展固定路径的只读摘要接口，不改变 Trace schema。
- P02 同步修正草坪主页的僵尸详情和卡牌槽布局；只调整已有 `renderLanes`、`renderCards` 与样式，保留 State 值、证据和交互。两项排版修订与 option 点阵在同一批实施和验收（OD-06），共用同一次 T8–T10 与浏览器审阅，不拆成前后两批。
- 无新第三方依赖；复用 Python 标准库、现有 `jev-loop` 和现有 `.log/` 目录。
- 因涉及 UI、HTTP、进程互斥、测试和文档，预期超过小改动基线；按独立结果拆成 P01/P02。

### Out of scope

- 不改变 JEV 策略、TypeSafe 请求、动作执行语义或游戏内 UI。
- 不支持远程访问、任意命令/参数或任意 Trace 路径由浏览器提交。
- 不要求页面接管在其他 Dashboard 实例或终端启动的进程；但必须检测其占用并拒绝第二个启动。
- 不改动 `.game/` 目标程序或已有 Trace schema。

## 4. Plan Catalog

| Plan ID | Plan | Main outcome | Depends on | Status | Link |
|---|---|---|---|---|---|
| P01 | JEV 进程生命周期 | 本机安全启动、唯一性、STOP、自动结束与状态接口 | None | Implemented | [plans/01-runtime-control.md](plans/01-runtime-control.md) |
| P02 | 三页视觉、option 点阵、主页排版与录制页 | 重做全部 option 点阵与执行亮灯，移除底部日志；僵尸详情去窄列、卡牌槽单行滚动内部分层；录制页三区域；**T11 修复窄屏布局** | P01 的状态接口契约 | Implemented（T1–T10）／**T11 Pending** | [plans/02-interface-and-decision-grid.md](plans/02-interface-and-decision-grid.md) |

## 5. Decision

- Open Decision：None。
- Confirmed Decision：OD-01（仅进行中 START）仍有效；OD-02（每 `job_end` 一个点）已被 Human 对实物 UI 的明确纠正取代。P02 的 OD-03（option 点阵、删除红框、成功执行才亮）、OD-04（本局每类问题最新一组）、OD-05（卡牌保留单行横向滚动）是当前用户决定；详见 P02。
- Confirmed Decision OD-06（2026-09-28，本次）：僵尸详情与卡牌槽两项排版修订作为 R10/R11 强化现有条目，与 option 点阵在 T5–T10 同批实施、同次验收，不拆批次、不新增独立需求 ID。详见 P02。

## 6. Task

- 先 P01 T1–T4：进程互斥与停止通路 → 服务端控制 API → CLI/Trace 集成与生命周期测试 → 用法文档。
- P02 T1–T4 是上一轮已实施的历史 Task，保留 backfill；T5（完整 option 摘要）→ T6（点阵替换和亮灯）→ T7（option 测试与文档）、T8（僵尸详情）、T9（卡牌横向卡片）、T10（主页布局验收）已于 2026-09-28 实施并回填。P01 未重做。
- **T11（本次新增，R12）**：修复 `/` 在窄屏下的布局——`.rt-bar` 允许换行、窄屏下三组纵向堆叠，
  决策链与 Position 在窄屏改为单列（沿用已有 `@media (max-width: 1280px)` 分支），确保 390px 无横向溢出、
  阶段标签不叠压。预期影响文件：`dashboard/static/style.css`（必要时 `index.html`）。
- T5–T10 是同一批修订（OD-06）：主页排版与 option 点阵一起实施、一起跑 T7/T10 的验收命令并做同一次回归。实施由 `$sdd-agents $sdd-implementation 007` 委派 3 个 `worker` 子代理、2 个波次完成（`tests/test_web.py` 与 `style.css` 按波次单一写者）；子代理不写 `.sdd/`，backfill 由主代理回写。
- 实施中的两处主代理修正：`#cards-list` 加 `tabindex="0"`（R11 键盘滚动）、`docs/architecture.md` 删除仍称 Dashboard 分别展示两种顺序的陈旧句子（R8）。

## 7. Validation

### Current delivery boundary

- 本次产物与实际用途：本机浏览器控制一局 JEV，并直接从 option 点阵看各类问题给了哪些选项、哪个选项有可证实的游戏执行。
- 本次交付成功的最小条件：原有单实例 START/STOP 与自动停机继续有效；本局每类问题最新 option 全部出现，种植/收集成功执行只点亮同源 option；红框内容完整移除；跨 run、延迟动作、无动作和 Trace 轮转不误亮；主页在截图所示场景下完整可读——僵尸详情的行摘要不再被 56px 列逐字挤断，卡牌槽十张卡保持单行横向滚动且卡内槽位/类型、费用、冷却状态分层可读；**录制页在 390px 视口下无横向溢出、页头不逐字换行、决策链四段不叠压（R12）**。
- 不作为本次交付门槛的场景：远程操作、多用户 Dashboard、跨机器单实例、旧 schema v1 的 option 还原；手机端触控交互与 <390px 视口。v1 没有完整问题 option 时只给兼容提示，不伪造点。

### Verification tiers

| Tier | Meaning | Handling in Verify |
|---|---|---|
| G1 核心路径 | 直接决定本次目标能否实现或结果是否可信 | 取得足够的进程、接口与浏览器证据；失败影响交付 |
| G2 当前风险 | 配置失败、外部 CLI、竞争、刷新等当前可能遇到的情形 | 记录影响和可接受条件；若造成重复进程或错误执行则升 G1 |
| G3 后续场景 | 远程、多用户、跨机器等未来用途 | 不纳入本轮验证，需求出现时重查 |

修订验证顺序：option 摘要的固定文件/多 run/长 Trace 确定性检查 → UI 的点数、亮灯与删改 DOM 检查 → 草坪主页长僵尸详情/十张未知卡牌样本的 DOM 与桌面/窄屏截图 → 受控游戏运行的 option 变化与成功动作对照。主页排版与点阵同批，主页检查与 UI 检查可在同一次浏览器审阅中完成。真机可能受游戏/API 可用性影响；若无法运行，G1 的现场证据缺失须如实标为未验证。

### Implementation status

T1–T10 已实施并回填（T5–T10 于 2026-09-28 由子代理委派完成）。已取得的确定性证据：`node --check` 两个脚本通过；全量 **443 tests OK**（含主页 DOM 与 option 点阵/亮灯/删改测试，解主代理复跑）；主代理另做独立摘要冒烟验证同源成功才亮、非成功不亮、迟到旧 job 不亮、管理选择恒暗、Noul 补数、新 run 清空。

**第 1 次 Verify 已取得的证据（2026-09-29，见 `verify.md`）**：全量 `unittest discover` **444 tests OK**；
`tests.test_web` 45 OK；四个 JS `node --check` 通过；V11 DOM **388 点 = 服务端 388 option**（300 条前置事件后 46/46 全键保真）；
V12 确定性 **6/6** + DOM 亮灯 1 = 服务端 executed 1；V7 控制边界 403×4 / 合法 409；V9 五种 Trace 状态各自正确；
V14 单次轮询 **0.250 ms**（预算 1000 ms）；V13 红框文案三页 0 命中；V15/V16 真实数据下 `nowrap` 全真、零溢出、十项一行。

**Verify 判定未过的项**：(a) **V6/R1** 390px 时 `/` 横向溢出 640px（→ 本次新增 R12 / T11）；
(b) **V13/R8** 单实例占用下点阵在 UI 中不可达（`/` 无 `#jev-timeline` 且无导航）。Human 已按 §9 接受 (b) 为当前剩余风险；
(a) 选择修复。

## 8. Risks

- 当前服务只接受 GET；新增 POST 控制端点须保持 `127.0.0.1` 绑定、固定路由、无浏览器参数拼接命令，并处理跨站提交风险。
- `jev-loop` 现会替换指定 Trace 文件；每次运行须有确定的文件归属和旧点清理/历史区分，避免旧点冒充新运行。
- Python 进程强制结束可能来不及写 `runtime_stop`；控制状态必须记录 STOP/退出码并独立于 Trace 表示终态。
- 现有测试含页面文案/CSS 静态断言；改版须更新与实际契约相关的断言，避免保留过时快照期望。
- 当前 `TraceFileReader.read` 仅返回 100 条，直接在前端从该窗口找“每类最新”会漏组；摘要须遵守固定配置路径、run_id 边界、完整行、文件替换/截断与长期运行性能，不把历史选项或动作混入新 run。
- `construction_intent`/`next_construction_type` 是经营选择，没有直接游戏动作；按“实际执行才亮”的要求保持暗点。collect 是 Noul `true|false`，成功 collect 才可亮 `true`；plant 需用 `target.type_name,row,col` 对齐 option。
- 主页当前 `.lane-row` 固定 56px 左列、`.seed-card` 使用 `min-width:max-content`，与长文本组合造成逐字换行及横向拥挤；排版修订不得隐藏未获取值、HP 证据或卡牌费用/冷却信息。
- 主页两处排版与 option 点阵同批实施（OD-06），会同时改动 `style.css`、`app.js` 与 `jev-page.js`；合并批次时须保证主页 DOM 断言（T8/T9）与点阵断言（T5/T6）在同一次 `tests/test_web.py` 运行中互不覆盖，避免一处样式修复回退另一处。
- 僵尸详情的 `未获取`/`待动态核验` 与卡牌的 `未获取` 费用、`卡牌可选: 否` 是真实采样事实，排版只能改变分行与层级，不能为了好看而隐藏、截断或改写这些状态。
- 工作区含 007 上一版尚未交付的实现和文档改动；修订实施时保留已完成 P01 与三页视觉，只替换 P02 的旧点阵及关联说明，不覆盖无关改动。
- 本次实施依赖子代理且其测试为自编自测；已在验证顺序中要求独立 Verifier 与 Human 现场取得浏览器/真机证据，不将“测试均通过”当作正式验证。

## 9. Approval

- Status: Approved
- Approved by: Human
- Approval date: 2026-09-28
- Notes: Human 在本次对话明确回复“approved”，批准经 OD-03/OD-04/OD-05/OD-06 修订后的 P02 与保持不变的 P01；无阻塞性 Open Decision。T1–T10 随后已实施并回填（T5–T10 由 `$sdd-agents $sdd-implementation 007` 委派，2026-09-28），全量 443 tests OK；仍未写 `verify.md`、未 commit/push，Verify 与 Delivery 需另行显式调用。
