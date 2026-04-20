<template>
  <div class="container">
    <div class="page-head">
      <h1>预测记录</h1>
      <p>每期每个模型给出 4 注投注。绿圈 = 命中号码，未开奖期标记为"待开奖"。</p>
    </div>

    <div v-if="!items.length" class="loading">加载中…</div>

    <div v-else class="list">
      <article v-for="item in items" :key="item.issue" class="card issue-card">
        <header class="issue-head">
          <div>
            <div class="issue-title">
              <span class="issue-num">第 {{ item.issue }} 期</span>
              <span class="tag" v-if="item.real">已开奖 · {{ item.real.date }}</span>
              <span class="tag tag-primary" v-else>待开奖</span>
            </div>
            <div v-if="item.real" class="real-row">
              <span class="real-label">真实开奖</span>
              <BallRow :front="item.real.front" :back="item.real.back" sm />
            </div>
          </div>
        </header>

        <div class="models">
          <div v-for="m in item.models" :key="m.model" class="model-block">
            <div class="model-head">
              <span class="model-badge" :data-model="m.model">{{ m.label }}</span>
              <span class="model-stat" v-if="hasHit(m)">{{ summary(m) }}</span>
            </div>
            <div class="tickets">
              <div v-for="t in m.tickets" :key="t.idx" class="ticket">
                <span class="ticket-idx">#{{ t.idx + 1 }}</span>
                <BallRow
                  :front="t.front"
                  :back="t.back"
                  :hit-front="item.real?.front || []"
                  :hit-back="item.real?.back || []"
                  sm
                />
                <span v-if="t.result" class="result" :class="{ win: t.result.amount > 0 }">
                  {{ t.result.level || "未中奖" }}
                  <em v-if="t.result.amount > 0">+¥{{ fmtMoney(t.result.amount) }}</em>
                </span>
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { api } from "../api";
import BallRow from "../components/BallRow.vue";

const items = ref([]);

function hasHit(m) {
  return m.tickets.some((t) => t.result && t.result.amount > 0);
}

function summary(m) {
  const wins = m.tickets.filter((t) => t.result && t.result.amount > 0).length;
  const total = m.tickets.reduce((s, t) => s + (t.result?.amount || 0), 0);
  return `${wins}/${m.tickets.length} 中奖 · 共 ¥${fmtMoney(total)}`;
}

function fmtMoney(n) {
  if (!n) return "0";
  if (n >= 1e4) return (n / 1e4).toFixed(2) + "万";
  return n.toLocaleString();
}

onMounted(async () => {
  items.value = (await api.predictions()) || [];
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

.list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.issue-card {
  padding: 20px 24px;
}

.issue-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}

.issue-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.issue-num {
  font-size: 17px;
  font-weight: 700;
  font-family: var(--font-mono);
}

.real-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.real-label {
  font-size: 12px;
  color: var(--text-3);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.models {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
}

.model-block {
  padding: 14px 16px;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
}

.model-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

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
.model-badge[data-model="lstm"] { background: rgba(236, 72, 153, 0.2); color: #f9a8d4; }
.model-badge[data-model="genetic"] { background: rgba(16, 185, 129, 0.2); color: #6ee7b7; }
.model-badge[data-model="ensemble"] { background: rgba(245, 158, 11, 0.2); color: #fcd34d; }

.model-stat {
  font-size: 11px;
  color: var(--green);
  font-family: var(--font-mono);
}

.tickets {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ticket {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ticket-idx {
  font-size: 11px;
  color: var(--text-3);
  font-family: var(--font-mono);
  width: 24px;
  flex-shrink: 0;
}

.result {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-3);
  font-family: var(--font-mono);
}

.result.win {
  color: var(--green);
}

.result em {
  font-style: normal;
  margin-left: 4px;
}
</style>
