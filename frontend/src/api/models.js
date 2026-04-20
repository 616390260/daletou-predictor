/**
 * 模型色标 & 标签配置（前端统一口径）
 */

export const MODEL_COLORS = {
  random: "#71717a",
  frequency: "#3b82f6",
  bayesian: "#06b6d4",
  markov: "#a855f7",
  lstm: "#ec4899",
  genetic: "#10b981",
  ensemble: "#f59e0b",
};

export const MODEL_LABELS = {
  random: "随机基线",
  frequency: "频率统计",
  bayesian: "贝叶斯",
  markov: "马尔可夫链",
  lstm: "LSTM 神经网络",
  genetic: "遗传算法",
  ensemble: "集成投票",
};

export const MODEL_ORDER = [
  "random",
  "frequency",
  "bayesian",
  "markov",
  "lstm",
  "genetic",
  "ensemble",
];
