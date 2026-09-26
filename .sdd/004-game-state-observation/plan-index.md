# Plan Index

## 1. Metadata

- Iteration: `004-game-state-observation`
- Created at: 2026-09-25
- Status: Approved
- Owner: 本仓库维护者

## 2. Goal

把现有只读 State 的字段、可信度和决策用途梳理成可审阅的契约；在确认语义的前提下补齐对下一步 JEV 决策有用的确定性信息；提供独立的 State 观察页、重整草坪状态 Dashboard，并提供由维护者显式调用的实机验证证据采集工具。本次不接入 JEV 或执行产品侧自动决策。P05 补充收敛 JEV 输入字段并改善 State JSON 页面可读性。

### Requirement Baseline

| Requirement ID | Requirement | Source | Verification tier | Reason for tier |
|---|---|---|---|---|
| R1 | 梳理当前 State 的实际字段、来源、证据级别、缺口和面向完整关卡的稳定契约；区分原始事实、确定性派生与尚不可断言的战术/预测。 | 用户本次“plan-01 先把 state 的内容理清楚”；引用对话中 State v1 讨论；当前 `state/builder.py`。 | G1 | 决定 004 对外描述是否可信，也是后续页面和 JEV 的数据基础。 |
| R2 | 程序在受支持的标准模式中计算当局 `cards[].cost` 与 bool 型 `cooldown_ready`，并核验冷却/卡牌可选语义；保留 `sun_balance`，不新增 `affordable*`。证据不足时标不可用，不把未算出的门槛交给 JEV 猜测。无尽模式升级加价不属于当前 004 验收范围，仍按未核验值处理。 | 用户 2026-09-25 对 OD-01 的 Option A 选择与卡牌字段修订；用户 2026-09-26 明确暂不要求无尽模式升级费用变化。 | G1 | 当前受支持模式的费用、冷却和可选状态直接供 State/JEV 使用；无尽模式加价明确延后。 |
| R3 | 增加一个独立前端页面，动态显示同一 `/api/state` 的完整 State，便于观察采样更新、断连、错误及字段证据；从草坪状态页 `/` 与 State 观察页 `/state` 在同一浏览器标签页双向切换。 | 用户本次“plan-02 前端页面需要一个 page 页面单独动态显示获取 state 来观察”；用户 2026-09-25 确认与草坪状态页同一 tab 切换。 | G1 | 独立观察页面和在当前监视器标签页内切换共同构成可达、可用的观察入口。 |
| R4 | 重设草坪状态页：移除常驻“字段状态”大面板，压缩卡槽，理顺草坪与僵尸详情，保留有用的 State 观察能力。使用文字为主，不添加植物光栅图片；1672×941 下的无滚动检查作为 G2 版面风险。 | 用户在引用对话中要求删除“字段状态”、重整卡槽及草坪/僵尸详情、让主要信息尽量一屏展示、移除植物图片并以文字为主；用户 2026-09-26 接受当前设计，不再要求定量打分。 | G1 | 信息准确、入口可读和不丢失 State 事实是核心；精确视口布局按本次 Human 裁定降为非阻塞风险。 |
| R5 | 连续样本的僵尸速度、到屋 ETA、威胁分数、全规则可种格及任意场景的 `available_actions`。 | 引用对话的后续候选；当前 `board.plantability` 为 unknown，冷却单位未验证。 | G3 | 这些需要时间序列、校准或完整规则，当前“梳理 State + 观察页面”的目标无需强制交付；未来决策闭环计划启动前重查。 |
| R6 | 现有 Dashboard 与新观察页在普通刷新、异常、断连情况下不泄漏旧样本或互相增加采样负载。 | 当前 `dashboard/server.py::StatePoller` 为单采样器，`dashboard/static/app.js` 周期请求。 | G2 | 属当前页面改动带来的风险；若状态错显影响 R3 的观察可信度，升级为 G1。 |
| R7 | 面向 JEV 的 State JSON 使用英文键、稳定英文标识和值；Web UI 按英文标识本地化植物和僵尸名称为中文，未知类型保留数值码与 `unknown`，不凭译名补含义。 | 用户 2026-09-25 明确要求“web ui 僵尸+植物显示中文”；本 Iteration 已记录 State 英文契约。 | G1 | JSON 语言契约及人工页面上的植物/僵尸中文名称均影响 State 的可读性和消费者兼容。 |
| R8 | 僵尸 HP 明确分为本体、头盔、盾牌、气球；旧 `hp` 仅为本体别名，`total_hp` 只作已读取分量之和，不代表单一可伤害血条，缺任一分量时为 null。 | 用户 2026-09-25 的 HP 说明；002/P02 的实现与 Verify；003 复用 State。 | G1 | 只报告本体会低估带装备僵尸；误读合计也会误导 JEV。 |
| R9 | 在固定目标标准日间草坪，用同场景截图/State 校准房屋触线 `house_x=0`、X 方向及 80px 格距/首格边界 X=50；输出每只僵尸 `distance_to_house_px`、0–8 整数 `distance_to_house_cells` 和每行最近值。删除 `progress_to_house`；其他背景/模式保持 unavailable。 | 用户 2026-09-25 对 P01/OD-02 的选择，经用户 2026-09-26 校准修订；同帧样本行 0 的 X 为 10/90/170/250/330/410/490/570/650。 | G1 | 像素距离和格子距离直接给出僵尸接近房屋的距离；错误触线或格列会误导观察和决策。 |
| R10 | 以同一场景的 State 与游戏截图核对可见植物、僵尸类型/行列和植物占用位置；不要求 Verify 阶段实际发送种植输入。 | 用户 2026-09-25 的 004 要求；用户 2026-09-26 提供配对 State/截图并认为匹配。 | G1 | 同帧可见事实对照直接检验 State 的位置/类型可信度；动作采集脚本另按 G2 评估。 |
| R11 | 实机阳光收集的 10 秒与增量 >50 成功阈值不作为本次交付验收；采集脚本仍保留有界逻辑和确定性测试。 | 用户 2026-09-26 明确删除 V16 阳光收集阈值实测。 | G3 | 用户暂不需要实机收集结果；若未来要求证明收集效果，再恢复验证。 |
| R12 | 使用同一场景的 State 与游戏截图核对可见且稳定的字段；items 因自然生成/消失而忽略。 | 用户 2026-09-25 的 004 要求；用户 2026-09-26 提供配对 State/截图并确认其可用于核对。 | G1 | 同场景 State/截图交叉检查 State 事实可信度，且不把动态掉落物误判为差异。 |
| R13 | 当前 Dashboard 视觉设计由用户直接认可；不再要求归档参考图或给出相似度分数。 | 用户 2026-09-26 明确表示设计已认可并删除 V18。 | G1 | 当前设计以 Human 明确批准为验收；后续重做页面时再定义视觉量表。 |
| R14 | 使用同一 State 样本中的僵尸行号和 `distance_to_house_cells`，在草坪对应行吸附到 0–8 列标记近似格位；这只是位置区间，不表示僵尸占据植物格。缺失/无效值时保留逐行详情且不猜画。 | 用户 2026-09-25 原选连续标记，后于 2026-09-26 明确改为像素距离加格子距离并删除 `progress_to_house`。 | G1 | 用户现在要按可读格位观察僵尸；边界映射或行列错误会误导人工。 |
| R15 | 将 State 分成 JEV State 与 All State：JEV State 按 001 初始模拟字段/决策清单建立显式精简字段集，不输出顶层 `availability`；未获取值继续使用 `null`。All State 保持完整诊断契约（含 `availability`），但按 R9 删除已废弃的 `progress_to_house` 并加入 `distance_to_house_cells`。两个 profile 复用同一采样。P05 对此前 P01/R15 的 availability 呈现作当前修订。 | 用户 2026-09-25 明确要求分类；2026-09-26 批准 R9 字段修订，并明确要求移除 JEV State 的 `availability`。 | G1 | JEV 输入不应携带用户认为不适合模型的字段级诊断；All State 仍需保留人工排错和核验路径。 |
| R16 | `/state` 以可读的 JSON 树展示当前选中 profile，同时保留原字段名、顺序、嵌套和值；对象/数组可展开折叠，值类型有语法颜色，轮询刷新时保持仍存在路径的展开状态，复制仍对应原 JSON 数据。 | 用户 2026-09-26 要求保留原始结构、增加截图示例风格。 | G1 | 独立 State 页必须保留可检查的原契约，同时 500ms 轮询不能持续打断人工浏览；结构转换或复制错 profile 会改变数据含义。 |
| R17 | JEV State `board.cells[row][col]`：null 表示空且可种，false 表示不可种，`plant:<type_name>` 表示占用；JEV board 不输出 `terrain`、`plantability`，All State 保持原结构。标准日间 5×9 草坪适用；occupancy 无效或不支持布局时整个 `cells` 为 null。 | 用户 2026-09-26 在 P01 中定义 cell 语义、要求删除两个字段并批准 Plan。 | G1 | 格子状态直接影响后续 JEV 决策；未知/不支持时须保持顶层 null，避免把未知单格误报为可种。 |

## 3. Scope

### In scope

- P01：盘点 State、记录字段契约，在固定目标实机核对当局费用与 bool 型冷却就绪，并由程序计算这些确定性结果；在已校准标准日间草坪计算像素距离、整数格子距离和行最近距离，不再输出 `progress_to_house`。新增基于 001 初始模拟字段组的 JEV State 显式投影，保留 All State 其余字段与默认消费者兼容。
- P01 将本次模拟快照、逐字段含义、已有/新增/暂缓状态及获取方法写入 Plan；将 State 语义字符串统一为英文，网页单独翻译为中文；保留僵尸分层 HP 语义。
- P01/T5：按 CD-08 将 JEV board `cells` 编码为空且可种、明确不可种、按英文 type_name 标注占用；移除 JEV board 上独立的 `terrain`/`plantability`，不改 All State。
- P02：独立页面读取共享采样，动态展示 JEV State / All State 并提供视图切换，默认 JEV State；草坪状态页 `/` 与 State 观察页 `/state` 通过普通页面链接在同一浏览器标签页双向切换；沿用本地只读 HTTP 服务。
- P03：重排 `/` 草坪状态 Dashboard；移除常驻字段状态面板、压缩卡槽、关联草坪行与僵尸威胁、保留结构化/JSON 只读观察；P01 格子距离可用时按 0–8 列标记近似格位，不表示植物格占用；1672×941、100% 缩放下的无滚动表现是 G2 优先目标。
- P04：增加显式调用的实机 State/截图证据采集脚本，覆盖有界种植、可选阳光收集及当前态 State/画面对照；同场景用户 State/截图用于当前验收，实时阳光阈值结果为 G3 暂缓。脚本不调用 LLM API。
- P05：修订 JEV State profile，不输出 `availability` 但保留 All State 诊断；将 `/state` JSON 文本展示为保留原结构的可折叠、语法着色树。
- P03 当前 Dashboard 已获 Human 认可，不再要求 CD-03 参考图或 OD-03 95 分计分；精确桌面视口只作为 G2 版面风险。
- 仅使用当前 Python 依赖、标准库和原生 HTML/CSS/JavaScript；不新增依赖。

### Out of scope

- JEV API、DecisionState 压缩、策略/Policy、产品侧自动动作循环、无人值守游玩和单僵尸或完整关卡通关。P04 仅包含用户显式启动的有界验证采集脚本。
- 输出冗余 `affordable`/`affordable_by_catalog`；未核准冷却 tick 单位时给出“剩余秒数”或把未知就绪状态写成 false；未校准房屋/出生坐标时给出精确进度或 ETA；推导所有背景/植物组合的通用可种规则。CD-08 仅定义标准日间 5×9 草坪编码；unsupported 或整盘未知时 `board.cells=null`。
- 超出 P03 已列目标的产品视觉重做、支持其他 PvZ 版本或新增 HTTP 写接口；除本次明确删除 `progress_to_house` 并增加格子距离外，修改其他 All State schema/语义、增加第二个采样器或改变 P02 `/state` 页面导航；未校准时推测僵尸位置或将格位区间解释为植物格占用。

## 4. Plan Catalog

| Plan ID | Plan | Main outcome | Depends on | Status | Link |
|---|---|---|---|---|---|
| P01 | State 契约、双 profile 与安全派生 | 英文 State、中文 UI、JEV/All 字段分类、分层 HP、费用/冷却、像素/格子距离及 JEV board cell 语义 | 001～003 当前实现 | Approved | `plans/01-state-contract.md` |
| P02 | 独立动态 State 页与 profile 切换 | 可直接打开并切换观察 JEV State / All State，复用同一快照 | P01 确定的 State/profile 契约；复用现有采样器 | Approved | `plans/02-live-state-page.md` |
| P03 | 草坪状态页结构与密度重设 | 单屏优先的主页、紧凑卡槽、按已校准 State 标记僵尸所在格列、结构化/JSON 观察 | P01 字段/位置语义；P02 页面边界 | Approved | `plans/03-dashboard-reduction.md` |
| P04 | 实机 State 与画面交叉验证 | 用脚本采集可复核的 State/截图/动作证据，LLM 只负责多模态判读 | P01 State 契约；003 已交付的动作执行器；最终完成态检查在 P02/P03 后执行 | Approved | `plans/04-live-state-validation.md` |
| P05 | JEV 字段边界与 State JSON 树形展示 | JEV profile 移除 `availability`；State 页面以保留 JSON 结构的样式化树展示所选 profile | P01/T4 JEV 投影；P02/T3 State profile 页面 | Approved | `plans/05-jev-state-presentation.md` |

## 5. Decision

- Open Decision：无。
- Confirmed Decision：2026-09-25 用户明确指定 004 为 P01 State、P02 独立动态页面、P03 现有页面重整；要求 State 值英文、Web UI 植物/僵尸中文、分层 HP、模拟样本/字段表、无 affordable*。用户确认 P01/OD-01 Option A（程序计算确定性 State，暂不冻结额外 state_version=1.0）与 P01/OD-02 Option A（先校准后输出距离）；另确认 / 与 /state 在同一浏览器标签页互相切换。P03/CD-03 的版式边界和处理方式见 P03；用户于 2026-09-25 批准 CD-04 连续标记。2026-09-26 用户把位置输出改为 `distance_to_house_px` + 整数 `distance_to_house_cells`，删除 `progress_to_house`，并批准按已校准格距在对应列标记；同场景样本给出 house_x=0、首格边界 X=50、列距80。用户同时要求把 JEV State / All State 分类并入 004，保持除该明确位置字段替换外的 All State 兼容。用户于 2026-09-26 又确认 CD-06：JEV 不输出 `availability`、All State 保留；CD-07：State 页保留原 JSON 结构并参考所附 JSON 树样式；CD-08/R17：JEV board cells 使用 null/false/plant type_name，删除 board terrain/plantability 字段，All State 保持原样。用户本次又明确：Endless surcharge 与阳光实机阈值不纳入当前 G1，Dashboard 由用户直接认可，V12/V15 降为 G2，并以配对 State/截图核对可见字段。

## 6. Task

- P01/T1 梳理并记录当前 State、模拟样本与字段证据；P01/T2 实现英文机器值、中文 UI 映射、分层 HP、标准模式当局费用/冷却的程序计算（无尽升级加价暂缓）；P01/T3 按 house_x、首格边界和 80px 列距输出像素/格子距离与行最近值并移除 progress 字段；P01/T4 定义 JEV State allowlist 并提供同样本投影、显式 CLI/API profile；P01/T5 按 CD-08 更新 JEV board cell 编码和投影测试，All State 保持兼容。
- P02/T1 新增独立页面及共享状态接口路由、同一浏览器标签页双向导航；P02/T2 验证当前标签页切换、动态刷新、断连和错误展示；P02/T3 增加默认 JEV State、可切换的 All State 视图。
- P03/T1 重排草坪状态页为状态栏、紧凑卡槽、草坪及次级观察区；P03/T2 回归 State 单一来源、结构化/JSON 切换、中文名称、P02 导航和当前认可设计；P03/T3 用校准的 row/grid-distance State 将僵尸标记吸附到对应列，并在数据不可用时隐藏标记、保留逐行详情。
- P04/T1 建立单次种植、限时收集阳光及完成态 State/游戏截图采集脚本；P04/T2 覆盖脚本边界测试并记录运行及 LLM 多模态判读方式。
- P05/T1 从 JEV projection 中移除 availability、保留 All State 并同步契约文档；P05/T2 为 `/state` 增加安全的 JSON 树渲染、语法样式与 profile/错误/复制回归。

## 7. Validation

### Current delivery boundary

- 本次产物与实际用途：为人工和后续 JEV 设计者提供可信的 State 契约、独立实时观察页、精简主页和可复核的实机 State/截图交叉验证工具。
- 本次交付成功的最小条件：P01 模拟样本/字段/证据表与实现一致；State 语义值英文、Web UI 植物/僵尸中文、分层 HP 准确；标准受支持模式费用和 bool 冷却由程序计算并经游戏/State 对照；无尽升级费用暂缓；日间草坪像素/格距与行最近值符合用户同场景校准；JEV State allowlist 和 All State 兼容、双 profile 同采样；P02 实时页面能切换并在错误时清旧样本；P05 State 页按原 JSON 结构展示；P03 当前设计已由用户认可、僵尸格列映射正确；同场景 State/游戏截图可见事实一致。精确视口和实机种植动作为 G2；阳光实机阈值为 G3。
- P01/R17 的验收补充：JEV 标准日间 board cell 为 null/false/`plant:<type_name>` 三态，独立 `terrain`/`plantability` 键消失；整盘读取或布局不支持时 cells 顶层为 null，All State 不变。
- 不作为本次交付门槛的场景：JEV 决策与自动通关、速度和 ETA、完整可种植规则、其他版本和布局、未达到明确运行前提的阳光掉落物场景（此时记录 inconclusive 并在受控场景重试）。

### Verification tiers

| Tier | Meaning | Handling in Verify |
|---|---|---|
| G1 核心路径 | State 可信契约、英文机器值/中文 UI、分层 HP、标准模式费用/冷却、校准距离、JEV/All 隔离、独立动态页、原结构 JSON 树、主页信息与格列标记、用户提供的 State/画面可见事实核对 | 用固定样本、配对 State/截图、API/浏览器和测试证据验证；未通过会影响交付。 |
| G2 当前风险 | 共享采样器异常观察、精确目标视口、实机种植动作采集 | 记录实际结果和剩余风险；明确降为 G2 的项目不作为当前交付阻塞。 |
| G3 后续场景 | 时间序列、策略、全规则可种性、无尽升级加价、阳光实机阈值 | 本次暂缓；相关功能保留 fail-closed 或仅保留确定性脚本测试，未来需要时重查。 |

R10、R12、R14、R17 为 G1；R11 已降为 G3，R13 由用户直接认可当前设计。R10/R12 仅比较用户配对图像中可观察的 State 字段；R12 明确排除 items。V15 实机种植动作属 G2；阳光阈值实测不再属于当前计划。R14/V19 用固定样本验证格距到列索引的映射、边界和无效值回退；R17/V30 用固定样本核对逐格 null/false/plant-name 语义、字段删除、未知棋盘回退和 All State 兼容。

验证顺序：先 P01 的静态样本、profile allowlist/兼容对照与必要实机语义/坐标核对；P05 在 P01/T4、P02/T3 后核对 JEV 字段隔离、JSON 树和复制，再 P04 实机采集及多模态核对，随后 P02/P03 浏览器切换、V19 格列标记及设计图验收。P03/V19 的实机定位只在 P01/V11 校准可用后核对；P04 的完成态截图在 P01–P03 和 P05 对相关页面的改动之后采集。具体检查 ID、命令、证据和升级条件见各 Plan。

## 8. Risks

- 现有卡槽冷却与可用标志只有单帧候选证据，003 的实机游戏还被人为去除了冷却；P01 的正常冷却动态核验是当前 G1 门槛，不能复用 003 的无冷却结果。
- 地址表给出 `PlantDefinition` 基础费用候选：类型 `t` 的模块相对 `0x29F2B0 + t×0x24 + 0x10`。已只读核对仓库固定 PE 文件中类型 0/1/41 分别为 100/50/150；这不是每张卡“当局最终价”的字段。公开反编译实现显示无尽生存的升级植物当局价格按场上同类植物数每株加 50；SeedPacket 结构未见独立最终费用字段。运行中读取及动态加价仍须实机核验。
- 白天标准草坪的 house_x=0、首格边界 X=50 和 80px 列距已由用户同场景截图/State 样本确认；格位采用零基 0–8。其他背景/版式无校准配置时须 unavailable。
- `board.plantability` 为 unknown，掉落物类型为 candidate；不能从占用或类型名直接推导通用合法动作。
- CD-08/R17 只约定 JEV 标准日间 5×9 board cell 表达；其他布局或整盘状态未知时整个 `cells` 为 null，不代表这些布局的种植规则已验证。
- 当前 `type_name` 与 `game.scene/mode/background` 输出中文，且页面直接展示这些值；实施时必须同时更新目录映射、State 测试及 Web UI 翻译，避免只改一侧。
- P03 以 1672×941 内容视口作为单屏基线；较小屏幕可响应式折行或滚动，不误认为核心目标失败。
- P03 格列标记使用 P01 的 `distance_to_house_cells`；仅在该字段可用且为 0–8 整数时绘制，不表示僵尸占据植物格。未校准模式隐藏标记并继续显示逐行详情。
- 原 CD-03 设计参考图/评分门槛已由用户 2026-09-26 明确取消；当前视觉设计以 Human 批准为准，不再是未决交付风险。
- items 类型/位置仍可能是候选证据，ActionExecutor 会拒绝不明确的坐标；10 秒内没有足够可定位阳光或期间存在其他阳光来源时，R11 结果是 inconclusive，不能用环境不足假装通过。
- JEV State 是新增的精简契约，必须按 allowlist 显式投影并保留 unknown/unavailable；不能把候选值升级或让 All State 的未来字段自动泄漏进 JEV State。
- JEV 不输出 availability 后，JEV 消费者不能区分不同 null 原因；All State 仍保留 field diagnostics。JSON 树只改变展示方式，严禁把 State 文本按 HTML 注入。
- 现有工作区有未提交的 SDD 技能及配置改动；004 只触及自身 Plan 和必要 memory，保留其他改动。

## 9. Approval

- Status: Approved
- Approved by: User
- Approval date: 2026-09-26
- Notes: 用户于 2026-09-26 明确批准 P05 与 P01/CD-08 修订。R17 cell value 语义和 JEV board 字段删除按本次批准生效；本次又将无尽加价与阳光收集实机阈值移出当前验收、将精确视口检查降为 G2，并接受当前 Dashboard 设计和同场景 State/截图作为验收证据；All State board 不变。
