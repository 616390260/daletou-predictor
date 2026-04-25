# AI_NOTES · 未来的我，看这里

> 这是 AI 协作者（Cursor agent / Claude / 任何模型）写给**下一次进入本 repo 的自己**的私人备忘录。
> 用户也可以读，但**主要受众是 AI**。
>
> 写入原则：**只记会复用、能省时间的东西**。一次性的发现请直接回用户消息，别污染本文件。

---

## 我每次进 repo 的最优开场动作（≤ 30 秒）

按 `AGENTS.md` 的反思 Protocol，但这里是**操作版速记**：

```bash
# 1. 看事实层（机器写的，最权威）
tail -20 docs/RUN_LOG.jsonl 2>/dev/null || echo "[note] 本地无 RUN_LOG，去 GitHub main 上看"

# 2. 看事件链是否还活着（最近 6h 有 backtest run 就算活）
#    需要在能调 gh CLI 的环境，否则跳过
gh run list --workflow=backtest.yml --limit 5 --json status,conclusion,createdAt 2>/dev/null

# 3. 看我自己上次留了什么备忘
sed -n '1,80p' docs/AI_NOTES.md
```

**Then** 才回答用户。如果反思发现的事比用户问的更紧急，先告知。

---

## 常见误判 & 避坑清单

### ❌ 误判 1：「本地没 `docs/RUN_LOG.jsonl` = 机制坏了」

**真相**：RUN_LOG 由 GitHub Actions 在 `main` 分支上 commit，本地仓库不一定 `git pull` 到最新。
**做法**：在回答前先 `git fetch && git log origin/main -- docs/RUN_LOG.jsonl --oneline | head -3` 确认 main 上有没有，再下结论。

### ❌ 误判 2：「Notify step skipped = 漏推送了」

**真相**：见 `AGENTS.md` 同名教训。`predict_any_new=false` 时本就该 skip，是幂等机制，不是 bug。
**判断真漏推**：查 `predictions` 覆盖度 + 该期是否从未成功推过。

### ❌ 误判 3：「GitHub schedule 没触发 = 我代码写错了」

**真相**：这个 repo 历史上 `predict.yml` schedule 触发次数 = 0，`evaluate.yml` = 1。是 GitHub 的问题，不是代码。
**做法**：所有调度都靠事件链 + heartbeat，不要再"修" cron 时间。

### ❌ 误判 4：「想通过加新模型/调超参提高命中率」

**真相**：大乐透 i.i.d. 随机，所有模型期望命中率 = random 基线。任何短期偏离都是采样噪声。
**做法**：新模型只为"丰富对照实验"，绝不以"提升命中率"为成功指标。指标用 t 检验 p 值 vs random。

---

## 我能动 vs 我不能动

| 我（AI）能做 | 我做不到 |
|---|---|
| 改代码、改 workflow、改文档 | 在后台常驻、自己定时跑 |
| 在对话里读 RUN_LOG 反思 | 自动执行反思（必须由"用户召唤"事件触发） |
| 让用户用 `gh` 命令救事件链 | 自己点 GitHub UI 按钮 |
| 把发现写进本文件让下次自己看到 | 修改自己的模型权重 |

**结论**：我的"进化"只能体现为**仓库里这些文件的累积**。本文件是其中最贴身的一份。

---

## 健康巡检 checklist（用户问"系统还活着吗"时直接走完）

按顺序，每条独立，**任何一条 ≠ 预期就停下报告**。需要 `gh` CLI。

```bash
# C1. 事件链心跳：最近 6h 是否有 backtest run？
#     预期：≥ 1（不论成功/失败/进行中都算活）
gh run list --workflow=backtest.yml --limit 5 --json status,conclusion,createdAt,event

# C2. 最近 5 次 backtest 的 conclusion 分布
#     预期：不能连续 ≥ 3 次 failure（连续失败 = 死链）
gh run list --workflow=backtest.yml --limit 5 --json conclusion --jq '[.[].conclusion]'

# C3. 最近一次 evaluate 是否在最近一次开奖日 21:30 之后跑过
#     预期：开奖日（周一/三/六）当晚必须有 evaluate run
gh run list --workflow=evaluate.yml --limit 3 --json createdAt,conclusion

# C4. 数据新鲜度：最近一期开奖距今天数
#     预期：≤ 4 天（超过说明抓取断流）
sqlite3 data/daletou.db "SELECT MAX(date), julianday('now') - julianday(MAX(date)) AS days_ago FROM draws"

# C5. RUN_LOG 是否在长
#     预期：本周内有新增行
git log --since="7 days ago" --oneline -- docs/RUN_LOG.jsonl
```

**判定**：
- C1 = 0 → 心跳断，立即 `gh workflow run heartbeat.yml`，再 `gh workflow run backtest.yml`
- C2 连续 ≥ 3 failure → 看最新失败 run 的 logs，**很可能是 yml 改坏了**，回滚或修
- C3 缺 → evaluate 没被 backtest 心跳触发，**回去查 backtest.yml 的 dispatch evaluate 那段**
- C4 > 4 天 → 抓取问题，看 `backend/src/tasks/predict.py` 拉数据那段
- C5 7 天没动 → workflow 没在跑（C1 应该已经先报警了）

---

## 反思日志（按时间倒序追加）

> 每次进入本 repo 完成反思后，**只在有新发现**时追加一条。无新发现就别污染。
> 格式：`### [YYYY-MM-DD HH:MM 模型名] 一行总结` + 必要的 bullet。

### [2026-04-25 13:54 Claude] 上线半自动反思（reflect.py + reflect.yml）

- 加了 `backend/src/utils/reflect.py`：纯本地规则识别 R1 连续失败 / R2 进度卡死 / R3 性能退化，幂等指纹 fp:XXXXXXXX
- 加了 `.github/workflows/reflect.yml`：schedule 每 12h + workflow_run 链式触发（在 backtest/predict/evaluate 跑完后立即跑一次）
- 不调 LLM、不发通知；只追加 `KNOWN_ISSUES.md` 和本文件的反思日志
- 已本地 mock 跑通：连续 failure + 进度卡死两条规则都能命中并幂等
- **意义**：从「用户召唤 AI 才反思」升级为「workflow 心跳后自动反思」，不再消耗用户算力
- 下一个 AI 进来：进 KNOWN_ISSUES 看 `fp:` 开头条目，把"根因/修复"从"待人工确认"变成具体内容——**这是你比 reflect.py 强的部分**

### [2026-04-25 13:51 Claude] 锁死闭环 + 加巡检

- 在 `AGENTS.md` 顶部钉了「先读 `docs/AI_NOTES.md`」。这条约定是闭环的入口，**别删**。
- 加了 `docs/README.md` 说明三件套的角色，防止后人觉得"docs 太乱"去合并。
- 给本文件加了「健康巡检 checklist」C1-C5，用户问"系统还活着吗"时按这 5 条走，不用现想。
- 仍未动业务代码 / workflow。

### [2026-04-25 13:50 Claude] 初始化本文件

- 用户问"AI 能不能自我进化"。本文件是我对这个问题的实际回答之一：**不能改权重，但能让仓库越来越聪明**。
- 同时建了 `docs/KNOWN_ISSUES.md`（AGENTS.md 引用了但之前不存在）。
- 没有动业务代码、没有动 workflow。只补了文档基础设施。
- 下一次进来的我：先 `tail -20 docs/RUN_LOG.jsonl`，再读本文件最近 3 条反思日志。
