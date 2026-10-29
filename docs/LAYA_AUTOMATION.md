# Laya 自动续跑

## 运行方式

九模型预测和前端 JSON 持久化后，predict 触发 `laya.yml`。开奖后的 evaluate 在核对到新一期时也触发它。Laya 取得与其他任务共用的写入锁后，读取主干最新状态：

1. 核对已保存且尚无结果的 Laya 选择，追加实际开奖、命中数和按当期规则估算的奖金。
2. 检查下一期待选记录。已选、候选不齐或已过停售时间时跳过。
3. 需要新选择时，恢复固定多语言基座和已入库决策头，在 Linux CPU 上给九模型候选评分、保存一注。
4. 保存 JSON 与运行日志，由 Pages 部署更新页面。

这条链路不需要本地电脑开机。当前仍用训练截止 **26116** 的 `daletou-decision-v1`；自动选注与自动重训是两个不同任务，本次没有改动训练数据、冻结测试报告或原九模型。

## 数据边界

- 自动选注只允许数据库最新开奖的下一期，且必须在下一个常规开奖日北京时间 20:00 前；开始推理和保存前均检查。
- 使用九模型已有候选，状态只读取目标期之前的开奖和历史结果。模型训练截止期必须早于目标期。
- 已发布选择不可被再次评分或覆盖；核对只增加结果，不改变原号码、候选评分、版本、发布时间与前瞻标记。
- 121—123 期当时没有 Laya 选择记录。自动任务不会为已开奖期创建“前瞻选择”；以后如补做，只能单独标为事后模拟。
- 奖金按当前项目的规则估算口径，含奖池档位近似，不代表真实购票收益。冻结历史评估保持原口径。

## 恢复与排查

```bash
gh workflow run laya.yml --ref main
gh run list --workflow laya.yml --limit 5
python -m backend.src.tasks.laya_sync --check
python -m backend.src.tasks.laya_sync --settle-only
```

`--check` 只读并显示 `issue / needs_decision / reason / version`。`--settle-only` 仅核对已有选择，不安装或加载神经网络。推理安装或下载失败时，workflow 仍尝试提交已完成核对和失败日志；原九模型已由上游保存，不受影响。检查失败步骤后重新触发 Laya；不要使用强制覆盖原始预测的方式恢复。

手动 CPU 同步：

```bash
python -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r backend/requirements-laya.txt
python -m backend.src.laya.bootstrap --version daletou-decision-v1
LAYA_DEVICE=cpu HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 USE_TF=0 python -m backend.src.tasks.laya_sync
```

基座固定为 `convaiinnovations/laya-multilingual` revision `e4e9ddf21a7b1903b7acffd8814ad4307bf63a67`，下载与缓存均验证 SHA256。只在 bootstrap 阶段联网；推理使用已验证的本地文件。
