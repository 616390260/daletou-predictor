<template>
  <div class="container">
    <div class="page-head">
      <h1>命中分析</h1>
      <p>每期每模型每注的中奖率、奖级分布、按期热力图；让算法的成绩真正看得见。</p>
    </div>

    <!-- 空态 / 加载态 -->
    <div v-if="loading" class="empty-state">
      <div class="empty-icon">⏳</div>
      <div class="empty-title">正在加载数据…</div>
    </div>

    <div v-else-if="!evaluatedIssues.length" class="empty-state">
      <div class="empty-icon">📊</div>
      <div class="empty-title">尚无评估数据</div>
      <div class="empty-desc">
        每期开奖后（周一 / 三 / 六 22:30 自动评估），本页会自动填充。<br />
        目前本期预测可在
        <router-link to="/predictions">预测记录</router-link> 页面查看。
      </div>
    </div>

    <template v-else>
      <!-- 1. 顶部 KPI -->
      <section class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-label">评估期数</div>
          <div class="kpi-val">{{ kpi.issues }}</div>
          <div class="kpi-sub">最近：{{ kpi.latestIssue }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">总投注</div>
          <div class="kpi-val">{{ kpi.totalTickets }}</div>
          <div class="kpi-sub">¥{{ kpi.totalCost }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">中奖注数</div>
          <div class="kpi-val">
            {{ kpi.winTickets }}<small>/{{ kpi.totalTickets }}</small>
          </div>
          <div class="kpi-sub">中奖率 {{ pct(kpi.winRate) }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">回报 / ROI</div>
          <div class="kpi-val" :class="kpi.roi >= 0 ? 'up' : 'down'">
            {{ (kpi.roi * 100).toFixed(1) }}<small>%</small>
          </div>
          <div class="kpi-sub">¥{{ kpi.totalPrize }}</div>
        </div>
      </section>

      <!-- 2. 奖级分布 -->
      <section class="card">
        <div class="card-title">奖级分布</div>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>奖级</th>
                <th class="num">前 / 后命中</th>
                <th class="num">中奖注数</th>
                <th class="num">占比</th>
                <th class="num">单注奖金</th>
                <th class="num">累计奖金</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in prizeRows" :key="row.key">
                <td>
                  <span class="prize-badge" :data-level="row.levelKey">
                    {{ row.label }}
                  </span>
                </td>
                <td class="num mono">
                  <span class="ball-tag front-tag">{{ row.frontHit }}</span>
                  +
                  <span class="ball-tag back-tag">{{ row.backHit }}</span>
                </td>
                <td class="num mono">{{ row.count }}</td>
                <td class="num mono">{{ pct(row.ratio) }}</td>
                <td class="num mono">¥{{ row.amount }}</td>
                <td class="num mono" :class="row.totalAmount > 0 ? 'up' : ''">
                  ¥{{ row.totalAmount }}
                </td>
              </tr>
              <tr class="table-total">
                <td><b>总计</b></td>
                <td></td>
                <td class="num mono"><b>{{ kpi.winTickets }}</b></td>
                <td class="num mono"><b>{{ pct(kpi.winRate) }}</b></td>
                <td></td>
                <td class="num mono up"><b>¥{{ kpi.totalPrize }}</b></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 3. 前/后区命中热力矩阵 -->
      <section class="card">
        <div class="card-title">前/后区命中数分布 · {{ kpi.totalTickets }} 注</div>
        <div class="grid-2">
          <v-chart class="chart" :option="hitMatrixOption" autoresize />
          <div class="matrix-legend">
            <p>
              横轴：前区命中数（0–5），纵轴：后区命中数（0–2）<br />
              格子深浅表示该命中组合出现的次数。标注
              <span class="dot-gold" /> 代表中奖组合。
            </p>
            <ul class="tip-list">
              <li>6 等奖及以上合计：<b>{{ kpi.midHighWin }}</b> 注（{{ pct(kpi.midHighWin / kpi.totalTickets) }}）</li>
              <li>中过最高奖：<b>{{ kpi.bestPrize || "—" }}</b></li>
              <li>平均前区命中：<b>{{ kpi.avgFrontHit.toFixed(2) }}</b> / 5</li>
              <li>平均后区命中：<b>{{ kpi.avgBackHit.toFixed(2) }}</b> / 2</li>
            </ul>
          </div>
        </div>
      </section>

      <!-- 4. 按期×模型 命中热力图 -->
      <section class="card">
        <div class="card-title">每期每模型命中注数（越亮代表 4 注中越多）</div>
        <v-chart class="chart chart-heatmap" :option="issueModelHeatOption" autoresize />
      </section>

      <!-- 5. 模型命中率排行 -->
      <section class="card">
        <div class="card-title">模型命中率排行（累计）</div>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>排名</th>
                <th>模型</th>
                <th class="num">中奖/投注</th>
                <th class="num">中奖率</th>
                <th class="num">前区均值</th>
                <th class="num">后区均值</th>
                <th class="num">累计奖金</th>
                <th class="num">ROI</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(s, i) in modelRanking" :key="s.model">
                <td class="mono">#{{ i + 1 }}</td>
                <td>
                  <span class="model-badge" :data-model="s.model">{{ s.label }}</span>
                </td>
                <td class="num mono">{{ s.wins }}/{{ s.tickets }}</td>
                <td class="num mono">{{ pct(s.hitRate) }}</td>
                <td class="num mono">{{ s.avgFront.toFixed(2) }}</td>
                <td class="num mono">{{ s.avgBack.toFixed(2) }}</td>
                <td class="num mono">¥{{ s.totalPrize }}</td>
                <td class="num mono" :class="s.roi >= 0 ? 'up' : 'down'">
                  {{ (s.roi * 100).toFixed(1) }}%
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 6. 逐期每注详情（可折叠） -->
      <section class="card">
        <div class="card-title card-title-flex">
          <span>逐期每注详情</span>
          <div class="filter-row">
            <select v-model="filterModel" class="select">
              <option value="">全部模型</option>
              <option v-for="m in allModels" :key="m.model" :value="m.model">
                {{ m.label }}
              </option>
            </select>
          </div>
        </div>
        <div class="issue-list">
          <div v-for="item in evaluatedIssues" :key="item.issue" class="issue-card">
            <div class="issue-head" @click="toggleIssue(item.issue)">
              <div>
                <div class="issue-no">第 {{ item.issue }} 期 · {{ item.real.date }}</div>
                <div class="issue-real">
                  <BallRow :front="item.real.front" :back="item.real.back" size="sm" />
                </div>
              </div>
              <div class="issue-meta">
                <span class="meta-chip">{{ item.winTickets }}/{{ item.totalTickets }} 中奖</span>
                <span class="meta-chip" :class="item.roi >= 0 ? 'up' : 'down'">
                  ROI {{ (item.roi * 100).toFixed(0) }}%
                </span>
                <span class="fold-arrow" :class="{ open: openIssues[item.issue] }">▾</span>
              </div>
            </div>
            <div v-show="openIssues[item.issue]" class="issue-body">
              <div
                v-for="m in filteredModels(item)"
                :key="m.model"
                class="detail-row"
                :class="{ 'is-win': m.winTickets > 0 }"
              >
                <div class="detail-head">
                  <span class="model-badge" :data-model="m.model">{{ m.label }}</span>
                  <span class="detail-tag" :class="m.winTickets > 0 ? 'up' : 'muted'">
                    {{ m.winTickets }}/{{ m.tickets.length }}
                    <template v-if="m.bestLevel"> · {{ m.bestLevel }}</template>
                  </span>
                </div>
                <div class="ticket-list">
                  <div
                    v-for="t in m.tickets"
                    :key="t.idx"
                    class="ticket-row"
                    :class="{ 'ticket-win': t.result && t.result.amount > 0 }"
                  >
                    <span class="ticket-idx">#{{ t.idx + 1 }}</span>
                    <BallRow
                      :front="t.front"
                      :back="t.back"
                      :hit-front="item.real.front"
                      :hit-back="item.real.back"
                      size="sm"
                    />
                    <span class="ticket-hit mono">
                      {{ t.result ? `${t.result.front_hit}+${t.result.back_hit}` : "—" }}
                    </span>
                    <span class="ticket-prize mono" :class="t.result && t.result.amount > 0 ? 'up' : 'muted'">
                      {{ t.result?.level || "未中奖" }}
                      <template v-if="t.result?.amount"> · ¥{{ t.result.amount }}</template>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { HeatmapChart } from "echarts/charts";
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  VisualMapComponent,
  DataZoomComponent,
} from "echarts/components";
import VChart from "vue-echarts";
import BallRow from "../components/BallRow.vue";
import { api } from "../api";
import { MODEL_LABELS } from "../api/models";

use([
  CanvasRenderer,
  HeatmapChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  VisualMapComponent,
  DataZoomComponent,
]);

const PRIZE_TABLE = [
  { front: 5, back: 2, level: "一等奖", amount: 10_000_000, key: "p1" },
  { front: 5, back: 1, level: "二等奖", amount: 300_000, key: "p2" },
  { front: 5, back: 0, level: "三等奖", amount: 10_000, key: "p3" },
  { front: 4, back: 2, level: "四等奖", amount: 3_000, key: "p4" },
  { front: 4, back: 1, level: "五等奖", amount: 300, key: "p5" },
  { front: 3, back: 2, level: "六等奖", amount: 200, key: "p6" },
  { front: 4, back: 0, level: "七等奖", amount: 100, key: "p7" },
  { front: 3, back: 1, level: "八等奖", amount: 15, key: "p8" },
  { front: 2, back: 2, level: "八等奖", amount: 15, key: "p8" },
  { front: 3, back: 0, level: "九等奖", amount: 5, key: "p9" },
  { front: 1, back: 2, level: "九等奖", amount: 5, key: "p9" },
  { front: 2, back: 1, level: "九等奖", amount: 5, key: "p9" },
  { front: 0, back: 2, level: "九等奖", amount: 5, key: "p9" },
];

const predictions = ref([]);
const loading = ref(true);
const openIssues = reactive({});
const filterModel = ref("");

const TICKET_PRICE = 2;

/**
 * 最近 N 期评估热力图的上限
 */
const HEATMAP_LIMIT = 40;

function pct(v) {
  if (!isFinite(v)) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

function toggleIssue(issue) {
  openIssues[issue] = !openIssues[issue];
}

/**
 * 仅保留已有命中结果的期
 */
const evaluatedIssues = computed(() => {
  return predictions.value
    .filter((p) => p.real && p.models.some((m) => m.tickets.some((t) => t.result)))
    .map((p) => {
      const models = p.models.map((m) => {
        const winTickets = m.tickets.filter((t) => t.result && t.result.amount > 0).length;
        const bestLevelRow = m.tickets
          .map((t) => t.result)
          .filter((r) => r && r.level)
          .sort((a, b) => (b.amount || 0) - (a.amount || 0))[0];
        return { ...m, winTickets, bestLevel: bestLevelRow?.level };
      });
      const totalTickets = models.reduce((s, m) => s + m.tickets.length, 0);
      const winTickets = models.reduce((s, m) => s + m.winTickets, 0);
      const cost = totalTickets * TICKET_PRICE;
      const prize = models.reduce(
        (s, m) => s + m.tickets.reduce((ss, t) => ss + (t.result?.amount || 0), 0),
        0,
      );
      return {
        ...p,
        models,
        totalTickets,
        winTickets,
        cost,
        prize,
        roi: cost ? (prize - cost) / cost : 0,
      };
    });
});

/**
 * 所有本页出现过的模型列表（供筛选器用）
 */
const allModels = computed(() => {
  const map = new Map();
  evaluatedIssues.value.forEach((p) => {
    p.models.forEach((m) => {
      if (!map.has(m.model)) map.set(m.model, { model: m.model, label: m.label });
    });
  });
  return [...map.values()];
});

function filteredModels(item) {
  if (!filterModel.value) return item.models;
  return item.models.filter((m) => m.model === filterModel.value);
}

/**
 * 累计 KPI
 */
const kpi = computed(() => {
  let tickets = 0;
  let wins = 0;
  let prize = 0;
  let frontHitSum = 0;
  let backHitSum = 0;
  let best = { amount: 0, level: null };
  let midHighWin = 0;

  evaluatedIssues.value.forEach((p) => {
    p.models.forEach((m) => {
      m.tickets.forEach((t) => {
        tickets += 1;
        const r = t.result;
        if (!r) return;
        frontHitSum += r.front_hit || 0;
        backHitSum += r.back_hit || 0;
        if (r.amount > 0) wins += 1;
        if (r.amount > (best.amount || 0)) best = { amount: r.amount, level: r.level };
        prize += r.amount || 0;
        if (r.amount >= 200) midHighWin += 1;
      });
    });
  });

  const cost = tickets * TICKET_PRICE;
  return {
    issues: evaluatedIssues.value.length,
    latestIssue: evaluatedIssues.value[0]?.issue || "—",
    totalTickets: tickets,
    winTickets: wins,
    winRate: tickets ? wins / tickets : 0,
    totalCost: cost,
    totalPrize: prize,
    roi: cost ? (prize - cost) / cost : 0,
    avgFrontHit: tickets ? frontHitSum / tickets : 0,
    avgBackHit: tickets ? backHitSum / tickets : 0,
    bestPrize: best.level,
    midHighWin,
  };
});

/**
 * 按 (front_hit, back_hit) 聚合，得到奖级分布
 */
const hitGrid = computed(() => {
  const grid = {};
  for (let f = 0; f <= 5; f += 1) {
    for (let b = 0; b <= 2; b += 1) {
      grid[`${f},${b}`] = 0;
    }
  }
  evaluatedIssues.value.forEach((p) => {
    p.models.forEach((m) => {
      m.tickets.forEach((t) => {
        if (!t.result) return;
        const key = `${t.result.front_hit},${t.result.back_hit}`;
        grid[key] = (grid[key] || 0) + 1;
      });
    });
  });
  return grid;
});

const prizeRows = computed(() => {
  const countMap = hitGrid.value;
  const total = kpi.value.totalTickets || 1;
  const rows = PRIZE_TABLE.map((r) => {
    const count = countMap[`${r.front},${r.back}`] || 0;
    return {
      key: `${r.front}-${r.back}`,
      levelKey: r.key,
      label: r.level,
      frontHit: r.front,
      backHit: r.back,
      count,
      ratio: count / total,
      amount: r.amount,
      totalAmount: count * r.amount,
    };
  });
  return rows;
});

const hitMatrixOption = computed(() => {
  const grid = hitGrid.value;
  const winKeys = new Set(PRIZE_TABLE.map((r) => `${r.front},${r.back}`));
  const data = [];
  let maxCount = 0;
  for (let f = 0; f <= 5; f += 1) {
    for (let b = 0; b <= 2; b += 1) {
      const c = grid[`${f},${b}`] || 0;
      maxCount = Math.max(maxCount, c);
      data.push([f, b, c, winKeys.has(`${f},${b}`)]);
    }
  }
  return {
    backgroundColor: "transparent",
    tooltip: {
      backgroundColor: "rgba(26,26,36,0.95)",
      borderColor: "rgba(255,255,255,0.14)",
      textStyle: { color: "#f4f4f5" },
      formatter: (p) => {
        const [f, b, c, win] = p.data;
        return `前区命中 ${f} + 后区命中 ${b}<br/>共 <b>${c}</b> 注${win ? " · 🎉 中奖" : ""}`;
      },
    },
    grid: { left: 50, right: 30, top: 30, bottom: 50, containLabel: true },
    xAxis: {
      type: "category",
      data: ["0", "1", "2", "3", "4", "5"],
      name: "前区命中",
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: { color: "#a1a1aa", fontSize: 11 },
      axisLine: { lineStyle: { color: "#3f3f46" } },
      axisLabel: { color: "#a1a1aa" },
      splitArea: { show: true, areaStyle: { color: ["rgba(255,255,255,0.01)"] } },
    },
    yAxis: {
      type: "category",
      data: ["0", "1", "2"],
      name: "后区命中",
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: { color: "#a1a1aa", fontSize: 11 },
      axisLine: { lineStyle: { color: "#3f3f46" } },
      axisLabel: { color: "#a1a1aa" },
    },
    visualMap: {
      min: 0,
      max: maxCount || 1,
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 5,
      textStyle: { color: "#a1a1aa" },
      inRange: { color: ["#1e293b", "#2563eb", "#f59e0b", "#ef4444"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: {
          show: true,
          formatter: (p) => (p.data[2] > 0 ? (p.data[3] ? `⭐ ${p.data[2]}` : p.data[2]) : ""),
          color: "#fff",
          fontWeight: 600,
        },
        itemStyle: { borderColor: "#0a0a0f", borderWidth: 1 },
        emphasis: { itemStyle: { borderColor: "#fcd34d", borderWidth: 2 } },
      },
    ],
  };
});

/**
 * 按期 × 模型 命中热力图：格子值 = 该期该模型 4 注中奖注数
 */
const issueModelHeatOption = computed(() => {
  const issuesSorted = [...evaluatedIssues.value].sort((a, b) =>
    a.issue.localeCompare(b.issue),
  ).slice(-HEATMAP_LIMIT);
  const modelOrder = allModels.value.map((m) => m.model);
  const data = [];
  issuesSorted.forEach((p, xi) => {
    p.models.forEach((m) => {
      const yi = modelOrder.indexOf(m.model);
      if (yi < 0) return;
      data.push([xi, yi, m.winTickets]);
    });
  });
  return {
    backgroundColor: "transparent",
    tooltip: {
      backgroundColor: "rgba(26,26,36,0.95)",
      borderColor: "rgba(255,255,255,0.14)",
      textStyle: { color: "#f4f4f5" },
      formatter: (p) => {
        const issue = issuesSorted[p.data[0]]?.issue;
        const model = modelOrder[p.data[1]];
        const label = MODEL_LABELS[model] || model;
        return `${label} · 第 ${issue} 期<br/>中奖 <b>${p.data[2]}</b>/4 注`;
      },
    },
    grid: { left: 120, right: 30, top: 30, bottom: 60, containLabel: true },
    xAxis: {
      type: "category",
      data: issuesSorted.map((p) => p.issue),
      axisLine: { lineStyle: { color: "#3f3f46" } },
      axisLabel: { color: "#71717a", fontSize: 9, rotate: 35 },
    },
    yAxis: {
      type: "category",
      data: modelOrder.map((m) => MODEL_LABELS[m] || m),
      axisLine: { lineStyle: { color: "#3f3f46" } },
      axisLabel: { color: "#a1a1aa", fontSize: 12 },
    },
    visualMap: {
      min: 0,
      max: 4,
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 10,
      textStyle: { color: "#a1a1aa" },
      inRange: { color: ["#1e293b", "#1d4ed8", "#f59e0b", "#ef4444"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: {
          show: true,
          formatter: (p) => (p.data[2] > 0 ? p.data[2] : ""),
          color: "#fff",
          fontWeight: 600,
        },
        itemStyle: { borderColor: "#0a0a0f", borderWidth: 1 },
      },
    ],
  };
});

/**
 * 模型累计命中率排行
 */
const modelRanking = computed(() => {
  const map = new Map();
  evaluatedIssues.value.forEach((p) => {
    p.models.forEach((m) => {
      const cur =
        map.get(m.model) ||
        {
          model: m.model,
          label: m.label,
          tickets: 0,
          wins: 0,
          frontSum: 0,
          backSum: 0,
          totalPrize: 0,
        };
      m.tickets.forEach((t) => {
        cur.tickets += 1;
        if (t.result) {
          cur.frontSum += t.result.front_hit || 0;
          cur.backSum += t.result.back_hit || 0;
          if (t.result.amount > 0) cur.wins += 1;
          cur.totalPrize += t.result.amount || 0;
        }
      });
      map.set(m.model, cur);
    });
  });
  const arr = [...map.values()].map((s) => ({
    ...s,
    hitRate: s.tickets ? s.wins / s.tickets : 0,
    avgFront: s.tickets ? s.frontSum / s.tickets : 0,
    avgBack: s.tickets ? s.backSum / s.tickets : 0,
    roi: s.tickets ? (s.totalPrize - s.tickets * TICKET_PRICE) / (s.tickets * TICKET_PRICE) : 0,
  }));
  arr.sort((a, b) => {
    if (b.hitRate !== a.hitRate) return b.hitRate - a.hitRate;
    return b.totalPrize - a.totalPrize;
  });
  return arr;
});

onMounted(async () => {
  try {
    predictions.value = (await api.predictions()) || [];
    evaluatedIssues.value.slice(0, 1).forEach((p) => {
      openIssues[p.issue] = true;
    });
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

.container > .card,
.container > section.kpi-row {
  margin-bottom: 20px;
}

/* KPI */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}
.kpi-card {
  padding: 18px 20px;
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.015));
  border: 1px solid var(--border);
}
.kpi-label {
  font-size: 12px;
  color: var(--text-3);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: var(--font-mono);
}
.kpi-val {
  font-size: 28px;
  font-weight: 800;
  font-family: var(--font-mono);
  line-height: 1.1;
  margin-top: 8px;
  letter-spacing: -0.02em;
}
.kpi-val small {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-3);
  margin-left: 2px;
}
.kpi-val.up { color: var(--green); }
.kpi-val.down { color: var(--red); }
.kpi-sub {
  font-size: 12px;
  color: var(--text-3);
  margin-top: 6px;
}

/* 通用 */
.card-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 14px;
}
.card-title-flex {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-wrap { overflow-x: auto; }
.num { text-align: right; }
.mono { font-family: var(--font-mono); font-size: 13px; }
.up { color: var(--green); }
.down { color: var(--red); }
.muted { color: var(--text-3); }

.table-total td { padding-top: 10px; border-top: 1px solid var(--border); }

/* 奖级徽章配色 */
.prize-badge {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-1);
}
.prize-badge[data-level="p1"] { background: rgba(250, 204, 21, 0.22); color: #fde68a; }
.prize-badge[data-level="p2"] { background: rgba(251, 146, 60, 0.22); color: #fed7aa; }
.prize-badge[data-level="p3"] { background: rgba(239, 68, 68, 0.2); color: #fca5a5; }
.prize-badge[data-level="p4"] { background: rgba(236, 72, 153, 0.2); color: #f9a8d4; }
.prize-badge[data-level="p5"] { background: rgba(168, 85, 247, 0.2); color: #d8b4fe; }
.prize-badge[data-level="p6"] { background: rgba(99, 102, 241, 0.2); color: #c7d2fe; }
.prize-badge[data-level="p7"] { background: rgba(6, 182, 212, 0.2); color: #67e8f9; }
.prize-badge[data-level="p8"] { background: rgba(16, 185, 129, 0.2); color: #6ee7b7; }
.prize-badge[data-level="p9"] { background: rgba(132, 204, 22, 0.2); color: #bef264; }

.ball-tag {
  display: inline-block;
  min-width: 20px;
  text-align: center;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 700;
  font-family: var(--font-mono);
  font-size: 12px;
}
.ball-tag.front-tag { background: rgba(239, 68, 68, 0.18); color: #fca5a5; }
.ball-tag.back-tag { background: rgba(59, 130, 246, 0.18); color: #93c5fd; }

/* 模型徽章（复用全局） */
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

/* 热力图布局 */
.grid-2 {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 20px;
  align-items: center;
}
@media (max-width: 820px) { .grid-2 { grid-template-columns: 1fr; } }

.chart { height: 280px; }
.chart-heatmap { height: 380px; }

.matrix-legend p {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.7;
  margin: 0 0 10px 0;
}
.tip-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--text-2);
}
.dot-gold {
  display: inline-block;
  width: 10px;
  height: 10px;
  background: #fcd34d;
  border-radius: 2px;
  margin: 0 4px;
  vertical-align: middle;
}

/* 筛选 */
.filter-row { display: flex; gap: 8px; }
.select {
  padding: 6px 10px;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-1);
}

/* 每期卡片 */
.issue-list { display: flex; flex-direction: column; gap: 12px; }
.issue-card {
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.025);
  overflow: hidden;
}
.issue-head {
  padding: 14px 18px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  gap: 16px;
}
.issue-head:hover { background: rgba(255, 255, 255, 0.03); }

.issue-no {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--text-1);
}
.issue-real { display: flex; align-items: center; }

.issue-meta {
  display: flex;
  gap: 10px;
  align-items: center;
}
.meta-chip {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.06);
  font-family: var(--font-mono);
}
.meta-chip.up { background: rgba(16, 185, 129, 0.18); color: #6ee7b7; }
.meta-chip.down { background: rgba(239, 68, 68, 0.15); color: #fca5a5; }
.fold-arrow {
  display: inline-block;
  color: var(--text-3);
  transition: transform 0.2s;
  font-size: 16px;
}
.fold-arrow.open { transform: rotate(180deg); color: var(--text-1); }

.issue-body {
  padding: 0 18px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-top: 1px dashed var(--border);
}

.detail-row {
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid var(--border);
}
.detail-row.is-win {
  border-color: rgba(250, 204, 21, 0.45);
  background: rgba(250, 204, 21, 0.05);
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.detail-tag {
  font-size: 12px;
  font-weight: 700;
  font-family: var(--font-mono);
  padding: 2px 8px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.06);
}
.detail-tag.up { background: rgba(250, 204, 21, 0.2); color: #fde68a; }

.ticket-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ticket-row {
  display: grid;
  grid-template-columns: 30px auto 60px 1fr;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.2);
}
.ticket-row.ticket-win {
  background: rgba(250, 204, 21, 0.08);
  box-shadow: inset 0 0 0 1px rgba(250, 204, 21, 0.25);
}
.ticket-idx {
  font-size: 12px;
  color: var(--text-3);
  font-family: var(--font-mono);
}
.ticket-hit { font-size: 13px; color: var(--text-2); }
.ticket-prize { font-size: 12px; }
.ticket-prize.up { color: #fde68a; font-weight: 700; }
.ticket-prize.muted { color: var(--text-3); }

@media (max-width: 640px) {
  .ticket-row {
    grid-template-columns: auto 1fr;
    row-gap: 4px;
  }
  .ticket-hit, .ticket-prize { grid-column: span 2; text-align: left; }
}

/* 空态 */
.empty-state {
  padding: 64px 24px;
  text-align: center;
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.015);
}
.empty-icon { font-size: 44px; margin-bottom: 12px; opacity: 0.9; }
.empty-title { font-size: 18px; font-weight: 700; color: var(--text-1); margin-bottom: 8px; }
.empty-desc { font-size: 13px; color: var(--text-3); line-height: 1.7; max-width: 520px; margin: 0 auto; }
.empty-desc a { color: var(--text-1); text-decoration: underline; text-decoration-color: var(--border); }
</style>
