# Delivery Report

## 1. Delivery Metadata

- Iteration: `007-dashboard-jev-runtime`
- Delivered at: 2026-09-29
- Branch: `main`（upstream `origin/main`）
- Commit type: `feat`
- Planned commit subject: `sdd(007): feat dashboard JEV runtime with option decision field`

## 2. Summary

把本机 Dashboard 从「阅读 Trace 的观察页」交付为**可控制一局 JEV 的运行时**，并把三页统一为一套暗色设计系统。

核心交付三件事：

1. **JEV 进程生命周期（P01）**：本机单实例锁 + START/STOP + 自动停机，网页与命令行竞争同一把锁。
2. **option 点阵（P02 / R6、R9）**：本局每个 question 最新一次请求的**全部 option** 各成一个点；只有被同源 `job_id` 且 `action_result.boundary.status == success` 证实的游戏动作才点亮。为此新增只读摘要接口 `GET /api/jev-options`，并删除红框内的任务详情、两种顺序列表、运行停止正文与点击展开日志。
3. **录制页 `/`（P02 + 本轮 T11）**：三区域布局——世界模型（5×9 草坪 + 目标/威胁）/ 精确 800×600 游戏窗口挂载点 / JEV 决策轨迹（OBSERVE › INTENT › OPTION › ACTION + Position 候选格点场）。

本轮（第 2 轮）额外完成 **R12/T11**：修复录制页在窄屏下的横向溢出与阶段叠压。

架构上把前端从单文件 `app.js` 拆为 **`viewmodel.js`（唯一 schema 适配层，产出 RuntimeViewModel）+ `recording.js`（录制页控制器，只消费 VM）**，并新增 `GET /api/catalog` 让 `configs/*.py` 成为名称唯一真源（前端不再复制 49 植物 / 34 僵尸 / 28 掉落的中英文对照表）。

## 3. What Changed

- **服务端**（`dashboard/server.py`，+484）：`OptionMatrixReader` 增量投影每类问题最新 option 集与同源成功执行；`GET /api/jev-options`、`GET /api/catalog`；`/api/jev-options` 增加真实 `choice`/`decision`/`execution`；`STATIC_FILES` 白名单更新。
- **进程控制**（`dashboard/runtime_control.py`，新增）：Windows 单实例 `RuntimeProcessLock` 与 JEV 子进程 START/STOP/自动停机状态机。
- **前端**：删除 `app.js`；新增 `viewmodel.js`、`recording.js`；`index.html` 改为录制页；`jev.html`/`state.html` 清理；`style.css` 重写为 token 化设计系统（+981 行）。
- **CLI**（`main.py`）：接入 Dashboard JEV Runtime 控制与锁。
- **测试**：`tests/test_web.py` 大幅重写（+1504/-…）；`tests/test_jev_cli.py` 增加锁用例。
- **文档**：`README.md`、`README.zh-CN.md`、`docs/architecture.md`、`docs/memory-map.md`、`docs/usage.md`。
- **工具**（`tools/`，新增）：`dev-view.mjs`（CDP 无头截图 + 几何量测，无 npm 依赖）、`fixtures/`（固定样本与窄屏探针）。
- **SDD**：`.sdd/007-dashboard-jev-runtime/`（plan-index、plans/01、plans/02、verify.md、本文件）。

## 4. Plan and Task Status

| Plan ID | Status | Completed Tasks | Incomplete Tasks | Notes |
|---|---|---|---|---|
| P01 | Implemented | T1–T4 | 无 | 单实例锁、STOP、CLI 集成、文档 |
| P02 | Implemented | T1–T11 | 无 | T1–T4 历史 backfill 保留；T5–T10 于 2026-09-28 委派完成；**T11 本轮完成**（R12 窄屏修复） |

## 5. Files Changed

见 `git show --stat <hash>`；§10 列出本次 commit 的完整范围。

## 6. Verification Result

- Overall result: **Passed**
- Evidence: `verify.md`

关键证据（第 2 轮复验，2026-09-29）：

| 检查 | 结果 |
|---|---|
| V17 / R12 窄屏（390/492/620/900/1280 五档） | 全部 `hOverflow=false`、`labelOverlaps=0`、`stageOverlaps=0` |
| V6 / R1 桌面 2560×1440 | `docH 1348 ≤ 1440`、游戏窗口精确 `800×600`、卡牌 10 项 1 行 |
| V11 / R6 点阵完整性 | DOM **388 点 = 服务端 388 option**；300 条前置事件后 46/46 全键保真 |
| V12 / R9 亮灯语义 | 确定性 **6/6**；DOM 亮灯 1 = 服务端 executed 1，aria 标「已证实执行」 |
| V7 / R2–R5 控制边界 | 403×4 / 合法 409；同源 `Origin` **与** `X-JEV-Control` 缺一不可 |
| V9 / R7 Trace 状态 | empty / missing / legacy / unconfigured / error 各自正确 |
| V14 / R6 性能 | 482 KB / 200 事件首扫 18.8 ms，增量 0.92 ms，单次轮询 **0.250 ms**（预算 1000 ms） |
| V13 / R8 删除项 | 红框文案三页 0 命中 |
| V15/V16 / R10,R11 | `nowrap` 全真、零溢出；卡牌 10 项 1 行 |
| `tests.test_web` | **45 OK** |

## 7. Deviations from Approved Plan

累计 10 项（其中 (8)(9) 已在第 2 次修订中撤销）：

1. 卡槽改为宽屏压缩到一行全显（与 R11/OD-05 措辞不完全一致）。
2. 点阵改为左右决策网络，不再按 R6/OD-04 分组平铺。
3. 页面内不加可见文字标签。
4. 删除英文小标题与页脚注释，界面统一中文。
5. 卡槽只留名称/费用/冷却进度条；僵尸详情精简为名称/位置/血量。
6. 删除三处状态徽章与僵尸坐标未舍入浮点。
7. JEV Runtime 一度改为霓虹 HUD 并内嵌主页 —— **后由第 2 次修订整体重做**。
8. ~~引入 vendored `augmented-ui`（打破“无新第三方依赖”约束）~~ —— **已撤销，`vendor/` 已删除，当前无第三方依赖**。
9. ~~整页霓虹化~~ —— **已撤销**。
10. **本轮新增**：录制页 `/` 改为三区域录制场景；前端拆为 `viewmodel.js` + `recording.js`；新增 `GET /api/catalog`；新增开发期工具 `tools/`（不参与运行时）。

## 8. Known Risks

- **单实例占用下点阵在 `/` 不可达**：`/api/jev-runtime` 为 `occupied` 时按钮禁用，且 `/` 无导航入口（需经 `/jev` 输入 URL）。**Human 2026-09-29 明确接受为当前剩余风险。**
- **录制页无页内导航**：R1 的「三页导航」按此限缩解释（录制页专注画面）。Human 同日接受。
- **未取得的现场证据**：Human 在真机对局中对 option 变化与成功动作的对照；窄屏修复后的 Human 现场目视（有主 agent 五档自动量测与截图替代）。
- **V14 用有界合成 Trace（482 KB）**替代多年 MB 样本；单次轮询 0.250 ms，距预算三个数量级。
- **`collect_target` 具体选项保持暗点**：Trace 剥离 item id，R9 只要求 `should_collect_now:true`。
- **Noul `false` 为原始 `1−p` 浮点**（未再取整）。

## 9. Follow-up Items

1. **`jev/` 越界改动必须另开 Iteration 交付**。工作区仍有 **10 个文件、约 872 行新增**未提交：
   `jev/strategy.py`(+278)、`jev/questions.py`(+82)、`jev/client.py`(+40)、`jev/trace.py`(+26)、
   `jev/loop.py`(+27)、`jev/scheduler.py`(+25)，以及 `tests/test_jev_*.py`(+450)。
   它们实现的是 **006 的 OD-41~OD-59 系列修订**（含 OD-47/R36 的 collect 轮询间隔与 collect 去重键修复），
   而 007 的 Scope 明确「不改变 JEV 策略」，因此**不属于本 Iteration**，本次 commit 已全部排除。
   证据：`tests.test_jev_loop.ManagementAcceptanceTests.test_model_can_wait_change_and_cancel_without_cheaper_substitute`
   当前失败（`'await_plan' != 'await_resource'`）；已用 `git stash push -- dashboard/static/style.css`
   证明该失败在 HEAD 的 CSS 下同样存在，与 007 无关。
2. 为上述 `jev/` 批次补 Plan 并单独 Verify + Delivery。
3. 若需在录制页直接展示 option 点阵，需新增区域（当前需经 `/jev`）。
4. `.log/jev-dashboard.jsonl`、`.log/jev-dashboard-process.log` 为运行期产物，未纳入提交。

## 10. Git Scope

- **Files intended for this Iteration commit**（17 改 + 5 增，共 22 项）：
  - `dashboard/server.py`、`dashboard/static/{index.html,jev.html,state.html,jev-page.js,style.css}`
  - `dashboard/static/app.js`（删除）
  - `dashboard/runtime_control.py`、`dashboard/static/{viewmodel.js,recording.js}`（新增）
  - `main.py`
  - `tests/test_web.py`、`tests/test_jev_cli.py`
  - `README.md`、`README.zh-CN.md`
  - `docs/{architecture.md,memory-map.md,usage.md}`
  - `.memory/{context.md,project-map.md}`
  - `.sdd/007-dashboard-jev-runtime/`（新增：plan-index、plans/01、plans/02、verify.md、delivery.md）
  - `tools/`（新增：dev-view.mjs、fixtures/*）
- **Unrelated working-tree files explicitly excluded**（**不得提交**）：
  `jev/client.py`、`jev/loop.py`、`jev/questions.py`、`jev/scheduler.py`、`jev/strategy.py`、`jev/trace.py`、
  `tests/test_jev_client.py`、`tests/test_jev_loop.py`、`tests/test_jev_scheduler.py`、`tests/test_jev_strategy.py`
  （共约 872 行，属 006 的后续修订，见 §9-1）；以及 `.log/` 下运行期产物。
- **Remote / branch intended for push**: `origin` / `main`
