# 九注覆盖实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline execution. Follow the checked tasks below.

**Goal:** 固定 18 元预算优化至少一注中奖的覆盖，并独立记录核对。

**Architecture:** 纯计算覆盖模块与 SQLite 快照服务分开；predict 生成、export 核对并输出独立 JSON，首页消费。金额数据修复和按期奖级服务提供可信口径，不改原始选号或冻结 Laya 实验。

**Tech Stack:** Python / NumPy / SQLite / Vue 3 / unittest / Playwright。

### 1. 精确覆盖计算
- [x] 新建 `backend/tests/test_portfolio.py`，独立穷举小球池，验证重复票并集、合法性、搜索确定性和严格不降低覆盖率。
- [x] 运行 `backend/.venv/bin/python -m unittest backend.tests.test_portfolio -v`，确认缺少模块导致失败。
- [x] 新建 `backend/src/portfolio/coverage.py`，参数化球池，默认 35 选 5 + 12 选 2；缓存前区命中模式；坐标搜索后区。
- [x] 重跑测试，并用真实九注独立穷举全部 21,425,712 种开奖核对计数。

### 2. 快照和历史核对
- [x] `backend/src/db/schema.sql` 新建独立 `portfolio_runs` 表，唯一键为期号和版本；JSON 快照保存九注。
- [x] `backend/src/portfolio/service.py` 读取 MODELS 各第 1 注，拒绝缺模型、事后前瞻、源候选变更；保存源摘要和截止期；核对只写结果。
- [x] `backend/src/tasks/portfolio.py` 提供 `--issue` 与 `--backtest`；历史仅取 significance 已核验模型期号交集，明确模拟。
- [x] predict 完成后生成独立方案；export 核对现存快照并输出 `portfolio.json`。用临时数据库验证幂等、未来隔离和原预测完全不变。

### 3. 数据口径
- [x] 新增抓取回归测试，先复现销量/奖池颠倒；修正 `fetch_history.py`。
- [x] 新建按期奖级函数及 26013/26014 边界测试，evaluate/backtest 使用它；旧冻结 PRIZE_TABLE 留作兼容。
- [x] 从源重新获取历史，严格匹配日期/号码后只更新金额；保存摘要和修复审计。金额特征版本纳入 LSTM/Transformer/XGBoost 缓存判断。
- [x] 2026 年已有结果重新核对奖级；导出标明奖金估算，覆盖回测只比较中奖事件。

### 4. 页面和发布
- [x] 新建 `frontend/src/components/PortfolioCard.vue`，显示当期九注、18元、原/优化理论覆盖、历史模拟和前瞻核对分区。
- [x] `frontend/src/api/index.js` 添加独立请求，Home 传入当前预测期号，旧期/404/慢请求不影响原数据。
- [x] 在临时数据库生成历史和当期报告，运行新旧后端测试、前端构建及 375px/1440px 浏览器检查。
- [x] 审阅差异，修复发现，提交代码/数据，更新远端并确认 Pages 最新构建及线上报告。

## 验证记录

- 后端 unittest discover：61 项通过；基础脚本通过。
- 前端 Node 测试 2 项通过，Vite 生产构建通过。
- 第26118期原/新方案独立穷举全部21,425,712种开奖，计数分别为10,071,551和10,343,338，与优化器一致。
- 375px/1440px 浏览器验证号码、59期模拟明细、过期/404/慢请求处理通过。
- 实际修复后DB重建Laya v1四份JSONL逐字节相同，冻结摘要保持d05641d90e09cc02caf5ee77e7ae2b314bccb1a1d5722587b9fbb02f254e39bc。
- 原始predictions和draw日期/号码与修复前DB完全一致；两项审查均LGTM。
- 发布提交dfe83fa；Pages run 38802419433成功，线上portfolio.json确认26118和59期模拟结果。
