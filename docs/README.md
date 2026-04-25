# docs/ · AI 进化三件套

本目录是这个 repo 的"AI 外脑"。**别整理、别合并、别删**——每个文件角色不同，少一个闭环就断。

| 文件 | 角色 | 写入者 | 读取者 | 删除风险 |
|------|------|--------|--------|----------|
| `RUN_LOG.jsonl` | **事实层**：每次 workflow run 的结构化日志 | GitHub Actions（`backend/src/utils/run_log.py`） | AI / 人类排障 | 删了等于失忆，不可恢复 |
| `RUN_LOG.archive.jsonl` | 归档：超过 2000 行后老内容自动挪到这里 | `run_log.py` 自动 rotate | 长期回溯 | 同上 |
| `KNOWN_ISSUES.md` | **知识层（共享）**：≥ 2 次重复出现的故障档案 | AI 反思后写入 | AI / 人类 | 删了等于把踩过的坑再踩一遍 |
| `AI_NOTES.md` | **知识层（AI 私笔记）**：开场命令、误判清单、反思日志 | AI 自己写 | 下一次进来的 AI | 删了等于让下个 AI 从零开始 |

## 三层模型

```
事实层（机器写）  →  RUN_LOG.jsonl
        ↓ AI 反思（用户召唤时触发 / heartbeat 触发）
知识层（AI 写）  →  KNOWN_ISSUES.md（共享） + AI_NOTES.md（私笔记）
        ↓ 下次 AI 进来加载
进化（仓库越来越聪明，不是模型权重越来越强）
```

## 为什么这套机制能成立

- `RUN_LOG.jsonl` 是 workflow 自动追加的，**不依赖任何 API key、不依赖定时任务**
- AI 反思发生在"用户召唤 AI"这个事件上，**靠 `AGENTS.md` 顶部的约定**强制
- 三类文件 `git commit` 后跟代码一起走，**没有外部依赖**

详见 [`AGENTS.md`](../AGENTS.md) 的「AI 反思 Protocol」章节。
