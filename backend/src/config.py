"""
全局配置
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "daletou.db"
EXPORT_DIR = DATA_DIR / "export"

DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

FRONT_MIN = 1
FRONT_MAX = 35
FRONT_COUNT = 5
BACK_MIN = 1
BACK_MAX = 12
BACK_COUNT = 2

TICKETS_PER_DRAW = 1
TICKET_PRICE = 2

# 用于频率/遗传/组合筛选等「看历史」逻辑：>= 当前库中期数即等价于全量反哺
MAX_HISTORY_WINDOW = 100_000

# LSTM 增量微调时，除新期外额外回放的最多期数（越大越贴近「全历史记忆」）
LSTM_INCREMENTAL_REPLAY_MAX = 2500

# 序列模型 / XGBoost 使用的过去期数（与各模型 WINDOW 常量保持一致）
SEQUENCE_FEATURE_WINDOW = 10

# Invalidate weights trained with reversed source money columns.
MONEY_FEATURE_VERSION = 2

# Walk-forward 回测：历史表中「第一期被评估目标」的最小行索引（0-based）。
# 评估第 i 行时 past = iloc[:i]，故 i 至少为 SEQUENCE_FEATURE_WINDOW+1，前若干行仅作上下文。
BACKTEST_MIN_START_INDEX = SEQUENCE_FEATURE_WINDOW + 1

# Legacy estimates retained for frozen Laya experiments and pre-26014 results.
PRIZE_TABLE = {
    (5, 2): ("一等奖", 10_000_000),
    (5, 1): ("二等奖", 300_000),
    (5, 0): ("三等奖", 10_000),
    (4, 2): ("四等奖", 3_000),
    (4, 1): ("五等奖", 300),
    (3, 2): ("六等奖", 200),
    (4, 0): ("七等奖", 100),
    (3, 1): ("八等奖", 15),
    (2, 2): ("八等奖", 15),
    (3, 0): ("九等奖", 5),
    (1, 2): ("九等奖", 5),
    (2, 1): ("九等奖", 5),
    (0, 2): ("九等奖", 5),
}

MODELS = [
    "random",
    "frequency",
    "bayesian",
    "markov",
    "xgboost",
    "lstm",
    "transformer",
    "genetic",
    "ensemble",
]

MODEL_LABELS = {
    "random": "随机基线",
    "frequency": "频率统计",
    "bayesian": "贝叶斯",
    "markov": "马尔可夫链",
    "xgboost": "XGBoost",
    "lstm": "LSTM 神经网络",
    "transformer": "Transformer",
    "genetic": "遗传算法",
    "ensemble": "集成投票",
}
