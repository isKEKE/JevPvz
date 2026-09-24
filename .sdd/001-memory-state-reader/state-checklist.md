# 001 — State 信息清单与缺口

目标是仓库自带 1.0.0.1051 的草坪关卡观测。用户自行预选卡牌。下表区分**用户/公开资料给出偏移**与**目标程序实机验证**：公开地址只是候选，不等于此 exe 的数据已经可靠。资料来自 [PvZLib 的 1051 地址表](https://github.com/HenryJk/PvZLib/blob/main/include/pvz_reference/1_0_0_1051_en.h)及[重建版 Board](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/Lawn/Board.h)、[SeedPacket](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/Lawn/SeedPacket.h)、[DataArray](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/Sexy.TodLib/DataArray.h)、[Coin](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/Lawn/Coin.h)与[枚举](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/ConstEnums.h)。

## A. 001 先读取的字段

| 数据 | State 字段 | 地址依据 | 当前证据与验收 |
|---|---|---|---|
| 采集来源与时间 | `schema_version`, `observed_at_utc`, `sample_sequence`, `source` | P01 进程身份、P03 构建 | 每轮都有 UTC 时间、序号、进程 ID、程序哈希和 profile ID；不一致时最多重读一次 |
| Board 指针 | 内部采集入口 | `[[module+0x2A9EC0]+0x768]` | 用户测试；只读采样成功，重启后需复核 |
| 阳光余额 | `sun_balance` | `Board+0x5560` | 用户测试；只读现场样本曾读到 100，动态变化尚未核验时为 `provisional` |
| 植物 | `plants[{type_code,row,col}]` | 数组 `Board+0xAC`，数量 `+0xBC`，步长 `0x14C`，字段 `+0x24/+0x1C/+0x28` | 每轮保留对象 ID 与槽位；单帧为 `provisional`，活性和增删需验证 |
| 棋盘占用 | `board.cells[5][9]` | 由活植物列表派生 | 0 基行列；空/占用与植物列表一致；与可种性分开 |
| 僵尸 | `zombies[{type_code,row,x,y,hp}]` | 数组 `Board+0x90`，数量 `+0xA0`，步长 `0x15C`，字段 `+0x24/+0x1C/+0x2C/+0x30/+0xC8` | 原样保留游戏 X/Y/HP；单帧为 `provisional`，尚需出现、移动、受伤、死亡核对 |
| 每行数量 | `lanes[{row,zombie_count}]` | 由活僵尸列表派生 | 五行计数之和等于活僵尸数 |
| 掉落物 | `items[{type_code,x,y}]` | 数组 `Board+0xE4`，数量 `+0xF4`，步长 `0xD8`，字段 `+0x58/+0x24/+0x28` | 保留类型码和坐标候选；类型枚举未核验，不派生阳光列表 |
| 字段可用性 | `valid`, `availability`, `errors`, `missing_fields` | P03 归一化 | 无对象、未映射、读取失败三者明确区分 |

`module` 是运行中主模块基址，不固定为 `0x00400000`。游戏中的 X/Y 保留原值，不等于浏览器像素位置。公开 `DataArray` 结构显示数组头 `+0x4` 是最高已用槽位数、`+0x10` 是活数，条目末尾 ID 的高 16 位用于活槽判断；这与用户 `Board+0xA0/+0xBC/+0xF4` 当前数及曾观测的僵尸 `Board+0x94=10` 相容，但仍需本机核对。不能只遍历 `range(current_count)`。

## B. 公开资料新增的候选字段（001 尝试验证）

| 数据 | 候选内存位置 | 进入 State 的条件 |
|---|---|---|
| 游戏场景/模式 | `Root+0x7FC/+0x7F8` | 菜单、选卡、进行中、结束多场景及枚举核对；分别输出 `game.phase/mode` |
| 暂停/关卡/波次/通关 | `Board+0x164/+0x5550/+0x5564/+0x557C/+0x55FC` | 暂停、恢复、波次推进及完成关卡的事件核对；注意波次可能 0 基 |
| 当前卡槽 | `SeedBank=[Board+0x144]`，槽数 `SeedBank+0x24`，槽数组**内嵌起点** `SeedBank+0x28`，步长 `0x50` | 槽数与游戏 UI 一致；逐槽可读且在选卡变化后同步 |
| 单张卡状态 | `Slot+0x34` 类型、`+0x38` 模仿者、`+0x24/+0x28` 冷却计数/总时长、`+0x48` 活跃标志 | 种植后开始冷却、倒计时与结束核对；未确认 tick 时长前只保留原始计数 |
| 地形与障碍 | `Board+0x168` 起 9×6 地形数组；GridItem 头 `Board+0x11C` | 验证数组行列方向、地形枚举和障碍对象；格子 `terrain` 与 `plantability` 分开 |
| 掉落阳光 | `Item+0x24/+0x28` float 坐标、`+0x58` 类型；普通/小/大阳光类型码候选 `4/5/6` | 逐类出现/收集时现场核对，验证后才派生 `collectible_suns` |
| 活槽 ID | `Zombie+0x158`、`Plant+0x148`、`Item+0xD0` | 与容器活数、出现/删除/槽位复用事件一致 |

以上是 2026-09-24 查到的候选地址。针对固定目标 SHA-256 `F587903E9C3AD3890C1F4E2FBC1FE1EA88BD191E3D623D6F291283F6658C8DD4`，P02 已将一次暂停样本和来源记入 `docs/memory-map.md`：SeedBank 卡槽及 Root/Board `game_progress` 候选字段可读，证据为 `observed_once`；State 将其映射字段标为 `provisional`。这只证明这些候选域在该样本可读，没有证明卡槽活跃/冷却、场景阶段或波次语义的动态变化，未升级为 `verified_with_gameplay`。同一样本读取了 `Board+0x168` 的 54 字节候选地形数据，但未确认元素类型和行列解释，故 `board.terrain` 仍为 `null` + `unavailable`，`plantability` 仍为 `unknown`。只有公开地址、无法确认读值或语义的其他字段也继续保持缺失/候选，不因本表列出地址而显示为可信。

## C. 仍需补齐，才适合让 JEV 玩这一关

| 缺口 | 为什么需要 | 001 处理方式 |
|---|---|---|
| 当前游戏阶段、真实关卡号 | 菜单、暂停、结束态不能继续决策；截图“1-3”不能当运行时事实 | P02 已在固定目标的一帧读取 scene/mode/background/level/wave 候选；当前 State 可映射显示且标 `provisional`。没有跨场景、恢复暂停或波次变化事件，语义未验证；不得把候选标签或旧截图当成可信当前阶段/关卡。 |
| 玩家选中的卡牌、槽位与冷却/可用状态 | 决策动作只能在当前卡组选择，避免冷却中的无效动作 | P02 已读到 10 个 SeedBank 候选槽和逐槽类型/模仿者/冷却原始计数/可用标志候选；State 标 `cards`/`cards.cooldown` 为 `provisional`。未观察选卡、种植后冷却起止或可用性变化，原始 tick 单位及标志语义仍待验证。 |
| 当前卡牌真实费用 | 决定阳光是否足够；升级植物等场景的费用可能动态变化 | 当前实现按已知植物类型从 1.0.0.1051 静态目录提供 `cost`，并标 `cost_source=static_catalog`、`availability["cards.cost"]="provisional"`；未知类型仍为 `null`。这不是游戏内实时费用读数，模式/升级费用及事件前后变化仍未核验。 |
| 具体格子能否放指定植物 | 有植物、地形、墓碑、坑洞、植物叠层及卡牌规则均可能影响 | P02 曾读取地形候选原始字节，但未解码；当前 `board.terrain` 为 `null` + `unavailable`，格子 `plantability` 为 `unknown`。没有种植/阻挡事件验证，不能推断“不可种”。 |
| 掉落物类型枚举中“阳光”的值 | 才能从 `items` 可靠派生 `collectible_suns` | P02 一帧保留了候选类型码与坐标；当前 State 可给目录候选名，但类型语义未通过出现/收集事件核验，`collectible_suns` 仍为 `null`。 |
| 活对象槽位上限、活性标志与 ID | 避免漏读或读到已删除对象 | P02 已按稀疏数组高水位和候选 ID 规则扫描；一帧中植物/僵尸/掉落物报告数与扫描数相符。该规则仍为 `observed_once`/`provisional`，未用删除、槽位复用事件验证。 |

用户确认 001 可以先留下未验证字段。P02 已缩小可读候选字段的地址缺口，但事件语义缺口仍在：阶段/关卡、卡槽冷却、费用变化、地形/可种性、掉落物阳光类型、对象删除/复用等均没有对应动态证据，不能把这些域标为 `available`。完整的 JEV 决策输入至少需要可信游戏阶段/关卡、阳光、活植物/格子、活僵尸/行威胁、卡牌可用性与费用；掉落阳光可交给后续自动收集器处理。

## D. 建议增强与执行层信息

| 信息 | 用途与归属 |
|---|---|
| 僵尸护具 HP、波次/进度、植物叠层 | 当前代码树由 002 加入僵尸护具 HP 分项/总量、进度字段映射和叠层表示；这些读取/显示仍是 `observed_once`/`provisional`，没有受伤、护具消耗或自然波次变化的动态证据。001 的僵尸本体 HP 候选偏移为 `+0xC8`。植物自身 HP 与小推车状态仍属后续增强。 |
| 窗口客户区、缩放比例、格子点击中心、卡牌与阳光点击位置 | 后续 Action Executor；不作为 JEV 的屏幕像素决策输出 |
| 动作执行后的回读确认 | 后续执行层和本 State Reader 的闭环 |

JEV 最终应选择语义动作，例如“某卡牌放到第 2 行第 4 列”；屏幕坐标由执行层换算。P04 可将经现场校准的游戏 X 投影到棋盘覆盖层，但它不是点击坐标，也不把视觉插值当成新采样。

## 验证分工与现场证据

- **第一部分，暂停进程的一次采样**：用户已提供 [暂停前截图](evidence/001-game-before-pause.png) 和 [暂停截图](evidence/002-game-paused.png)，显示五行草坪、阳光 3333、关卡 1-3 与右侧一只僵尸。截图是拍摄时的场景参照；正式验证须重新读取仍运行的目标进程，记录采样时间、PID、程序身份、原始内存值、State、`GET /api/state` 和页面显示，再与**当时**游戏画面比对。暂停菜单遮挡处不据旧图断定植物、格子或掉落物。单帧可确认存在和值，不能独自确认移动、冷却倒计时或死亡事件。
- **第二部分，用户亲自玩一关**：页面和采样器保持只读，用户自行恢复/操作游戏并决定观察结果。记录自然发生的阳光、卡牌、植物、僵尸、掉落物、波次/阶段变化以及断开/重连；每项与原始读数和 State 对照。未发生或未由用户确认的事件维持候选/缺失状态，不以静态画面推断动态通过。
- 当前进程若在实施或正式 Verify 前退出，归档图片不能替代内存证据；第一部分须等待用户再次提供暂停且有僵尸的现场。整体 Verify 在两部分强制证据与用户判断未齐时不能标记 `Passed`。

## E. 快照形状与状态语义

以下只示意字段组织，数值不是实测。`availability` 的状态以实际验证结果为准；示例中的植物/僵尸等若只完成一次现场对照，应改为 `provisional`。卡牌费用和种植规则未齐时 `decision_ready` 仍为 `false`。僵尸 HP 示例是原始值，没有最大 HP 就不派生百分比。

```json
{
  "schema_version": 1,
  "observed_at_utc": "2026-09-23T15:00:00Z",
  "source": { "pid": 1234, "profile": "pvz-1.0.0.1051", "exe_sha256": "..." },
  "valid": true,
  "decision_ready": false,
  "availability": {
    "sun_balance": "available",
    "plants": "available",
    "zombies": "available",
    "items": "available",
    "game.phase": "unavailable",
    "game.level": "unavailable",
    "cards": "unavailable",
    "board.terrain": "unavailable",
    "board.plantability": "unavailable"
  },
  "errors": [],
  "missing_fields": ["game.phase", "game.level", "cards", "board.terrain", "board.plantability"],
  "game": { "mode": null, "phase": null, "paused": null, "level": null, "wave": null },
  "sun_balance": 125,
  "board": {
    "rows": 5,
    "cols": 9,
    "terrain": null,
    "plantability": null,
    "cells": [
      [null, null, null, "plant:1", null, null, null, null, null],
      [null, null, null, null, null, null, null, null, null],
      [null, null, null, null, null, null, null, null, null],
      [null, null, null, null, null, null, null, null, null],
      [null, null, null, null, null, null, null, null, null]
    ]
  },
  "plants": [{ "type_code": 1, "row": 0, "col": 3 }],
  "zombies": [{ "type_code": 0, "row": 2, "x": 650.0, "y": 330.0, "hp": 180 }],
  "lanes": [
    { "row": 0, "zombie_count": 0 },
    { "row": 1, "zombie_count": 0 },
    { "row": 2, "zombie_count": 1 },
    { "row": 3, "zombie_count": 0 },
    { "row": 4, "zombie_count": 0 }
  ],
  "items": [],
  "cards": null,
  "collectible_suns": null
}
```

成功读取且无对象是 `[]`，并保留该域证据等级；一次现场对照成功的读数是值 + `provisional`；尚无地址或候选无法确认是 `null` + `unavailable`；读取失败是 `null` + `error`。页面须按这些状态分别显示“当前没有”“待动态核验”“未获取”和错误原因。格子占用、地形与可种性独立表达，僵尸不占用植物格；同一列可有多只僵尸。

## F. P03/P04 当前实现字段状态与证据边界

- P03 的 `availability` 使用扁平字段路径，状态只取 `available`、`provisional`、`unavailable`、`error`。本次可读字段有单帧/候选偏移证据时标为 `provisional`；成功但无对象用 `[]`，未映射或语义未确认用 `null` + `unavailable`，读取错误用 `null` + `error`。事件前后语义未核验的字段不升为 `available`。
- `board.cells` 固定为 5×9；空格为 `null`。占用格保留主植物、`plants` 列表、`plant_count`、类型码、0 基行列和对象标识，因此同格叠层不会抹掉其他植物。当前工作树的叠层支持来自后续 002 实现，不能据此宣称 001 已通过叠层动态事件验证。每格的 `plantability` 单独为 `unknown`，不从占用推断不可种；`board.terrain` 当前为 `null` + `unavailable`。
- `lanes` 固定五行，按僵尸列表派生每行数量，并保留每只僵尸的行、原始 X/Y 和本体 HP。当前 State 还可能列出头盔/路障等护具 HP 与 `total_hp`；这属于后续 002 的 HP 扩展，不证明 001 已动态核对受伤/护具消耗。没有已验证的最大 HP 时不输出百分比。
- `cards` 可保留候选槽位、类型码、模仿者码和冷却原始计数；冷却单位仍未知，不换算秒数。已知类型的静态目录费用以 `cost_source=static_catalog` 提供，`cards.cost` 标为 `provisional`，不是进程内读取的动态费用；缺少目录值时不伪造费用。事件、模式或升级造成的费用变化仍未核验。
- 当前实现会将可读候选码映射为场景/阶段、模式、背景、关卡和波次等显示值；对应 `game.*` 可用性仍为 `provisional`，原始候选值保留在诊断字段中。当前代码树包含后续 002 对进度字段的映射；尚无跨场景或自然波次变化记录，故这些标签不代表 001 已验证其语义。掉落物保留类型候选名和 X/Y，`items.type` 仍为 `provisional`，没有确认阳光枚举，`collectible_suns` 仍为 `null`。
- P04 已提供只读本机页面、共享 State 轮询、原始 JSON 和各字段状态显示。费用来源能标为静态目录；未校准僵尸 X 投影时显示“位置未校准”，不画推断位置，侧栏保留行及原始 X/Y/HP。
- 直接可追溯的暂停样本包括 raw→State 一致性记录、邻近 API 响应和既有页面检查；本次复采样也与两个现存 API 端点在阳光与对象计数上相符。这些记录不是同刻游戏画面 + raw + State + API + 页面的一次性联证。用户报告亲自测试页面且未发现问题，但没有按事件保存阳光、种植、僵尸、掉落物或进度变化的时间关联证据；这些动态语义继续待 Verify 核验。
