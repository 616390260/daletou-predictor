<template>
  <div class="container method">
    <!-- Hero -->
    <div class="page-head">
      <h1>方法论 · Walk-Forward Backtest</h1>
      <p class="muted">
        用严格的时间序列回测 + 统计显著性检验，判决 9 个模型是不是真能跑赢随机。
      </p>
    </div>

    <!-- 0. 全量历史反哺 -->
    <section class="card">
      <div class="card-title">0. 全量历史反哺（当前实现）</div>
      <p>
        爬虫入库的 <b>全部开奖期</b>（约 2800+ 期）都会参与：
      </p>
      <ul class="bullets">
        <li><b>频率 / 遗传</b>：统计与适应度窗口默认拉满到库中全部期（上限由配置 <code>max_history_window</code> 保护）</li>
        <li><b>贝叶斯 / 马尔可夫</b>：本就一直遍历整表构建后验与转移矩阵</li>
        <li><b>XGBoost</b>：训练样本从第 WINDOW 期起覆盖到最后一期</li>
        <li><b>LSTM / Transformer</b>：首次全量训练吃满历史；增量微调时回放区扩大到 <code>lstm_incremental_replay_max</code> 期</li>
        <li><b>组合筛选器</b>：分位区间在「可用全部历史」上学出边界（仍用 5%–95% 分位避免极端噪声）</li>
      </ul>
      <p class="muted">
        首页元数据里的 <code>max_history_window</code>、<code>lstm_incremental_replay_max</code> 与当前库期数可对账。
      </p>
    </section>

    <!-- 1. Walk-forward 说明 -->
    <section class="card">
      <div class="card-title">1. 回测协议：Walk-Forward（滚动单步）</div>
      <p>
        时间序列场景下，如果"训练/测试"不按时间切分，模型会偷看未来（look-ahead bias），
        指标会虚高。有效评估应采用严格的 walk-forward：
      </p>
      <ol class="steps">
        <li>从第 <b>k</b> 期开始，每次<b>只用 [1..i-1] 期</b>的历史训练模型</li>
        <li>预测第 <b>i</b> 期号码（每模型出 1 注 5+2）</li>
        <li>实际开奖后记录命中：前区中几个、后区中几个</li>
        <li>i ← i+1，回到第 2 步</li>
      </ol>
      <p class="muted">旧回测记录尚未全部通过权重与时间边界核验。下面的统计仅使用已核验逐期补算或有开奖前运行日志的记录，全库累计指标只作历史描述。</p>
      <p class="muted k-note">
        <b>最早从哪一期开始评估？</b> 不是「随便空 50 期」，而是技术下限：LSTM / Transformer / XGBoost
        需要至少过去 <b>10</b> 期构造序列特征，再加 1 期才能形成一条训练样本，因此全库回测里
        <code>k = backtest_min_start_index</code>（当前为 <b>11</b>，即表中第 <b>12</b> 行对应的期号起才作为「被预测的当期」）。
        更前面的期号仍然全部参与训练，只是不作为第一条 walk-forward 的评估目标。
      </p>
      <div class="walkforward">
        <div class="wf-row" v-for="i in 5" :key="i">
          <div class="wf-train" :style="{ width: 30 + i * 8 + '%' }">训练窗口</div>
          <div class="wf-test">预测</div>
          <div class="wf-label">i = {{ baseIdx + i }}</div>
        </div>
        <div class="wf-legend">
          <span class="box train" /> 可见历史
          <span class="box test" /> 当期（不可见，仅用于开奖后核对）
        </div>
      </div>
    </section>

    <!-- 2. 原假设 + 理论基线 -->
    <section class="card">
      <div class="card-title">2. 原假设与理论基线</div>
      <p>
        如果模型本质上等价于"随机抽号"，那么每一个号码被它抽到的长期频率应该等于：
      </p>
      <div class="formula">
        <div>
          <div class="f-label">前区单号单期命中概率</div>
          <div class="f-val">P<sub>前</sub> = 5 / 35 ≈ <b>0.1429</b></div>
        </div>
        <div>
          <div class="f-label">后区单号单期命中概率</div>
          <div class="f-val">P<sub>后</sub> = 2 / 12 ≈ <b>0.1667</b></div>
        </div>
      </div>
      <p class="muted">
        H<sub>0</sub>（原假设）：均匀、独立开奖。同一注内号码不独立，前后区命中数按
        <a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.hypergeom.html" target="_blank" rel="noopener">超几何分布</a>
        逐期卷积；每期是否中奖才是一次二项事件。全部模型、前后区和中奖率共同进行 Holm 多重校正，α = 0.05。
        图中竖线是理论随机基线的 95% 参考范围，点是实际观测值，并非观测率置信区间。
      </p>
    </section>

    <!-- 3. 每个模型 vs 随机基线 -->
    <section class="card">
      <div class="card-title">
        3. 已核验记录 vs 理论随机基线
        <span v-if="totalIssues" class="chip">已核验 {{ totalIssues }} 期 · {{ totalTickets }} 注</span>
      </div>
      <p v-if="sampleLow" class="warn-banner">
        当前已核验样本仅 {{ totalIssues }} 期，判决仅供观察。需要积累更多可核验的后续预测，单纯增加旧补算期数不能证明有效。
      </p>
      <v-chart v-if="models.length" class="chart chart-ci" :option="frontChartOption" autoresize />
      <v-chart v-if="models.length" class="chart chart-ci" :option="backChartOption" autoresize />

      <div v-if="!models.length" class="empty-state">
        <p>暂无数据，请先触发 backtest workflow 或等待线上累积。</p>
      </div>
    </section>

    <!-- 4. 判决表 -->
    <section class="card" v-if="models.length">
      <div class="card-title">4. 统计判决表</div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>模型</th>
              <th>期数</th>
              <th>前区观测率</th>
              <th>前区校正 p</th>
              <th>后区观测率</th>
              <th>后区校正 p</th>
              <th>中奖 / 注数</th>
              <th>中奖率校正 p</th>
              <th>判决</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in models" :key="m.model">
              <td>
                <span class="model-badge" :data-model="m.model">{{ label(m.model) }}</span>
              </td>
              <td class="mono">{{ m.issues }}</td>
              <td class="mono">
                {{ pct(m.front.observed) }}
                <span class="ci">随机范围 [{{ pct(m.front.ci95[0]) }}, {{ pct(m.front.ci95[1]) }}]</span>
              </td>
              <td class="mono" :class="{ 'p-sig': m.front.significant && !sampleLow }">
                {{ (m.front.adjusted_p_value ?? m.front.p_value).toFixed(3) }}
              </td>
              <td class="mono">
                {{ pct(m.back.observed) }}
                <span class="ci">随机范围 [{{ pct(m.back.ci95[0]) }}, {{ pct(m.back.ci95[1]) }}]</span>
              </td>
              <td class="mono" :class="{ 'p-sig': m.back.significant && !sampleLow }">
                {{ (m.back.adjusted_p_value ?? m.back.p_value).toFixed(3) }}
              </td>
              <td class="mono">{{ m.win_tickets ?? '—' }} / {{ m.tickets }}</td>
              <td class="mono" :class="{ 'p-sig': m.win?.significant && !sampleLow }">{{ m.win ? m.win.adjusted_p_value.toFixed(3) : '—' }}</td>
              <td class="verdict">{{ m.verdict }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 5. 总体结论 -->
    <section class="card conclusion" v-if="models.length">
      <div class="card-title">5. 总体结论</div>
      <p v-if="sampleLow">
        样本量不足（{{ totalIssues }} 期），所有模型都处在"统计无力判决"状态。
        这并不意味着它们有效，而是说"证据不足以否定 H<sub>0</sub>"。
      </p>
      <p v-else-if="anySig">
        有 <b>{{ sigModels.length }}</b> 个模型在多重校正后显著偏离理论随机基线：
        <span v-for="(n, i) in sigModels" :key="n">
          {{ label(n) }}{{ i < sigModels.length - 1 ? "、" : "" }}
        </span>。
        仍需核对偏离方向、数据质量，并用后续开奖前发布的预测复验。短期偏离不等同于稳定预测能力。
      </p>
      <p v-else>
        在当前已核验样本与多重校正下，未检测到显著偏离理论随机基线的模型。证据不足不等同于已经证明模型无效或有效。
      </p>
      <p class="muted tip">
        检验以均匀独立开奖为原假设。走势图可以帮助核查频率、遗漏和异常，但历史形状本身不能证明下一期可预测。
      </p>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { CustomChart, ScatterChart, LineChart } from "echarts/charts";
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
} from "echarts/components";
import VChart from "vue-echarts";
import { api } from "../api";
import { MODEL_LABELS, MODEL_COLORS, MODEL_ORDER } from "../api/models";

use([
  CanvasRenderer,
  CustomChart,
  ScatterChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
]);

const methodology = ref(null);
const models = ref([]);
const meta = ref(null);

const baseIdx = computed(() => {
  // 仅用于示意图的 i 标签：用“当前库期数 - 5”做动态基准，避免硬编码漂移
  const total = meta.value?.total_draws;
  if (!total || Number.isNaN(Number(total))) return 0;
  return Math.max(0, Number(total) - 5);
});

onMounted(async () => {
  const [m, d] = await Promise.all([api.meta(), api.significance()]);
  meta.value = m;
  methodology.value = d?.methodology || null;
  const order = MODEL_ORDER;
  const items = [...(d?.models || [])];
  items.sort((a, b) => order.indexOf(a.model) - order.indexOf(b.model));
  models.value = items;
});

const totalIssues = computed(() =>
  models.value.length ? Math.max(...models.value.map((m) => m.issues)) : 0,
);
const totalTickets = computed(() =>
  models.value.reduce((s, m) => s + m.tickets, 0),
);
const sampleLow = computed(() => totalIssues.value < 30);
const anySig = computed(() =>
  models.value.some((m) => m.front.significant || m.back.significant || m.win?.significant),
);
const sigModels = computed(() =>
  models.value
    .filter((m) => m.front.significant || m.back.significant || m.win?.significant)
    .map((m) => m.model),
);

function label(k) {
  return MODEL_LABELS[k] || k;
}
function pct(v) {
  return `${(v * 100).toFixed(2)}%`;
}

/**
 * 构建"带误差棒"的自定义图：每个模型一根竖线（CI）+ 一个点（观测值）
 * @param {"front"|"back"} key 前区或后区
 * @param {number} theoretical 理论基线（横线）
 */
function buildCIOption(key, theoretical, titleText) {
  const data = models.value.map((m, i) => ({
    name: label(m.model),
    color: MODEL_COLORS[m.model] || "#888",
    idx: i,
    observed: m[key].observed,
    lo: m[key].ci95[0],
    hi: m[key].ci95[1],
    p: m[key].adjusted_p_value ?? m[key].p_value,
    sig: m[key].significant && !sampleLow.value,
    issues: m.issues,
  }));
  const maxHi = Math.max(theoretical, ...data.map((d) => Math.max(d.hi, d.observed)));
  const minLo = Math.min(theoretical, ...data.map((d) => Math.min(d.lo, d.observed)));
  const pad = (maxHi - minLo) * 0.2 + 0.01;

  return {
    backgroundColor: "transparent",
    title: {
      text: titleText,
      left: "center",
      top: 6,
      textStyle: { color: "#d4d4d8", fontSize: 13, fontWeight: 600 },
    },
    tooltip: {
      backgroundColor: "rgba(26,26,36,0.95)",
      borderColor: "rgba(255,255,255,0.14)",
      textStyle: { color: "#f4f4f5" },
      formatter: (p) => {
        const d = p.data;
        return `<b>${d.name}</b><br/>
          观测命中率：<b>${(d.observed * 100).toFixed(2)}%</b><br/>
          随机基线95%范围：[${(d.lo * 100).toFixed(2)}%, ${(d.hi * 100).toFixed(2)}%]<br/>
          理论基线：${(theoretical * 100).toFixed(2)}%<br/>
          校正 p 值：<b>${d.p.toFixed(4)}</b>${d.sig ? " 显著" : ""}<br/>
          回测期数：${d.issues}`;
      },
    },
    grid: { left: 50, right: 20, top: 40, bottom: 70 },
    xAxis: {
      type: "category",
      data: data.map((d) => d.name),
      axisLine: { lineStyle: { color: "#3f3f46" } },
      axisLabel: { color: "#a1a1aa", rotate: 30, fontSize: 11 },
    },
    yAxis: {
      type: "value",
      min: Math.max(0, minLo - pad),
      max: Math.min(1, maxHi + pad),
      axisLine: { lineStyle: { color: "#3f3f46" } },
      axisLabel: {
        color: "#a1a1aa",
        formatter: (v) => `${(v * 100).toFixed(1)}%`,
      },
      splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
    },
    series: [
      {
        type: "custom",
        name: "CI",
        data,
        encode: { x: "idx", y: "observed" },
        renderItem: (params, api) => {
          const d = data[params.dataIndex];
          const pLo = api.coord([params.dataIndex, d.lo]);
          const pHi = api.coord([params.dataIndex, d.hi]);
          const pMid = api.coord([params.dataIndex, d.observed]);
          const halfW = 10;
          return {
            type: "group",
            children: [
              {
                type: "line",
                shape: { x1: pLo[0], y1: pLo[1], x2: pHi[0], y2: pHi[1] },
                style: { stroke: d.color, lineWidth: 2 },
              },
              {
                type: "line",
                shape: {
                  x1: pLo[0] - halfW, y1: pLo[1],
                  x2: pLo[0] + halfW, y2: pLo[1],
                },
                style: { stroke: d.color, lineWidth: 2 },
              },
              {
                type: "line",
                shape: {
                  x1: pHi[0] - halfW, y1: pHi[1],
                  x2: pHi[0] + halfW, y2: pHi[1],
                },
                style: { stroke: d.color, lineWidth: 2 },
              },
              {
                type: "circle",
                shape: { cx: pMid[0], cy: pMid[1], r: 6 },
                style: {
                  fill: d.sig ? "#facc15" : d.color,
                  stroke: "#0a0a0f",
                  lineWidth: 2,
                },
              },
            ],
          };
        },
        markLine: {
          symbol: ["none", "none"],
          lineStyle: { type: "dashed", color: "#f43f5e", width: 1.5 },
          label: {
            formatter: `理论基线 ${(theoretical * 100).toFixed(2)}%`,
            color: "#f43f5e",
            position: "insideEndTop",
          },
          data: [{ yAxis: theoretical }],
        },
      },
    ],
  };
}

const frontChartOption = computed(() =>
  buildCIOption("front", methodology.value?.theoretical_front ?? 5 / 35, "前区观测率与随机基线95%范围"),
);
const backChartOption = computed(() =>
  buildCIOption("back", methodology.value?.theoretical_back ?? 2 / 12, "后区观测率与随机基线95%范围"),
);
</script>

<style scoped>
.method {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.page-head h1 {
  margin: 0 0 4px;
}
.muted {
  color: rgba(212, 212, 216, 0.7);
}
.card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 16px;
  padding: 20px 22px;
}
.card-title {
  font-size: 15px;
  font-weight: 700;
  color: #f4f4f5;
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.chip {
  background: rgba(59, 130, 246, 0.12);
  color: #93c5fd;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 10px;
  border: 1px solid rgba(59, 130, 246, 0.3);
}

/* Walk-forward 示意 */
.walkforward {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wf-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}
.wf-train {
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.25), rgba(59, 130, 246, 0.55));
  color: #bfdbfe;
  padding: 4px 8px;
  border-radius: 4px;
  white-space: nowrap;
}
.wf-test {
  background: rgba(244, 63, 94, 0.35);
  color: #fecdd3;
  padding: 4px 10px;
  border-radius: 4px;
}
.wf-label {
  color: #71717a;
  font-family: var(--mono, monospace);
}
.wf-legend {
  margin-top: 10px;
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #a1a1aa;
}
.wf-legend .box {
  display: inline-block;
  width: 14px;
  height: 10px;
  margin-right: 4px;
  vertical-align: middle;
  border-radius: 2px;
}
.wf-legend .train {
  background: rgba(59, 130, 246, 0.55);
}
.wf-legend .test {
  background: rgba(244, 63, 94, 0.45);
}

.formula {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin: 14px 0;
}
.f-label {
  font-size: 12px;
  color: #a1a1aa;
  margin-bottom: 4px;
}
.f-val {
  font-size: 15px;
  font-family: var(--mono, monospace);
  color: #f4f4f5;
}
.f-val b {
  color: #facc15;
}
.steps {
  padding-left: 20px;
  line-height: 1.9;
}
.steps li::marker {
  color: #3b82f6;
  font-weight: bold;
}

.k-note {
  margin-top: 14px;
  font-size: 13px;
  line-height: 1.75;
}
.k-note code {
  font-size: 12px;
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.12);
  padding: 1px 6px;
  border-radius: 4px;
}

.bullets {
  margin: 10px 0 0;
  padding-left: 20px;
  line-height: 1.85;
  color: #d4d4d8;
}
.bullets code {
  font-size: 12px;
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.12);
  padding: 1px 6px;
  border-radius: 4px;
}

.chart-ci {
  height: 360px;
  width: 100%;
  margin-bottom: 8px;
}

.table-wrap {
  overflow-x: auto;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.table th,
.table td {
  padding: 10px 8px;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.table th {
  color: #a1a1aa;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.03);
}
.mono {
  font-family: var(--mono, monospace);
}
.ci {
  color: #71717a;
  font-size: 11px;
  margin-left: 4px;
}
.p-sig {
  color: #facc15;
  font-weight: 700;
}
.verdict {
  font-size: 12px;
  color: #d4d4d8;
}
.model-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}
.model-badge[data-model="random"] { background: #71717a; }
.model-badge[data-model="frequency"] { background: #3b82f6; }
.model-badge[data-model="bayesian"] { background: #06b6d4; }
.model-badge[data-model="markov"] { background: #a855f7; }
.model-badge[data-model="xgboost"] { background: #84cc16; color: #0a0a0f; }
.model-badge[data-model="lstm"] { background: #ec4899; }
.model-badge[data-model="transformer"] { background: #f43f5e; }
.model-badge[data-model="genetic"] { background: #10b981; }
.model-badge[data-model="ensemble"] { background: #f59e0b; color: #0a0a0f; }

.warn-banner {
  margin: 0 0 14px;
  padding: 10px 14px;
  background: rgba(250, 204, 21, 0.1);
  border: 1px solid rgba(250, 204, 21, 0.3);
  color: #fde68a;
  border-radius: 8px;
  font-size: 13px;
}
.empty-state {
  padding: 30px;
  text-align: center;
  color: #71717a;
}

.conclusion p {
  line-height: 1.8;
}
.up {
  color: #facc15;
}
.tip {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed rgba(255, 255, 255, 0.08);
  font-size: 13px;
}
</style>
