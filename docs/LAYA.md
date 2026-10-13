# Laya 独立决策实验

Laya 为大乐透单独学习，从原 9 个模型各自的一注中选一注。原模型和集成权重不受它影响。历史选择是事后按时间隔离的回测，不能当作当时已发布的预测。

## 本次实际数据和结果

- 原始开奖：2934 期，截至 26116。
- 首次可信监督样本：26059—26116，共 58 期、522 张候选。仅使用恢复日志明确证明逐期隔离的区间；更早回测可能复用未来权重，未作为监督标签。
- 按期分组：40 期训练（360 候选）、8 期验证（72 候选）、10 期测试（90 候选）。同一期不会跨分区。
- 冻结评估版 `daletou-evaluation-v1` 训练到 26098，实际训练 4 轮；验证与测试都晚于训练截止。
- 最新可用版 `daletou-decision-v1` 用全部 522 候选实际训练 4 轮，截止 26116。该版不能重算上述冻结成绩。

| 冻结测试，10 期各选一注 | 中奖注数 | 奖金 | 成本 | ROI |
| --- | ---: | ---: | ---: | ---: |
| Laya | 1 | 5 元 | 20 元 | -75% |
| 固定种子随机选择候选 | 3 | 15 元 | 20 元 | -25% |
| 原随机模型 | 2 | 10 元 | 20 元 | -50% |
| 原集成模型 | 1 | 5 元 | 20 元 | -75% |

Laya 候选 Brier 为 0.105195，训练中奖率常数基线为 0.099390，较低更好。本次没有支持优于基线的证据。样本够运行初次实验，远不足以证明稳定优势；评分不等同于可靠中奖概率。收益沿用项目固定奖金额表估算。

## 本地训练方式

复用 `~/laya-lab/train_local.py` 和公开 `convaiinnovations/laya-multilingual` 基础模型。仓库的 `train_head.py` 仅在独立训练进程中冻结编码器、关闭编码器 dropout，并保存约 29 MB 的专用决策头；原 SEO 训练器与权重未改动。保留原训练目标及仅在训练源内部的温度校准。共享 `.seo-laya.lock`，避免与 SEO GPU 任务同时运行。

正式决策头、配置和摘要保存在 `data/laya/adapters/`、`data/laya/manifests/`。本地目录缺失时可从仓库恢复决策头，基础编码器必须已在 `~/laya-lab/hf/` 缓存。推理核对基础与决策头 SHA256、版本和训练截止，拒绝时间越界。

从仓库根目录执行：

```bash
# Rebuild the explicitly verified dataset.
~/laya-lab/.venv/bin/python -m backend.src.tasks.laya_decision build

# Train new versions without overwriting existing checkpoints.
~/laya-lab/.venv/bin/python -m backend.src.tasks.laya_decision train --version daletou-evaluation-v2 --split train --epochs 4
~/laya-lab/.venv/bin/python -m backend.src.tasks.laya_decision evaluate --version daletou-evaluation-v2
~/laya-lab/.venv/bin/python -m backend.src.tasks.laya_decision train --version daletou-decision-v2 --split all --epochs 4
```

## 下一期如何使用

先按现有流程生成原 9 个模型的下一期候选，再同步含候选的数据库到本地，执行独立评审：

```bash
~/laya-lab/.venv/bin/python -m backend.src.tasks.laya_decision decide --issue 26117 --version daletou-decision-v1
```

缺任何原模型候选时直接报错，Laya 不会代为生成。训练截止必须严格早于评审期；已开奖历史的手动评审标记为 `retrospective`。重新冻结评估不会删除本期显式决策，也不会覆盖最新可用版。冻结选择和九个候选分数另保留于 `evaluation.decisions`。

报告写入 `data/export/laya.json`，提交并发布后在预测记录页显示。GitHub Actions 不加载本机 Laya 或自动运行独立评审；本次没有生成 26117 的原始预测或 Laya 选择。
