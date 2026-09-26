# Delivery

## 1. Delivery Metadata

- Iteration: `004-game-state-observation`
- Delivered at: 2026-09-26
- Branch: `main`
- Commit type: `feat`
- Planned commit subject: `sdd(004): feat game state observation`
- Primary commit: `8cdc3b821544c2b76fa3a0309c9ac62e1c800306`
- Push: `origin/main` succeeded.

## 2. Summary

交付 004 的 State 契约与双 profile、实时 State 页面、草坪 Dashboard、受限证据采集工具及经用户裁定后的验收范围。标准 Hard Survival 卡槽费用、冷却和可选状态由 State/UI 一致呈现；P01–P05 Task 均已完成。

## 3. What Changed

- 将 State 规范为英文机器字段，并保留 All State 诊断契约；增加显式 JEV allowlist 和 `/api/jev-state`，两个 profile 共享采样器。
- JEV board 按标准日间 5×9 格输出 `null`、`false` 和 `plant:<type_name>`；All State 保留完整 board 诊断。
- 增加 `/state` JEV/All State 页面、可折叠 JSON 树和同标签页导航；重整草坪 Dashboard，并按校准格距显示僵尸所在列。
- Dashboard 卡槽按 State 的 availability 显示费用状态，直接显示 `cooldown_ready` 和 `usable`，不再把已知值标成候选或展示原始计数作为冷却结论。
- 增加本机实机证据采集工具和确定性边界测试。
- 保留用户指定的 P05 JEV 字段边界/JSON 树改动；保留 `.sdd/005` 取消记录。

## 4. Plan and Task Status

| Plan ID | Status | Completed Tasks | Incomplete Tasks | Notes |
|---|---|---|---|---|
| P01 | Approved | T1–T5 | None | 标准模式费用/冷却与格距完成；Endless surcharge 按 Human 决定 deferred。 |
| P02 | Approved | T1–T3 | None | 断连实机观察保留为 G2。 |
| P03 | Approved | T1–T3 | None | 当前设计获用户接受；精确目标视口保留为 G2。 |
| P04 | Approved | T1–T2 | None | V15 实机种植为 G2；阳光实机阈值为 G3 deferred。 |
| P05 | Approved | T1–T2 | None | JEV 不输出 availability；State 页面保留 JSON 结构树。 |

## 5. Files Changed

- State/runtime: `configs/item_catalog.py`, `configs/plant_catalog.py`, `configs/pvz_1051.py`, `configs/zombie_catalog.py`, `game/reader.py`, `main.py`, `state/builder.py`, `state/projection.py`, `dashboard/server.py`。
- UI: `dashboard/static/app.js`, `dashboard/static/index.html`, `dashboard/static/style.css`, `dashboard/static/state.html`, `dashboard/static/state-page.js`。
- Tests and usage: `tests/test_reader.py`, `tests/test_state.py`, `tests/test_web.py`, `tests/capture_live_validation.py`, `tests/test_live_validation.py`, `README.md`。
- Docs and SDD: `docs/architecture.md`, `docs/memory-map.md`, `.sdd/004-game-state-observation/plan-index.md`, `plans/01-state-contract.md`–`plans/05-jev-state-presentation.md`, `verify.md`, `delivery.md`, `.sdd/005-jev-state-projection/plan-index.md` (cancelled-number record), `.memory/context.md`, `.memory/project-map.md`。

## 6. Verification Result

- Overall result: Passed
- Evidence: `verify.md`.
- Evidence basis: the completed verification run and post-fix direct-task results already recorded for this Iteration, plus the user's paired State/screenshot and explicit scope decisions. This delivery update did not rerun tests or live checks.
- Latest recorded automated results: 64/64 full-suite tests and 13/13 `test_web.py`; JS/Python syntax and `git diff --check` passed.

## 7. Deviations from Approved Plan

- 用户决定不把 Endless Survival 升级加价事件列为本次 G1 验收；对应场景继续输出 provisional/unavailable。
- 用户删除 V16 阳光实机阈值检查；R11 调整为 G3，确定性采集逻辑测试保留。
- 用户接受当前 Dashboard 设计并删除 V18/R13 定量评分；V12 精确视口和 V15 实机种植动作降为 G2。
- 用户提供同场景 State/游戏截图用于 V10/V17 可见字段对照；截图不可见的 HP 数值由 raw→State 自动化测试核对，不从像素推断。

## 8. Known Risks

- G2 尚未执行：V07 真实浏览器断连、V12 精确 1672×941 视口、V15 实机种植动作、V29 大型 All State 树渲染性能；用户已接受这些项目不阻塞本次交付。
- G3 暂缓：Endless upgrade price event、实机 sun collection threshold 和 V04 预测/策略字段。
- 非日间标准布局的 plantability/distance 仍保持 unavailable；不推导通用种植合法性。

## 9. Follow-up Items

无当前交付阻塞项。只有在用户要求 Endless 价格、实机阳光收集结果、精确目标视口或真实种植动作认证时，再恢复相应验证。

## 10. Git Scope

- Files intended for this Iteration commit: the State/runtime, UI, tests, README/docs, P01–P05 Plans, `verify.md`, this Delivery report, the 005 cancellation-number record, and the two SDD memory files listed in Section 5.
- Unrelated working-tree files explicitly excluded: edits under `.agents/skills/`, untracked `.agents/skills/direct-task/` and `.agents/skills/sdd-agents/`, `.codex/config.toml`, `AGENTS.md`, `.env`, and historical unreviewed bundles under `.sdd/004-game-state-observation/evidence/`.
- Remote / branch intended for push: `origin/main`。
- Primary commit: `8cdc3b821544c2b76fa3a0309c9ac62e1c800306` (`sdd(004): feat game state observation`); pushed by ordinary fast-forward.
