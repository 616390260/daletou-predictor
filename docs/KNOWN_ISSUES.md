# KNOWN_ISSUES · 已知问题档案

> **写入门槛**：同一现象在 `RUN_LOG.jsonl` 中**重复出现 ≥ 2 次**才记一条。
> **写入责任人**：AI 协作者（按 `AGENTS.md` 反思 Protocol）。
> **不要写**：单次偶发、未经 RUN_LOG 证据支持的猜测。

格式：

```
## [YYYY-MM-DD] 简短标题
- 现象：用户 / workflow 表现出的可观测症状
- 证据：RUN_LOG 行（贴 ts + run_id），或 GitHub run URL
- 根因：分析得到的真实原因（区分确认 / 推测）
- 规避：当前可用的 workaround
- 修复：是否已彻底修，commit / PR 链接
```

---

## [2026-10-19] 多个 workflow 并发写主干，预测生成后推送失败

- 现象：predict 已训练模型并生成 26119 预测，提交阶段被拒绝；runner 结束后新预测和权重未持久化，后续通知与 JSON 导出也未执行。
- 证据：[predict 39039619380](https://github.com/616390260/daletou-predictor/actions/runs/39039619380)（2026-10-17 14:12 UTC）与 [predict 39040781955](https://github.com/616390260/daletou-predictor/actions/runs/39040781955) 均在 `git-auto-commit-action@v5` 推送时报 `main -> main (non-fast-forward)`。失败运行写出的 RUN_LOG 位于被拒绝的本地提交中，因此主干日志未收录这两次失败；需结合 Actions 原始日志判断。
- 根因（已确认）：predict、evaluate 没有共享写入锁，backtest 与 reflect 使用各自独立的 concurrency group；生成产物期间其他 workflow 推进同一分支，当前工作区随即过期。仅串行还不够，默认 checkout 会固定到排队前的事件 SHA。
- 规避：恢复产物时暂停其他同分支写入者，重新读取分支最新状态后再运行；避免强推或对 SQLite/模型权重盲目 rebase。
- 修复：四个 writer 按实际写入分支共享 `daletou-state-*` 并发组，设置 `cancel-in-progress: false` 与 `queue: max`，保留最多 100 个待运行任务，防止其他类型任务替换等待中的预测；取得锁后 checkout 分支最新头，reflect 使用触发运行的 `head_branch`，其他事件回退 `ref_name`。本地配置回归测试已补齐，线上仍须发布后通过真实 workflow 验证。排队规则见 [GitHub 官方文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)。
