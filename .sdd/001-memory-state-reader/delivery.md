# Delivery Report

## 1. Delivery Metadata

- Iteration: `001-memory-state-reader`
- Delivered at: 2026-09-24（本地提交；远程推送待配置）
- Branch: `main`
- Commit type: `feat`
- Planned commit subject: `sdd(001): feat deliver PvZ State reader and 002 extensions`

## 2. Summary

交付本地只读 PvZ 1.0.0.1051 内存读取、版本化 State 和浏览器监视器，作为后续验证 JEV 的前置工程。用户明确接受当前用途的部分结果；严格同帧联证、自然事件时间线和真实退出/恢复现场保留为未验证后续项。

## 3. What Changed

- Python 3.12.13/uv 工程、`pywin32` 进程发现和 `ctypes` 只读内存访问。
- 固定版本身份、Board 链、阳光、植物/僵尸/掉落物和候选卡牌/进度读取。
- 带来源、时间、可用性、错误与缺口的 State，及只读 `probe`、`snapshot`、`serve` 命令。
- 本地浏览器状态栏、卡牌、5×9 草坪、僵尸详情与掉落物显示。
- 实现、测试、字段清单和文档与 002 的进度、分层血量、叠放植物扩展共用源码；当前 Git 基线无法将两者按文件拆成不重叠提交，故按用户同时交付 001/002 的要求作一次联合基线提交。

## 4. Plan and Task Status

| Plan ID | Status | Completed Tasks | Incomplete Tasks | Notes |
|---|---|---|---|---|
| P01 | Completed | T1, T2 | None | 环境、架构和只读内存模块 |
| P02 | Completed | T1, T2, T3 | None | 已知字段与公开候选偏移 |
| P03 | Completed | T1, T2 | None | State 与快照入口 |
| P04 | Completed for current local use | T1, T2 | None under revised acceptance | 空闲端口服务、页面和刷新已验证；现场可靠性联证延后 |

## 5. Files Changed

本 Iteration 基础范围：`.python-version`、`pyproject.toml`、`uv.lock`、`README.md`、`main.py`、`configs/`、`runtime/`、`game/`、`state/`、`dashboard/`、`tests/`、`docs/`、`.sdd/001-memory-state-reader/`、`.gitignore`、`.memory/`。002 对其中部分文件也有修改；联合提交的具体 002 范围见其 `delivery.md`。

## 6. Verification Result

- Overall result: **Passed**（用户批准的当前本地用途标准；保留未验证项）
- Evidence: [verify.md](verify.md)
- 已记录的 34 项测试、编译、JS 语法、进程只读采样和浏览器/API 检查通过；本次范围复核复用既有证据，没有声称重跑。

## 7. Deviations from Approved Plan

用户明确将 R9 严格同帧联证、R14 逐自然事件联证和真实游戏退出/重连后的浏览器恢复现场列为当前交付的非阻塞后续项，见批准的 Plan Index 和 P04 CD-06。端口冲突处理已由 CD-05 排除。未观察行为没有写为已验证。

## 8. Known Risks

- 某些卡牌、进度、地形与可种性仍为 `provisional` 或 `unavailable`，State 不得被当成完整、已动态验证的 JEV 决策输入。
- 僵尸 X 到页面棋盘的精确投影尚未校准；原始行、X/Y 和 HP 保留。
- 真正游戏退出/重连时的浏览器恢复行为尚无现场证据。
- 仓库未配置 Git remote；本地提交后无法完成推送，需另行配置目标。

## 9. Follow-up Items

- 需要更强可靠性证据时，再取得严格同帧游戏画面与 raw/State/API/UI 对照、自然事件前后时间线和真实退出/恢复观察。
- 配置 Git remote 后推送当前 `main` 分支；不使用 force push。

## 10. Git Scope

- Files intended for this joint 001+002 commit: 本报告 §5 的基础文件、`.sdd/002-progress-and-zombie-health/` 及其交付报告、两次迭代共用的源码/测试/文档。
- Unrelated working-tree files explicitly excluded: `.codex/config.toml`、`.sdd/.sdd-001-002.zip`；`.game/` 与 `.venv/` 保持忽略。
- Remote / branch intended for push: remote 尚未配置；当前分支 `main`，本地提交后等待配置推送目标。
