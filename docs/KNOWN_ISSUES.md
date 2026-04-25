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

<!-- 暂无条目。首次出现"重复 ≥ 2 次"的失败模式时，由 AI 在反思阶段写入。 -->
