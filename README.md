# 大乐透预测实验室

一个用来**戳破"彩票能被算法预测"幻觉**的小实验。

用 5 种不同思路的模型（随机基线、频率统计、马尔可夫链、LSTM 神经网络、遗传算法）并行预测大乐透号码，每期生成 4 注投注，开奖后真刀真枪对比长期命中率和投入产出比。

![screenshot](https://placehold.co/800x400?text=Preview)

---

## 核心想法

- **彩票是真随机**，任何模型的长期命中率都应该**收敛到随机基线**
- 这个平台的意义**不是"预测中奖"**，而是：
  - 验证"冷热号"、"号码记忆"、"神经网络能抓特征"这些说法
  - 提供一个**公平的长期基准**，让各种"大师"的方法可被量化检验
  - 完整地走一遍 **数据抓取 → 建模 → 回测 → 可视化 → 自动化** 的链路

## 架构

```
数据流
  ├── 中国体彩官方 API
  ├── SQLite (data/daletou.db)
  ├── 5 个预测模型
  └── 导出 JSON → Vue3 前端 → GitHub Pages

定时任务（GitHub Actions）
  ├── 周一/三/六 18:00 北京时间 → 生成下期预测
  └── 周一/三/六 22:30 北京时间 → 抓开奖结果 + 评估 + 重新部署前端
```

## 目录结构

```
DaLeTou/
├── backend/                 # Python 后端
│   ├── requirements.txt
│   ├── src/
│   │   ├── config.py        # 彩票规则/奖金表/模型列表等
│   │   ├── db/              # SQLite 访问
│   │   ├── scraper/         # 历史数据爬虫
│   │   ├── models/          # 5 个预测模型
│   │   ├── tasks/           # 预测 / 评估 / 回测
│   │   ├── export/          # 导出 JSON 给前端
│   │   └── utils/
│   └── tests/
├── frontend/                # Vue3 + Vite + ECharts
│   └── src/{views,components,api,router,styles}
├── data/
│   ├── daletou.db           # SQLite 数据库
│   └── export/*.json        # 前端消费的 JSON
└── .github/workflows/
    ├── predict.yml          # 定时预测
    ├── evaluate.yml         # 定时评估
    └── deploy-frontend.yml  # 前端部署
```

## 本地跑通（5 分钟）

```bash
# 1. 安装后端依赖
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ..

# 2. 抓取全部历史开奖（约 2700 期，耗时 1-2 分钟）
python -m backend.src.scraper.fetch_history

# 3. 回测最近 200 期，给前端铺满数据
python -m backend.src.tasks.backtest --start -200

# 4. 生成下一期预测
python -m backend.src.tasks.predict

# 5. 导出 JSON
python -m backend.src.export.to_json

# 6. 跑前端
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## 部署到 GitHub（自动化）

1. 把仓库推到 GitHub
2. 仓库 **Settings → Pages → Source** 选 "GitHub Actions"
3. 仓库 **Settings → Actions → General → Workflow permissions** 勾选 "Read and write permissions"
4. 手动触发一次 `Predict Next Draw` 工作流补齐初始数据
5. 完成。此后每周一/三/六自动跑。

## 模型简介

| 模型 | 思路 | 用于验证 |
|---|---|---|
| **随机基线** | 均匀随机 | 所有其他模型的对照组 |
| **频率统计** | 按近 300 期频次加权抽样 | "冷热号理论" |
| **马尔可夫链** | 上期号码 → 下期号码 转移概率 | "号码记忆/惯性" |
| **LSTM 神经网络** | 多热向量序列建模 | 是否存在可学习的时序模式 |
| **遗传算法** | 以"历史回本率"为适应度进化号码组合 | 是否存在"历史最佳组合" |

## 奖级对照（按国彩官方规则）

| 前区命中 | 后区命中 | 奖级 | 奖金 |
|:---:|:---:|:---:|:---:|
| 5 | 2 | 一等 | 浮动，按 1000 万计 |
| 5 | 1 | 二等 | 约 30 万 |
| 5 | 0 | 三等 | 10000 |
| 4 | 2 | 四等 | 3000 |
| 4 | 1 | 五等 | 300 |
| 3 | 2 | 六等 | 200 |
| 4 | 0 | 七等 | 100 |
| 3 | 1 / 2 | 八等 | 15 |
| 3 | 0 / 2 | 九等 | 5 |
| 其他 | — | 未中奖 | 0 |

## 免责声明

彩票是负期望博弈。本项目仅供**算法研究和数据可视化**展示，**不构成任何购彩或投资建议**。未成年人禁止购彩。理性娱乐，量力而行。

## License

MIT
