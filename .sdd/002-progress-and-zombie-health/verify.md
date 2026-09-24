# Verify

## 1. Verification Metadata

- Iteration: `002-progress-and-zombie-health`
- Verified at: 2026-09-24（Asia/Shanghai；现场采样时间见下文 UTC 时间戳）
- Verifier: 独立 fresh-context verifier sub-agent（未参与本轮 Implementation）
- Overall result: **Passed**

## 2. Baseline Reviewed

- Original requirement source: 用户提出场景/模式/关卡/波次读数、单字节暂停/完成、僵尸本体与装备 HP、同格植物叠放及草坪全空问题；用户本次表示亲自试用未发现问题，并提供两张新页面截图（`C:\Users\86131\AppData\Local\Temp\codex-clipboard-b96b9784-ba3a-4e2a-8bd6-f212ebb6b8fa.png`、`...790bd04e-ab17-4dbe-ad2f-a9e2f4b10b9c.png`）。截图仅作为页面显示证据，不当作同帧游戏/raw 证据。
- Plan Index revision/state: `.sdd/002-progress-and-zombie-health/plan-index.md`，R1–R9 均为 mandatory，Status/Approval 均为 Approved；P01/P02/P03 均 Approved，T1 均 `[x]` 且有 Implementation backfill。
- Concrete Plans reviewed: `plans/01-game-progress.md`、`plans/02-zombie-health.md`、`plans/03-layered-plants.md`；批准范围与 R1–R9 一致。
- Implementation diff/revision: 当前 HEAD 为 `ce72337 init`；002 与大部分源码、测试均为未跟踪文件，`git diff` 无法表示完整实现。逐一审阅当前工作树的 `configs/pvz_1051.py`、`game/reader.py`、`state/builder.py`、`dashboard/static/app.js`、`dashboard/server.py`、相关测试、`docs/memory-map.md`、`pyproject.toml`、`README.md`；三个 Task 的 Actual files 与现存实现相符。另有 `.codex/config.toml`、`.gitignore`、`.memory/*` 改动，未纳入本次验证的功能结论。

## 3. Requirement Traceability

| Requirement ID | Plan / Task | Implementation evidence | Verification evidence | Result |
|---|---|---|---|---|
| R1 | P01 / T1 | `configs/pvz_1051.py::CANDIDATE_OFFSETS["scene"]`；`game/reader.py::read_game_progress`；`state/builder.py` 场景/模式枚举及 raw code；`app.js::renderGame` | 当前同帧 raw `scene=3, mode=1` → State“正在游玩 / 生存模式（普通，第 1 阶段）”；新服务浏览器 AX 树显示名称和码 3/1。`test_state.py::test_progress_maps_codes_keeps_unknowns_and_reports_per_field_evidence` 覆盖未知码。 | Passed |
| R2 | P01 / T1 | `read_game_progress` 单独读取 background/level/current_wave/total_waves；`build_state` 仅 mode 0 的 1–50 关映射冒险标签；`renderGame` 标“已生成” | 同帧 raw `0/0/10/10` → State 场地白天、原始关卡 0、10/10 波；浏览器一致。`test_state.py` 检查冒险 15→2-5、50→5-10，生存模式不套公式，菜单隐藏旧 Board 值。 | Passed |
| R3 | P01 / T1 | `game/reader.py::_candidate_u8_fields` 使用 `read_bytes(..., 1)` 读取 `pause_flag`/`won_flag`；State 只接受 0/1 | `test_reader.py::test_progress_reads_single_byte_flags_and_preserves_other_progress_codes` 用非零邻字节；`test_state.py::test_progress_flags_reject_wide_legacy_values_instead_of_truthiness` 拒绝旧四字节值。现场 raw 为 1/0，State 为 `True/False`，浏览器显示“是/否”。 | Passed |
| R4 | P02 / T1 | `FIELD_OFFSETS["zombies"]` 的 C8/D0/DC/E4；`read_zombies` 按 i32 分读；`build_state` 保留 `hp=body_hp`、非负装备值、可空 `total_hp`；`renderLanes` 与覆盖提示限定“数值参考” | `test_reader.py` 与 `test_state.py` 覆盖路障、铁桶、铁门、气球、无甲、缺分量。新 API 的铁门样本本体 45 + 盾牌 892 = 937；浏览器同名部位和合计说明。P02 记录先前铁桶同帧 270+1100=1370；本次现场另见带头盔僵尸。 | Passed |
| R5 | P01/P02 / T1 | `build_state` 逐进度字段写 availability/evidence、保留 `progress_raw`，装备缺值合计为 null；`server.py::StatePoller/DashboardHandler` 发布完整快照 | 新服务 `GET /api/state` HTTP 200、`Cache-Control: no-store`；其 State 为 `ok`，50 株、场景/模式/波次/暂停与浏览器相邻样本一致。浏览器 AX 树显示逐字段“待动态核验”、原始码、HP 分量；固定样本覆盖 unknown/unavailable/error。 | Passed |
| R6 | P01/P02 / T1 | `runtime/memory.py` 仅请求 `PROCESS_VM_READ` 与查询权限；`runtime/process.py` 仅查询/读取；无写内存/游戏输入调用 | 34 项测试、编译、JS 语法、命名检查通过；只读 `probe`、`snapshot --once` 与本地 API 成功。动态事件未人为制造，候选含义维持 `provisional`。 | Passed |
| R7 | P03 / T1 | `build_state` 按坐标聚合 `cell.plants`，以主体→南瓜头→承载层稳定排序，顶层 `plants` 保留实体 ID、类型、行列 | 2026-09-24T08:09:45.921Z 同一 raw/State：raw reported/scanned 50/50、44 占用格、6 叠放格；State `ok`、50/44/6、逐格数量和 50、全部 ID 集合相等，(0,6) 同格含高坚果与南瓜头。双数组顺序、承载层、三株与槽位交换测试通过。 | Passed |
| R8 | P03 / T1 | `app.js::renderBoard` 遍历 `cell.plants`，失败、未获取、空格分别显示；类型码写入格子提示 | 新服务浏览器 AX 树：5×9 全部格可见，(0,6)/(0,7) 均显示“高坚果 南瓜头”且提示有类型码 23/30，(2,7) 为“当前无植物；可种规则未获取”。合成读取失败页面 45 格均为“植物读取失败”，`empty` 格为 0。用户新截图亦显示完整草坪及叠放名称。 | Passed |
| R9 | P03 / T1 | `build_state` 对越界/非法类型及数组活数不符设 `error`、`plants=null`；`capture_state` 不一致时重采一次 | `test_state.py::test_invalid_plant_and_count_mismatch_are_explicit_errors` 与 `test_read_failure_is_distinct_from_a_successful_empty_array` 通过；现场同帧 raw/State 为 50/44/6/50 且错误 0；新 API 相邻采样仍为 50/44/6。真实用户页面截图与现场数量 50 一致，但不是原子同帧。 | Passed |

## 4. Plan and Task Results

| Plan ID | Task ID | Planned outcome | Actual result | Result |
|---|---|---|---|---|
| P01 | T1 | 独立进度字段、单字节布尔、保守语义与网页 | 代码、固定样本、现场 raw→State 及浏览器显示均符合；未经动态核验的字段仍标 provisional。 | Passed |
| P02 | T1 | 分层 HP 和参考合计 | 固定样本、现场盾牌/头盔读数、API/浏览器文案符合；缺分量不伪造总值。 | Passed |
| P03 | T1 | 多株聚合与错误/空格区分 | 同帧 raw/State 数量与 ID 一致；浏览器正例和合成失败例均符合。 | Passed |

## 5. Commands Run

| Command | Result | Evidence / important output |
|---|---|---|
| `uv run python -m unittest discover -s tests -p "test_*.py"` | Passed | 34 tests, `OK`。 |
| `uv run python -m unittest discover -s tests -p "test_reader.py"`；`... "test_state.py"` | Passed | 分别 8、18 tests，均 `OK`。 |
| `uv run python -m compileall -q configs game state dashboard tests` | Passed | exit 0。 |
| `node --check dashboard/static/app.js` | Passed | exit 0。 |
| `python .codex/hooks/check_iteration_names.py` | Passed | exit 0。 |
| `uv run python main.py probe` | Passed | PID 4092；版本 1.0.0.1051、x86、SHA-256 与固定目标身份吻合；raw 植物 50，进度 3/1/0/0/10/10/1/0。 |
| `uv run python main.py snapshot --once` | Passed | `status=ok`、plants=50、scene=3、mode=1、level=0、wave=10/10、paused=True、plants availability=provisional、errors=0。 |
| 只读 Python 同帧 raw→`build_state` 对照 | Passed | 2026-09-24T08:09:45.921Z：50/44/6；State 逐格和 50、ID 集合一致。 |
| `uv run python main.py serve --port 8879`，读取 `/api/state` 和浏览器页面 | Passed | API HTTP 200，`no-store`；相邻样本 `status=ok`、50/44/6，页面 DOM 见下节。验证后已停止该临时服务。 |
| 合成读取失败 State 的临时本地服务 `:8880` | Passed | 浏览器页面 45 格均为读取失败、0 个空格，并显示诊断 `fixture short read`；验证后已停止。合成服务未改生产文件或游戏进程。 |

## 6. Manual / Browser Verification

| Check | Result | Evidence |
|---|---|---|
| 用户本次手工试用及两张页面截图 | Passed as display evidence | 第一张有 50 株、21 僵尸、9 掉落物和完整草坪叠放格；第二张有场景 3、模式 1、生存普通第 1 阶段、暂停是、10/10 波及分层 HP。截图未证明同时刻 raw 或游戏画面。 |
| 当前新服务真实浏览器 DOM | Passed | Codex in-app browser `http://127.0.0.1:8879/` 的 AX 树展示 5×9 网格、6 处叠放格、正常空格、进度原始码/名称/证据标签、路障/铁桶/铁门 HP 分量及合计限定语。 |
| 合成读错浏览器 DOM | Passed | `http://127.0.0.1:8880/`；失败格 45、空格 0，页面显示“采样存在错误”和错误诊断。仅验证 UI 分支，并非声称现场发生真实读取失败。 |
| 只读边界 | Passed | 当前读取/服务调用路径仅查询进程和 `ReadProcessMemory`；未发游戏输入或执行内存写入。 |

## 7. Issues Found

未发现本 Iteration 范围内可复现的实现缺陷或越界变更。当前仓库大量文件尚未 Git 跟踪，不能用 `git diff` 独立重建 002 的精确改动范围；交付阶段须保留其他工作树改动并只提交本 Iteration 相关文件。

## 8. Missing Evidence and Blockers

- 用户新页面截图、独立 raw/State 同帧对照及 API/DOM 是不同采样时刻；植物数量与分布稳定一致，但没有把它们冒充为一个原子帧。当前 R5/R9 的静态数据路径已有同帧 raw→State 及相邻 API/DOM 充分证据。
- 未现场观察自然场景切换、暂停恢复、关卡完成、僵尸装备受伤前后等动态事件，也未取得真实内存读取失败的页面；计划允许这些含义维持 `observed_once`/`provisional`，本次已用固定样本和合成失败页面覆盖相应分支。后续如需把这些字段升级为 gameplay-verified，应由用户自然游玩时另取事件前后证据。
- 001 的遗留 Task/Verify 缺口不属于 002，本结论不改变 001 状态。

## 9. Conclusion

- Overall result: **Passed**
- Reason: R1–R9 与三个已批准 Task 均有代码、固定样本及必要现场/浏览器证据；未知和动态未核验语义仍被如实标注，未发现阻塞性偏差。
- Required next stage: 由用户显式调用 `$sdd-delivery` 时可进入 Delivery；本 Verify 不执行 commit 或 push。
