# AGENTS.md · 给 AI 看的项目速查表

> 面向 AI 协作者的"避坑指南"。读完这一页，你应该能安全地改动本仓库而不会踩雷。
> 面向人类请看 [`README.md`](./README.md)。

## 项目一句话

大乐透多模型命中率对比实验室：9 个模型（`random / frequency / bayesian / markov / xgboost / lstm / transformer / genetic / ensemble`）对真实历史开奖做 walk-forward 回测，产物走 git 存储 + `raw.githubusercontent.com` 当 CDN 给前端读。

## 目录速览

```text
backend/src/
  config.py          ← 单一事实源：MODELS / BACKTEST_MIN_START_INDEX / PRIZE_TABLE
  tasks/
    predict.py       ← 生成本期预测（+ 可选微信推送）
    evaluate.py      ← 拿真实开奖评估上期预测
    backtest.py      ← walk-forward 批量补历史（支持时间预算续跑）
    notify_backtest.py ← 回测结束时推送进度/完成/异常通知
  models/            ← 9 个模型的实现，统一 get_model(name) 返回带 .predict(history, n) 的对象
  export/to_json.py  ← DB → data/export/*.json（前端消费）
  export/chart.py    ← 渲染 data/img/*.png
  db.py              ← sqlite 连接与 schema
  utils/notifier.py  ← ServerChan / 企业微信 / PushPlus 三通道广播

.github/workflows/
  predict.yml  evaluate.yml  backtest.yml  deploy-frontend.yml

data/
  daletou.db           ← 核心，所有预测/结果/开奖都在这里
  export/*.json        ← 前端读这些
  img/*.png            ← 图表
  lstm_*.pt / transformer_*.pt / xgboost_probs.npz  ← 模型权重，入库（故意的）
  .backtest_state.json ← backtest.py 写的进度文件，workflow 消费
```

## 坑 1：GitHub Actions 单 job 硬上限 6 小时

**全库 walk-forward 一轮要 ~13 小时，单 job 根本跑不完。**

本仓库的 `backtest.yml` 走"**时间预算 + 自动接力**"模式解决：

1. `backend/src/tasks/backtest.py` 支持 `--time-budget-seconds`，到点后用 `break` 正常退出（不抛异常），写 `data/.backtest_state.json` 记录 `{done, processed, total, last_issue, ...}`
2. workflow 后续的 `Export JSON / Render charts / Commit progress / Notify / Auto-dispatch` **全部 `if: always()`**，哪怕 backtest 异常也会保存已算的部分
3. `Commit progress` 用 `stefanzweifel/git-auto-commit-action@v5` 把 DB + JSON + 图表 + state 推回 main
4. `Auto-dispatch next run` 读 state，若 `done=false` 就用 `GITHUB_TOKEN` + `gh workflow run` 触发自己
5. `concurrency: group=backtest, cancel-in-progress: false` 保证新 run 排队等旧 run 完全结束才启动
6. 下一轮 `actions/checkout@v4` 拉到包含最新 DB 的 main，靠 `backtest.py` 第 61 行的 `SELECT ... LIMIT 1` 命中即跳过，自然从断点续跑

**你改 backtest.yml 的注意事项：**

- 时间预算 `time_budget_seconds` 必须**小于** `timeout-minutes` 转成秒值，差值留给 commit/export/dispatch（经验值：`timeout-minutes: 355`、`time_budget_seconds: 17400` ≈ 4h50m）
- 续跑参数 `force` 必须强制 `false`，否则会把前一轮刚写的记录删掉重算
- `permissions` 里 **必须有 `actions: write`**，否则 `gh workflow run` 触发下一轮会 403
- `GITHUB_TOKEN` 通过 REST API 调 `workflow_dispatch`/`repository_dispatch` 是 GitHub 明确允许的两个例外（push 触发被禁是另一回事）

## 坑 2：续跑的幂等性靠 DB，不要破坏

看 `backend/src/tasks/backtest.py`：

```python
existing = conn.execute(
    "SELECT 1 FROM predictions WHERE issue = ? AND model = ? LIMIT 1",
    (real_issue, name),
).fetchone()
if existing and not force:
    continue
```

这段是整个续跑机制的支点。动 schema 或动这段的时候要想清楚：

- `predictions` 主键 `(issue, model, ticket_idx)`，用 `INSERT OR REPLACE` 写
- `results` 同样主键，`results` 依赖 `predictions`（level/amount 算的时候需要中奖对比）
- 如果你要加新模型或改 `ticket_idx` 语义，`force=true` 跑一次全量重算是安全兜底

## 坑 3：通知机制已经集成好了，别重造

项目里 **三通道微信推送**已经是现成的：`backend/src/utils/notifier.py` 的 `notify(title, content)`。

需要的 repo secret（`predict.yml` 已经在用，一般都配过）：

- `SERVERCHAN_SENDKEY`（推荐，最简单）
- `WEWORK_WEBHOOK`
- `PUSHPLUS_TOKEN`

任一配置就能收到，未配置时静默跳过。`backtest.yml` 中 `Notify progress / completion / failure` step 调用 `python -m backend.src.tasks.notify_backtest`。

## 坑 4：产物都要 git commit，别加进 .gitignore

所有预测/DB/图表/权重都 commit 到 main 是**故意**的：

- 前端通过 `raw.githubusercontent.com/<repo>/main/data/...` 直接读，相当于免费 CDN
- workflow 之间用 git 作为"状态存储"（这就是续跑能工作的基础）
- `.gitignore` 里只忽略 `data/*.bak` / `data/*.tmp` / `data/lstm_*_cache.pt`，别动

## 触发/取消 workflow 的 API 小抄（给 AI 自己跑的时候用）

用户的 `~/.git-credentials` 里存着 GitHub PAT（`credential.helper=store`），可以用 Python 读出来调 API，但**不要把 token 明文 echo 到 terminal log**。示例见过往会话。

```python
import json, os, re, urllib.request
with open(os.path.expanduser("~/.git-credentials")) as f:
    token = next(re.match(r'https://616390260:([^@]+)@github\.com', l.strip()).group(1)
                 for l in f if re.match(r'https://616390260:', l.strip()))
# api(method, path, body) ...
```

关键端点：

- `GET  /repos/{owner}/{repo}/actions/workflows/{file}/runs` — 列 run
- `POST /repos/{owner}/{repo}/actions/workflows/{file}/dispatches` — 触发（body: `{ref, inputs}`）
- `POST /repos/{owner}/{repo}/actions/runs/{run_id}/cancel` — 取消
- `GET  /repos/{owner}/{repo}/actions/runs/{run_id}/jobs` — 看步骤进度

## 规范

- 代码注释风格：**JSDoc** `@param @returns`（Python 里也用这个风格写 docstring）
- 回复用户：**中文，直接，不铺垫**
- 改 DB schema 前先读 `backend/src/db.py` 的 `init_db`；加字段要迁移老库
- 新模型要 `backend/src/models/__init__.py` 的 `get_model` 里注册，并加进 `config.MODELS`

## 我最近学到的教训

- **workflow 里后置步骤一定要 `if: always()`**，否则 backtest 一旦超时被 GitHub kill，之前 5h+ 算的东西就因为没 commit 而全部丢失。这是这个项目踩过的最惨一次坑。
- **改完 workflow 要测一次小数据**（比如 `start=-50`）再上全量，不然每次都等 5h 才知道 yml 写错了。
- **别把 token 拼进 shell 命令**，用 Python `urllib` + headers 发请求更安全（terminal log 会被其他工具读）。
- **GitHub schedule 不可信**：predict.yml 单一 cron 从未按时触发过；evaluate.yml 延迟 81 min。解法是一个 workflow 配多个 cron 时间点 + 任务代码幂等，而不是押注单点。
- **`Notify predict` step 出现 `skipped` 不代表故障**：这是幂等设计的**正确行为**。当 DB 里已经有当期所有 9 个模型的预测（通常是前一次 predict run 已经预测过这期），`predict.py` 会把 `any_new` 置为 False，不往 `GITHUB_OUTPUT` 写 `issue`，于是 Notify step 的 `if: steps.pred.outputs.issue` 判定为假，被跳过。**判断是否真的"漏发通知"的正确姿势**：先查 `predictions` 表同期覆盖度（`SELECT issue, COUNT(DISTINCT model) FROM predictions GROUP BY issue ORDER BY issue DESC LIMIT 5`），再查该期号更早的 workflow run 是否成功 Notify 过。覆盖度 = 9 且更早有成功 Notify → 幂等命中，一切正常，不要重复触发。
- **GitHub schedule 几乎完全不工作**：这个 repo 的 predict.yml schedule 历史触发次数 = 0，evaluate.yml = 1。不能靠 cron 驱动业务。已改为事件链 + backtest 心跳触发，见下面"事件链"章节。

## 事件链（核心调度模型）

> **Do NOT 依赖 GitHub schedule 触发业务**。下面这个事件链是这个 repo 的心跳源。

```
[种子] backtest 接力循环（60min/轮，time_budget=3600）
         ├─ 每轮结束判断：当前是开奖日 + 北京时间 ≥ 21:30 吗？
         │     是 → dispatch evaluate.yml
         │     否 → 只接力 backtest 自己
         │
         ↓ (开奖日晚 21:30+)
     evaluate.yml：拉取最新开奖号入库 → 评估 9 模型命中 → 推送开奖通知
         │
         ├─ 评估到新期号（evaluated_issue != ""）时
         │     → dispatch predict.yml（预测下一期）
         │     → dispatch backtest.yml（把新期纳入 walk-forward）
         │
         ↓
     predict.yml：LSTM/Transformer 增量训练 → 预测下一期 → 推送预测通知
     backtest.yml：把新开奖那期 walk-forward 跑一遍（几分钟）
```

**为什么这么设计**：

1. **predict 不抢 20:00 停售前的时间**。开奖 21:15 后，距下一次开奖约 46h，从容不迫。
2. **不依赖 GitHub schedule**。靠 backtest 自续 dispatch（concurrency 排队+fail-safe 接力）持续产生心跳。
3. **predict 不等 backtest 完成**。evaluate 触发 predict 和 backtest 是**并行**的——LSTM/Transformer 自己有增量训练，拿到最新 DB 就能预测。backtest 是评估工具，不是预测依赖。
4. **每个环节都幂等**：evaluate 只处理无 results 的期，predict 只生成新期缺失的模型，backtest 只跑未跑过的 (issue, model)。心跳重复 dispatch 不会重复骚扰。

**事件链的必要条件**：

- `backtest.yml` 必须一直在心跳（哪怕 done=true 也接力）。如果心跳断了，evaluate 就不会被触发，事件链断开。
- 心跳断了怎么恢复？任何时候手动 `gh workflow run backtest.yml` 一次，心跳就恢复了。

**调试事件链**：

```bash
# 看最近 3 天所有 workflow run（包括 dispatch 源）
gh run list --limit 50 --json name,event,createdAt,status,conclusion
# 找事件链是否完整：evaluate 成功 → 应紧跟一个 workflow_dispatch 触发的 predict
```

## AI 反思 Protocol（每次进入本 repo 必读）

> **这一节是给 AI（Cursor agent / Claude Code / 任何协作者）的强制性行为指引。**
> 你每次被召唤进这个 repo 时，第一件事**不是**直接回答用户的问题，而是先完成反思环节。

### 触发条件

- 用户的问题与 workflow / backtest / predict / evaluate / 通知 / 数据 / 回测进度有关
- 或者用户明显在"排查什么东西出问题了"
- 或者是一个新 session 的第一轮对话

以上任一成立时，**在回答前**执行以下步骤：

### Step 1：读 `docs/RUN_LOG.jsonl` 最后 20 行

这是所有 workflow run 的结构化记录（workflow 结束自动追加）。字段见 `backend/src/utils/run_log.py`。

你要识别三种信号：

1. **连续失败同一个 step** → 说明是系统性问题，不是偶发。读对应 run 的 logs（用 GitHub API，参考 `API 小抄` 一节），找根因。
2. **性能退化**：同类 run 的 `duration_s` 显著变长（比如 backtest 单轮时间从 4h 变 8h）→ 可能是模型/数据变化或 runner 问题，值得提醒用户。
3. **新的 outcome 模式**：出现从未见过的 outcome 或 extra 字段异常 → 说明有新变化，至少记一笔。

### Step 2：决策是否需要升级经验

基于 Step 1 的发现，决定：

| 发现 | 动作 |
|---|---|
| 重复故障 ≥ 2 次 | 写/更新 `docs/KNOWN_ISSUES.md` 一条，含故障特征、根因、规避方式 |
| 新的跨项目可复用 pattern | 调 `user-memory` MCP 的 `add_observations` 追加到 `pattern:*` 或新建 entity |
| 本项目特有的约定变化 | 更新 `AGENTS.md` 对应章节 |
| 仅当次偶发 | 不做任何持久化，只在回答里提一句 |

### Step 3：再回答用户

反思完了再回应用户原问题。如果反思发现的问题**比用户问的更重要**（比如用户问小事但你发现生产故障），**先告知**用户这个更紧急的发现。

### 反例（不要这样）

- ❌ 直接改代码不先读 RUN_LOG
- ❌ 每次反思都往 AGENTS.md 堆内容（只有**重复出现 ≥ 2 次**的模式才值得沉淀）
- ❌ 把猜测写进 KNOWN_ISSUES（必须基于 RUN_LOG 证据）

### 用 jq 快速看最近状态

```bash
# 最近 20 条 run
tail -20 docs/RUN_LOG.jsonl | jq '.'

# 最近所有 failure
grep '"outcome":"failure"' docs/RUN_LOG.jsonl | tail -10 | jq '.'

# backtest 进度趋势
grep '"workflow":"backtest"' docs/RUN_LOG.jsonl | jq '{ts, processed:.extra.processed, total:.extra.total}' | tail -10
```

### 为什么这么设计

AI 的"进化"受限于模型权重不可改。能做的是**积累外部 context**，每次被召唤时加载回大脑。RUN_LOG 是事实层（workflow 自动写），AGENTS.md / KNOWN_ISSUES / user-memory 是知识层（AI 反思后写）。事实→知识的转化发生在"用户召唤 AI"这个事件上，不需要定时任务也不需要 API key，靠文档约定即可闭环。

**换句话说：这个 repo 每多跑一次 workflow，积累的外部经验就多一份；下一次 AI 进来就更强一点。** 这是目前能做到的最接近"自主进化"的形态。
