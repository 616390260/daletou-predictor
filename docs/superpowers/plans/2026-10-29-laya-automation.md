# Laya 自动续跑实施计划

**目标**：沿用已冻结的独立 Laya v1，在九模型预测持久化后自动选一注，开奖后自动核对并发布。用户已授权实施这一自动链路。

**架构**：新增 `laya.yml`，由 predict/evaluate 使用 `workflow_dispatch` 触发，加入现有同分支共享写入队列。Laya 使用 Linux CPU 和固定版本的多语言基座、已入库决策头；本地仍可用 MPS。选注与核对分开，核对不加载模型。保持九模型、冻结训练集和测试报告不变。

**边界**：自动任务只创建尚未开奖且未停售的下一期选择；过期或缺少候选时明确跳过。已发布选择不可改写。121—123 缺失的选择不伪装成当时的预测。暂不自动重训，继续用训练截止 26116 的 v1 观察前瞻表现。

## 1. 云端运行环境

- [ ] 先写 CPU 设备选择、基座准备和摘要校验的失败测试，再实现。
- [ ] 修改 `backend/src/laya/runtime.py` 支持 `LAYA_DEVICE=cpu`，本地默认仍用 MPS。
- [ ] 新增 `backend/src/laya/bootstrap.py`，只下载固定 Hugging Face revision 的所需文件并校验基座 SHA256。保持原冻结 adapter/config 不变。
- [ ] 新增 `backend/requirements-laya.txt` 固定已验证依赖；Linux 安装 CPU PyTorch。
- [ ] 运行 `backend/.venv/bin/python -m unittest backend.tests.test_laya backend.tests.test_laya_bootstrap`，再用真实 v1 完成 CPU 推理。

## 2. 生命周期与幂等

- [ ] 新增 `backend/tests/test_laya_sync.py`：已发布选择重复运行不改写；已开奖目标拒绝新前瞻选择；停售时间边界；缺候选跳过；核对保留评分、版本、kind；使用当期奖表；历史和冻结评估不变。
- [ ] 把开奖截止时间帮助函数提取到 `backend/src/utils/draw_calendar.py`，供覆盖方案和 Laya 共用。
- [ ] 新增 `backend/src/laya/lifecycle.py` 管理读取候选、创建前瞻选择和只追加结果；现有手动 `laya_decision.decide` 复用相同保护。
- [ ] 新增 `backend/src/tasks/laya_sync.py`：`--check` 仅检查并写 GitHub outputs，`--settle-only` 无模型核对，默认完成同步。每次真正保存前重新确认候选、时间和开奖结果；JSON 用临时文件替换。
- [ ] 运行 `backend/.venv/bin/python -m unittest backend.tests.test_laya_sync` 和完整后端测试。

## 3. 调度与发布

- [ ] 修改 predict/evaluate 尾部 dispatch `laya.yml`，传实际分支，不吞掉触发失败。
- [ ] 新增共享 writer 队列中的 `laya.yml`：先核对、再检查；需要选注才安装/缓存模型；失败时仍提交已完成核对和 RUN_LOG。
- [ ] 部署订阅 Laya workflow 完成事件；扩展 `test_workflow_writers.py` 覆盖第五个 writer 和触发链。
- [ ] 代码审查分为规则符合性与实现质量，修复阻断项后发布主干。
- [ ] 实际触发一次 Laya workflow，确认 120 期核对和 124 期开奖前选择，第二次重复触发确认完全幂等。原始九模型预测逐行对比不变。
- [ ] 确认 Pages 上本期 Laya 与结果显示，补充 AGENTS/使用文档说明云端调度及失败恢复。
