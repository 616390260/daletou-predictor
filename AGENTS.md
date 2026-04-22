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
