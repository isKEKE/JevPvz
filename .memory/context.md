# Shared Context

## Current Focus

004 Verify was updated to Passed using the already collected 64-test, browser, and Human-provided State/screenshot evidence; no checks were rerun per the user's request. Delivery report is prepared and the scoped commit/push is in progress.

## Active Iteration

004-game-state-observation — formal Verify record updated to Passed after applying Human scope decisions; all Plans/Tasks are complete. Delivery document prepared; only scoped commit and push remain.

## Open Decisions and Blockers

- The source does not currently provide a fully decoded plantability grid; CD-08 supports the standard daytime 5×9 lawn and maps an explicitly false plantability value to false. Other backgrounds or invalid occupancy return top-level null.
- Non-blocking G2 observations not run: V07 real-browser disconnect, V12 exact 1672×941 viewport, V15 real plant-action capture. Recheck if those scenarios become current acceptance needs.
- G3 deferred: Endless Survival upgrade-price event and live sun-collection threshold; deterministic collector logic tests remain. Other backgrounds/plantability remain unavailable outside the calibrated daytime 5×9 lawn.

## Recent Activity

- 2026-09-26 — verify: 按用户裁定更新 004 Verify 为 Passed；沿用此前 64 tests、浏览器 DOM 和用户配对 State/截图证据，本次未重跑验证。
- 2026-09-26 — direct: 修正卡槽费用/冷却/可选文案并调整 004 验收；主页 DOM 对齐 State，用户配对样本的 13 僵尸/7 植物可见位置匹配。
- 2026-09-26 — plan: 用户批准 P01/CD-08/R17，确定 JEV board cell 三态语义、删除 JEV `terrain`/`plantability`、All State 不变，并规定无效/unsupported 整盘顶层 null。
- 2026-09-26 — direct: 删除 JEV `collectible_suns`，僵尸距离恢复 `distance_to_house_*`，lane 加回最近格距且不含像素最近距离；All State 不变。State/Web 测试 24/12 项通过。
- 2026-09-26 — direct: 按用户要求回填 P05 T1/T2 并标记完成，注明 direct-task 路径；后续 JEV 字段调整使此前 backfill 需重核。
- 2026-09-26 — direct: 完成 P05 JSON 树实现；JEV 无 availability、All 保留；树保留原结构及 per-profile 展开状态，测试与临时浏览器检查通过。
- 2026-09-26 — plan: 用户批准 004/P05，Index 与 P05 Approval 均记为 Approved。
- 2026-09-26 — direct: 修复 cooldown 边界状态；Hard Survival 实时快照 10/10 卡牌 readiness/usability 为布尔。

## Next Action

按 Delivery skill 将仅暂存 004 源码、测试、SDD 与相关 memory，排除其他技能/配置改动及历史证据包，然后提交并推送 `origin/main`。
