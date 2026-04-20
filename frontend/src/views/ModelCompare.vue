<template>
  <div class="container">
    <div class="page-head">
      <h1>模型对比</h1>
      <p>多模型长期命中率、投入产出比、号码频次热力图。</p>
    </div>

    <div v-if="loading" class="empty-state">
      <div class="empty-icon">⏳</div>
      <div class="empty-title">正在加载数据…</div>
    </div>

    <div v-else-if="!stats.summary.length" class="empty-state">
      <div class="empty-icon">📊</div>
      <div class="empty-title">尚无评估数据</div>
      <div class="empty-desc">
        每期开奖后（周一/三/六 22:30 自动评估），本页将自动展示各模型命中率、ROI、冷热号。<br />
        目前本期预测可在 <router-link to="/predictions">预测记录</router-link> 页面查看。
      </div>
    </div>

    <template v-else>
      <div class="card">
        <div class="card-title">命中率 vs 随机基线</div>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>模型</th>
                <th class="num">参与期数</th>
                <th class="num">总投注</th>
                <th class="num">中奖注</th>
                <th class="num">中奖率</th>
                <th class="num">平均前区命中</th>
                <th class="num">投入 / 回报</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in stats.summary" :key="s.model">
                <td>
                  <span class="model-badge" :data-model="s.model">{{ s.label }}</span>
                </td>
                <td class="num mono">{{ s.issues }}</td>
                <td class="num mono">{{ s.tickets }}</td>
                <td class="num mono">{{ s.win_tickets }}</td>
                <td class="num mono">{{ (s.hit_rate * 100).toFixed(2) }}%</td>
                <td class="num mono">{{ s.avg_front_hit.toFixed(2) }}</td>
                <td class="num mono" :class="s.roi >= 0 ? 'up' : 'down'">
                  ¥{{ s.cost }} → ¥{{ s.total_prize }}
                  <br />
                  <small>{{ (s.roi * 100).toFixed(1) }}%</small>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card" v-if="hasHitTrend">
        <div class="card-title">模型命中率滚动曲线（越多期数据越能暴露真实水平）</div>
        <v-chart class="chart" :option="hitChartOption" autoresize />
      </div>

      <div class="card" v-if="hasTrend">
        <div class="card-title">投入产出比累计曲线</div>
        <v-chart class="chart" :option="roiChartOption" autoresize />
      </div>

      <div class="card" v-if="frequency">
        <div class="card-title">号码冷热热力图 · 近 100 期</div>
        <v-chart class="chart heat-chart" :option="freqChartOption" autoresize />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from "vue";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart, BarChart, HeatmapChart } from "echarts/charts";
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  VisualMapComponent,
  DataZoomComponent,
} from "echarts/components";
import VChart from "vue-echarts";
import { api } from "../api";

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  HeatmapChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  VisualMapComponent,
  DataZoomComponent,
]);

const stats = ref({ summary: [], trend: {} });
const frequency = ref(null);
const loading = ref(true);

import { MODEL_COLORS, MODEL_LABELS } from "../api/models";

const hasTrend = computed(() => {
  return Object.keys(stats.value.trend || {}).length > 0;
});

const hasHitTrend = computed(() => {
  return Object.keys(stats.value.hit_trend || {}).length > 0;
});

const hitChartOption = computed(() => {
  const trend = stats.value.hit_trend || {};
  const allIssues = new Set();
  Object.values(trend).forEach((arr) => arr.forEach((p) => allIssues.add(p.issue)));
  const xAxis = [...allIssues].sort();

  const series = Object.entries(trend).map(([model, arr]) => {
    const map = Object.fromEntries(arr.map((p) => [p.issue, p.rate]));
    return {
      name: MODEL_LABELS[model] || model,
      type: "line",
      smooth: true,
      showSymbol: false,
      lineStyle: { color: MODEL_COLORS[model], width: 2 },
      itemStyle: { color: MODEL_COLORS[model] },
      data: xAxis.map((i) => (map[i] !== undefined ? (map[i] * 100).toFixed(2) : null)),
    };
  });

  return {
    backgroundColor: "transparent",
    textStyle: { color: "#a1a1aa", fontFamily: "inherit" },
    grid: { left: 50, right: 20, top: 40, bottom: 60 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(26,26,36,0.95)",
      borderColor: "rgba(255,255,255,0.14)",
      textStyle: { color: "#f4f4f5" },
      valueFormatter: (v) => (v === null ? "—" : `${v}%`),
    },
    legend: { top: 5, textStyle: { color: "#a1a1aa" }, icon: "roundRect" },
    xAxis: {
      type: "category",
      data: xAxis,
      axisLine: { lineStyle: { color: "#3f3f46" } },
      axisLabel: { color: "#71717a", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      axisLine: { lineStyle: { color: "#3f3f46" } },
      splitLine: { lineStyle: { color: "rgba(255,255,255,0.04)" } },
      axisLabel: { formatter: "{value}%", color: "#71717a" },
    },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 20, bottom: 10 }],
    series,
  };
});

const roiChartOption = computed(() => {
  const trend = stats.value.trend || {};
  const allIssues = new Set();
  Object.values(trend).forEach((arr) => arr.forEach((p) => allIssues.add(p.issue)));
  const xAxis = [...allIssues].sort();

  const series = Object.entries(trend).map(([model, arr]) => {
    const map = Object.fromEntries(arr.map((p) => [p.issue, p.roi]));
    return {
      name: MODEL_LABELS[model] || model,
      type: "line",
      smooth: true,
      showSymbol: false,
      lineStyle: { color: MODEL_COLORS[model], width: 2 },
      itemStyle: { color: MODEL_COLORS[model] },
      data: xAxis.map((i) => (map[i] !== undefined ? (map[i] * 100).toFixed(2) : null)),
    };
  });

  return {
    backgroundColor: "transparent",
    textStyle: { color: "#a1a1aa", fontFamily: "inherit" },
    grid: { left: 50, right: 20, top: 40, bottom: 50 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(26,26,36,0.95)",
      borderColor: "rgba(255,255,255,0.14)",
      textStyle: { color: "#f4f4f5" },
      valueFormatter: (v) => (v === null ? "—" : `${v}%`),
    },
    legend: {
      top: 5,
      textStyle: { color: "#a1a1aa" },
      icon: "roundRect",
    },
    xAxis: {
      type: "category",
      data: xAxis,
      axisLine: { lineStyle: { color: "#3f3f46" } },
      axisLabel: { color: "#71717a", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      axisLine: { lineStyle: { color: "#3f3f46" } },
      splitLine: { lineStyle: { color: "rgba(255,255,255,0.04)" } },
      axisLabel: { formatter: "{value}%", color: "#71717a" },
    },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 20, bottom: 10 }],
    series,
  };
});

const freqChartOption = computed(() => {
  if (!frequency.value) return {};
  const win = frequency.value.recent100;
  const frontData = Object.entries(win.front)
    .map(([n, c]) => [Number(n), c])
    .sort((a, b) => a[0] - b[0]);
  const backData = Object.entries(win.back)
    .map(([n, c]) => [Number(n), c])
    .sort((a, b) => a[0] - b[0]);

  return {
    backgroundColor: "transparent",
    textStyle: { color: "#a1a1aa" },
    grid: [
      { left: 50, right: 20, top: 50, height: 120 },
      { left: 50, right: 20, top: 230, height: 80 },
    ],
    xAxis: [
      {
        gridIndex: 0,
        type: "category",
        data: frontData.map((d) => String(d[0]).padStart(2, "0")),
        axisLine: { lineStyle: { color: "#3f3f46" } },
        axisLabel: { color: "#71717a", fontSize: 10 },
      },
      {
        gridIndex: 1,
        type: "category",
        data: backData.map((d) => String(d[0]).padStart(2, "0")),
        axisLine: { lineStyle: { color: "#3f3f46" } },
        axisLabel: { color: "#71717a", fontSize: 10 },
      },
    ],
    yAxis: [
      {
        gridIndex: 0,
        type: "value",
        name: "前区",
        nameTextStyle: { color: "#a1a1aa" },
        axisLine: { lineStyle: { color: "#3f3f46" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.04)" } },
        axisLabel: { color: "#71717a" },
      },
      {
        gridIndex: 1,
        type: "value",
        name: "后区",
        nameTextStyle: { color: "#a1a1aa" },
        axisLine: { lineStyle: { color: "#3f3f46" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.04)" } },
        axisLabel: { color: "#71717a" },
      },
    ],
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(26,26,36,0.95)",
      borderColor: "rgba(255,255,255,0.14)",
      textStyle: { color: "#f4f4f5" },
    },
    series: [
      {
        name: "前区频次",
        type: "bar",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: frontData.map((d) => d[1]),
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "#ef4444" },
              { offset: 1, color: "#b91c1c" },
            ],
          },
        },
      },
      {
        name: "后区频次",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: backData.map((d) => d[1]),
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "#3b82f6" },
              { offset: 1, color: "#1d4ed8" },
            ],
          },
        },
      },
    ],
  };
});

onMounted(async () => {
  try {
    const [s, f] = await Promise.all([api.stats(), api.frequency()]);
    stats.value = s || { summary: [], trend: {} };
    frequency.value = f;
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.page-head h1 {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.page-head p {
  color: var(--text-3);
  font-size: 14px;
  margin-top: 4px;
  margin-bottom: 24px;
}

.container > .card {
  margin-bottom: 20px;
}

.table-wrap {
  overflow-x: auto;
}

.mono {
  font-family: var(--font-mono);
  font-size: 13px;
}

.num {
  text-align: right;
}

.num small {
  color: var(--text-3);
  font-size: 11px;
}

.up { color: var(--green); }
.down { color: var(--red); }

.model-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
}

.model-badge[data-model="random"] { background: rgba(113, 113, 122, 0.2); color: #d4d4d8; }
.model-badge[data-model="frequency"] { background: rgba(59, 130, 246, 0.2); color: #93c5fd; }
.model-badge[data-model="bayesian"] { background: rgba(6, 182, 212, 0.2); color: #67e8f9; }
.model-badge[data-model="markov"] { background: rgba(168, 85, 247, 0.2); color: #d8b4fe; }
.model-badge[data-model="xgboost"] { background: rgba(132, 204, 22, 0.2); color: #bef264; }
.model-badge[data-model="lstm"] { background: rgba(236, 72, 153, 0.2); color: #f9a8d4; }
.model-badge[data-model="transformer"] { background: rgba(244, 63, 94, 0.2); color: #fda4af; }
.model-badge[data-model="genetic"] { background: rgba(16, 185, 129, 0.2); color: #6ee7b7; }
.model-badge[data-model="ensemble"] { background: rgba(245, 158, 11, 0.2); color: #fcd34d; }

.chart {
  height: 400px;
}

.heat-chart {
  height: 400px;
}

.empty-state {
  padding: 64px 24px;
  text-align: center;
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.015);
}
.empty-icon {
  font-size: 44px;
  margin-bottom: 12px;
  opacity: 0.9;
}
.empty-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-1);
  margin-bottom: 8px;
}
.empty-desc {
  font-size: 13px;
  color: var(--text-3);
  line-height: 1.7;
  max-width: 520px;
  margin: 0 auto;
}
.empty-desc a {
  color: var(--text-1);
  text-decoration: underline;
  text-decoration-color: var(--border);
}
</style>
